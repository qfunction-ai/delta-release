import gzip
import logging
import os
import shutil
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.agents.letta_proxy import router as letta_proxy_router
from app.agents.routes import router as agents_router
from app.audit.middleware import AuditMiddleware
from app.audit.routes import router as audit_router
from app.auth.dependencies import get_admin_user
from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.config import get_cors_origins, get_settings
from app.credentials.routes import router as credentials_router
from app.dashboard.routes import router as dashboard_router
from app.database import init_db
from app.docs.routes import router as docs_router
from app.evals.routes import router as evals_router
from app.export_import import router as export_import_router
from app.lessons.routes import router as lessons_router
from app.logs.routes import router as logs_router
from app.observability.routes import router as observability_router
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.scheduler import start_scheduler, stop_scheduler
from app.settings.routes import router as settings_router
from app.skills.routes import router as skills_router
from app.tools.routes import router as tools_router
from app.workflows.routes import router as workflows_router

LOG_DIR = "/data/logs"
LOG_FILE = os.path.join(LOG_DIR, "backend.log")

# Set up file logging only when the log directory is writable.
# In test environments or read-only containers, skip file logging gracefully.
_log_dir_exists = os.path.isdir(LOG_DIR)
if _log_dir_exists:
    try:
        # Touch the file to confirm writability
        with open(LOG_FILE, "a"):
            pass
    except OSError:
        _log_dir_exists = False

if _log_dir_exists:
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=50 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    file_handler.setLevel(logging.INFO)

    # Attach to the "app" logger, not the root logger.
    # uvicorn's dictConfig replaces the root logger's handlers on startup,
    # which would remove our file handler. The "app" logger is unaffected
    # by uvicorn's config, and with propagate=True (default), messages
    # also reach the root logger's console handler for stdout/Docker logs.
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(file_handler)

