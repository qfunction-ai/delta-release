"""
Audit logging middleware.

Logs all API requests to the audit_logs table.

Uses pure ASGI instead of BaseHTTPMiddleware to avoid buffering
streaming responses. BaseHTTPMiddleware pipes the response body
through an anyio memory stream with buffer=0, which deadlocks
streaming handlers when the middleware does any work between
call_next() and return.
"""

import json
import logging
import re
import time

from sqlalchemy import insert

from app.audit.models import AuditLog
from app.database import _get_session_maker

# Bounded semaphore to prevent unbounded task spawning for audit log writes.
# Without this, a burst of requests could create thousands of asyncio tasks
# that all compete for DB connections.
_AUDIT_SEMAPHORE_MAX = 50
_audit_semaphore = None


def _get_audit_semaphore():
    """Get or create the module-level audit semaphore."""
    global _audit_semaphore
    if _audit_semaphore is None:
        import asyncio

        _audit_semaphore = asyncio.Semaphore(_AUDIT_SEMAPHORE_MAX)
    return _audit_semaphore


# Paths that contain sensitive data — redact query strings from audit logs
SENSITIVE_PATHS = {"/api/chat/stream", "/api/auth/login", "/api/auth/change-password"}

# UUID regex for extracting resource IDs from request paths
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class AuditMiddleware:
    """Pure ASGI middleware to log all API requests."""

    # Paths to skip logging
    SKIP_PATHS = {"/health", "/scheduler/status", "/favicon.ico"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip certain paths
        path = scope.get("path", "")
        if path in self.SKIP_PATHS or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        start_time = time.time()

        headers_dict = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        server = scope.get("server", ("", 0))
        x_forwarded_for = headers_dict.get("x-forwarded-for", "")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = server[0] if server else None
        user_agent = headers_dict.get("user-agent", "")[:500]
        query_string = scope.get("query_string", b"").decode()

        # Determine action and resource
        action = self._get_action(scope)
        resource_type = self._get_resource_type(scope)
        resource_id = self._get_resource_id(scope)

        # Capture response status code
        status_code = 0
        user_id = None
        auth_method = "jwt"

        async def send_with_audit(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        await self.app(scope, receive, send_with_audit)

        # Try to get user_id from the request state — but since we're in
        # pure ASGI, we don't have access to Starlette's request.state.
        # Instead, we parse the Authorization header to identify the user.
        # This is a compromise — the audit log may not have user_id for
        # all requests, but it avoids the BaseHTTPMiddleware deadlock.
        try:
            auth_header = headers_dict.get("authorization", "")
            if auth_header.startswith("Bearer "):
                from app.auth.security import decode_access_token

                payload = decode_access_token(auth_header[7:])
                if payload:
                    user_id = payload.get("sub")
                    auth_method = "jwt"
        except Exception as e:
            logger.debug("Failed to extract user_id from request: %s", e)

        service_token = headers_dict.get("x-service-token", "")
        if service_token:
            auth_method = "service"

        if any(path.startswith(p) for p in SENSITIVE_PATHS):
            query_str = "[REDACTED]"
        else:
            query_str = query_string

        details = {
            "method": scope.get("method", ""),
            "path": path,
            "query": query_str,
            "duration_ms": round((time.time() - start_time) * 1000, 2),
            "auth_method": auth_method,
        }

        # Write audit log in background to avoid blocking.
        # Use a bounded semaphore to prevent unbounded task spawning under load.
        import asyncio

        _audit_semaphore = getattr(scope.get("app", {}), "_audit_semaphore", None)
        if _audit_semaphore is None:
            # Fallback: create a module-level semaphore if not on the app
            _audit_semaphore = _get_audit_semaphore()

        async def _write_audit():
            async with _audit_semaphore:
                try:
                    async with _get_session_maker()() as session:
                        await session.execute(
                            insert(AuditLog).values(
                                user_id=user_id,
                                action=action,
                                resource_type=resource_type,
                                resource_id=resource_id,
                                details=json.dumps(details),
                                ip_address=ip_address,
                                user_agent=user_agent,
                                status_code=status_code,
                            )
                        )
                        await session.commit()
                except Exception as audit_err:
                    logging.getLogger(__name__).error("Audit log write failed: %s", audit_err)

        asyncio.create_task(_write_audit())

    def _get_action(self, scope) -> str:
        method = scope.get("method", "")
        path = scope.get("path", "")

        if method == "GET":
            if path.endswith("/"):
                return "list"
            return "read"
        elif method == "POST":
            if "/run" in path or "/execute" in path:
                return "execute"
            if "/login" in path:
                return "login"
            if "/register" in path:
                return "register"
            if "/stream" in path:
                return "stream"
            return "create"
        elif method in ("PUT", "PATCH"):
            return "update"
        elif method == "DELETE":
            return "delete"
        return method.lower()

    def _get_resource_type(self, scope) -> str | None:
        path = scope.get("path", "")
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "api":
            return parts[1]
        return None

    def _get_resource_id(self, scope) -> str | None:
        path = scope.get("path", "")
        parts = path.strip("/").split("/")
        for part in parts:
            if _UUID_RE.match(part):
                return part
        for part in parts:
            if part.startswith("agent-"):
                return part
        return None