# Quieten SQLAlchemy engine logging — echo=True in dev mode is very verbose
# Set level on the logger (not just the handler) so it doesn't propagate
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def rotate_external_logs(log_dir: str = LOG_DIR, max_bytes: int = 50 * 1024 * 1024, backup_count: int = 3):
    """Rotate postgres.log and letta.log in the shared logs volume.

    Uses the same policy as the backend's RotatingFileHandler:
    50MB max, 3 backups. Old backups are gzip-compressed.
    """
    for log_name in ("postgres.log", "letta.log"):
        log_path = os.path.join(log_dir, log_name)
        if not os.path.exists(log_path):
            continue
        try:
            if os.path.getsize(log_path) < max_bytes:
                continue
        except OSError:
            continue

        # Rotate: .log.3.gz → delete, .log.2.gz → .log.3.gz, .log.1.gz → .log.2.gz, .log → .log.1.gz
        for i in range(backup_count, 0, -1):
            gz_path = os.path.join(log_dir, f"{log_name}.{i}.gz")
            if i == backup_count:
                if os.path.exists(gz_path):
                    os.remove(gz_path)
                continue
            if os.path.exists(gz_path):
                new_path = os.path.join(log_dir, f"{log_name}.{i + 1}.gz")
                os.rename(gz_path, new_path)

        # Compress current log → .log.1.gz
        gz_path = os.path.join(log_dir, f"{log_name}.1.gz")
        with open(log_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        # Truncate the log file (don't delete — the tee pipe is still writing to it)
        with open(log_path, "w") as f:
            f.truncate(0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger = logging.getLogger("app.main")
    logger.info("Delta backend starting up")
    await init_db()
    logger.info("Database initialized")

    # Migrate credentials from v0 (SHA-256) to v1 (PBKDF2) if needed
    try:
        from app.credentials.encryption import (
            check_for_v0_credentials,
            migrate_credentials_to_v1,
            migrate_credentials_to_v2,
        )
        from app.database import _get_session_maker

        async with _get_session_maker()() as session:
            await migrate_credentials_to_v1(session)
            await migrate_credentials_to_v2(session)
            v0_count = await check_for_v0_credentials(session)
            if v0_count > 0:
                logger.error(
                    "SECURITY: %d credential(s) still encrypted with v0 (raw SHA-256, no salt). "
                    "Migration may have failed. These credentials are vulnerable to brute-force. "
                    "Investigate and re-encrypt immediately.",
                    v0_count,
                )
    except (SQLAlchemyError, ValueError) as e:
        logger.error(
            "Credential migration failed: %s. Refusing to start with potentially unencrypted credentials.",
            e,
        )
        raise

    start_scheduler()
    logger.info("Scheduler started")

    # Schedule external log rotation every 10 minutes
    from app.scheduler import get_scheduler

    sched = get_scheduler()
    sched.add_job(
        rotate_external_logs,
        "interval",
        minutes=10,
        id="log_rotation",
        replace_existing=True,
    )
    logger.info("External log rotation scheduled (every 10m)")

    # Startup banner
    banner = (
        "\n  Delta is running at http://localhost:3000\n"
        "  Stop:             docker compose down\n"
        "  Reset (DELETES):  docker compose down -v"
    )
    logger.info(banner)
    # Also print to stdout so it shows in docker compose logs
    import sys

    sys.stdout.write(banner + "\n")
    sys.stdout.flush()
    yield
    # Shutdown
    logger.info("Delta backend shutting down")
    stop_scheduler()


app = FastAPI(
    title="Delta API",
    description="Cybersecurity workflow automation platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# Catch-all for unhandled exceptions — prevent stack trace leakage
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Log unhandled exceptions and return a generic error to the client.

    Adds CORS headers so the browser can read the error response.
    Without this, unhandled exceptions return 500s without CORS headers,
    and the browser blocks the response — reporting it as a CORS error
    instead of the actual 500.
    """
    import logging

    logging.getLogger("app.main").error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    response = JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )
    # Add CORS headers so the browser can read the error response
    origin = request.headers.get("origin", "")
    if origin in get_cors_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


app.add_middleware(SlowAPIMiddleware)

# CORS for frontend — origins configurable via DELTA_CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Service-Token"],
)

# Audit logging middleware
app.add_middleware(AuditMiddleware)


# Security headers — set via pure ASGI middleware to avoid BaseHTTPMiddleware
# buffering streaming responses. BaseHTTPMiddleware pipes the response body
# through an anyio memory stream with buffer=0, which means the handler blocks
# on every send until the client reads. For streaming endpoints that produce
# chunks slowly (e.g., agent execution), this works fine. But if ANY middleware
# does work between call_next() and return, the handler deadlocks because the
# client can't start reading the body until the middleware returns.
class _SecurityHeadersMiddleware:
    """Pure ASGI middleware that adds security headers without buffering."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-content-type-options"] = b"nosniff"
                headers[b"x-frame-options"] = b"DENY"
                headers[b"x-xss-protection"] = b"0"
                headers[b"referrer-policy"] = b"strict-origin-when-cross-origin"
                headers[b"permissions-policy"] = b"camera=(), microphone=(), geolocation=()"
                headers[b"content-security-policy"] = b"default-src 'none'"
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(_SecurityHeadersMiddleware)

# Include routers
app.include_router(auth_router)
app.include_router(letta_proxy_router)
app.include_router(agents_router)
app.include_router(credentials_router)
app.include_router(docs_router)
app.include_router(skills_router)
app.include_router(tools_router)
app.include_router(workflows_router)
app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(logs_router)
app.include_router(dashboard_router)
app.include_router(lessons_router)
app.include_router(evals_router)
app.include_router(settings_router)
app.include_router(export_import_router)
app.include_router(observability_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/health/detailed")
async def health_detailed():
    """Check connectivity to all dependent services.

    Returns per-service status so the frontend can surface which
    service is down instead of showing a generic error.
    """
    import httpx
    from sqlalchemy import text

    from app.database import _get_session_maker

    services = {}
    overall = "healthy"

    # Postgres
    try:
        session_maker = _get_session_maker()
        async with session_maker() as db:
            await db.execute(text("SELECT 1"))
        services["postgres"] = {"status": "healthy"}
    except Exception as e:
        services["postgres"] = {"status": "unhealthy", "error": str(e)}
        overall = "degraded"

    # Letta
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{get_settings().letta_base_url}/v1/health/")
            if res.status_code == 200:
                data = res.json()
                services["letta"] = {"status": "healthy", "version": data.get("version")}
            else:
                services["letta"] = {"status": "unhealthy", "status_code": res.status_code}
                overall = "degraded"
    except Exception as e:
        services["letta"] = {"status": "unreachable", "error": str(e)}
        overall = "degraded"

    # Ollama
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    ollama_host = ollama_base.rstrip("/v1").rstrip("/v1")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{ollama_host}/api/tags")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                services["ollama"] = {"status": "healthy", "models": models}
            else:
                services["ollama"] = {"status": "unhealthy", "status_code": res.status_code}
                overall = "degraded"
    except Exception as e:
        services["ollama"] = {"status": "unreachable", "error": str(e)}
        overall = "degraded"

    # Eval service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{get_settings().eval_url}/health")
            if res.status_code == 200:
                services["eval"] = {"status": "healthy"}
            else:
                services["eval"] = {"status": "unhealthy", "status_code": res.status_code}
                overall = "degraded"
    except Exception as e:
        services["eval"] = {"status": "unreachable", "error": str(e)}
        # Eval being down is not critical — don't degrade overall status
        services["eval"]["optional"] = True

    return {"status": overall, "services": services}


@app.get("/scheduler/status")
async def scheduler_status(current_user=Depends(get_admin_user)):
    """Check scheduler status."""
    from app.scheduler import get_scheduled_workflows, get_scheduler

    sched = get_scheduler()
    return {
        "running": sched.running,
        "jobs_count": len(sched.get_jobs()),
        "jobs": get_scheduled_workflows(),
    }
