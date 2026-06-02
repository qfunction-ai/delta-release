"""Shared test fixtures for Delta backend tests."""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import String, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add project root to sys.path so `shared.code_safety` is importable
# (the Docker container copies shared/ next to the app, but the test
# runner runs from backend/ without the project root on the path)
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Save the real service token before overriding it — E2E tests need the
# real token to authenticate against the live backend, while unit tests
# use a fake value that doesn't leak into the shared config volume.
_REAL_SERVICE_TOKEN = os.environ.get("DELTA_SERVICE_TOKEN", "")

# Force dev mode and known secrets before any app imports
os.environ["DELTA_DEV_MODE"] = "1"
os.environ["DELTA_JWT_SECRET"] = "test-jwt-secret-for-testing-only"
os.environ["DELTA_CREDENTIALS_ENCRYPTION_KEY"] = "short-test-key"
os.environ["DELTA_SERVICE_TOKEN"] = "test-service-token"

from app.database import Base, get_db


class SQLiteUUID(TypeDecorator):
    """UUID type that stores as string in SQLite."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(str(value))
        return value


def _create_test_app():
    """Create a FastAPI app instance for testing — no rate limits, no audit middleware."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    from app.agents.routes import router as agents_router
    from app.audit.routes import router as audit_router
    from app.auth.routes import router as auth_router
    from app.chat.routes import router as chat_router
    from app.credentials.routes import router as credentials_router
    from app.dashboard.routes import router as dashboard_router
    from app.docs.routes import router as docs_router
    from app.evals.routes import router as evals_router
    from app.export_import import router as export_import_router
    from app.lessons.routes import router as lessons_router
    from app.logs.routes import router as logs_router
    from app.observability.routes import router as observability_router
    from app.settings.routes import router as settings_router
    from app.skills.routes import router as skills_router
    from app.tools.routes import router as tools_router
    from app.workflows.routes import router as workflows_router

    test_app = FastAPI(title="Delta Test API")

    # Set up a very permissive rate limiter so @limiter.limit decorators don't 429
    test_limiter = Limiter(key_func=get_remote_address, default_limits=["1000/minute"])
    test_app.state.limiter = test_limiter

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    test_app.include_router(auth_router)
    test_app.include_router(agents_router)
    test_app.include_router(credentials_router)
    test_app.include_router(skills_router)
    test_app.include_router(tools_router)
    test_app.include_router(workflows_router)
    test_app.include_router(chat_router)
    test_app.include_router(audit_router)
    test_app.include_router(logs_router)
    test_app.include_router(dashboard_router)
    test_app.include_router(lessons_router)
    test_app.include_router(evals_router)
    test_app.include_router(settings_router)
    test_app.include_router(docs_router)
    test_app.include_router(export_import_router)
    test_app.include_router(observability_router)

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return test_app


_sqlite_patched = False


def _patch_metadata_for_sqlite():
    """Replace PostgreSQL UUID and ENUM types with SQLite-compatible types.

    Idempotent — only patches once.
    Imports all model modules to ensure metadata is populated.
    """
    global _sqlite_patched
    if _sqlite_patched:
        return
    _sqlite_patched = True

    # Import all model modules to populate Base.metadata
    from sqlalchemy import Enum
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    import app.agents.models  # noqa: F401
    import app.audit.models  # noqa: F401
    import app.auth.models  # noqa: F401
    import app.credentials.models  # noqa: F401
    import app.evals.models  # noqa: F401
    import app.lessons.models  # noqa: F401
    import app.settings.models  # noqa: F401
    import app.skills.models  # noqa: F401
    import app.tools.models  # noqa: F401
    import app.workflows.models  # noqa: F401

    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, PG_UUID):
                column.type = SQLiteUUID()
            elif isinstance(column.type, Enum):
                column.type = String(20)


# --- SQLite test database ---


@pytest_asyncio.fixture
async def engine():
    """Create an in-memory SQLite engine for tests."""
    _patch_metadata_for_sqlite()

    eng = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Create a fresh database session for a test."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def app_client(engine):
    """Create an httpx AsyncClient that talks to a test FastAPI app with a SQLite DB.

    Uses a lightweight test app without rate limiting or audit middleware.
    Patches pg_advisory_xact_lock (PostgreSQL-only) to be a no-op for SQLite compat.
    Resets rate limiter storage between tests.
    """
    # Reset the rate limiter's in-memory storage so limits don't carry over between tests
    from app.rate_limit import limiter

    limiter.reset()

    test_app = _create_test_app()

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            original_execute = session.execute

            async def patched_execute(statement, params=None, **kwargs):
                from sqlalchemy.sql.elements import TextClause

                if isinstance(statement, TextClause) and "pg_advisory_xact_lock" in str(statement):
                    return None
                return await original_execute(statement, params, **kwargs)

            session.execute = patched_execute
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    test_app.dependency_overrides.clear()


# --- Auth helpers ---


@pytest_asyncio.fixture
async def registered_client(app_client):
    """Return an httpx client with a registered user and auth token."""
    resp = await app_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "TestPass123!",
        },
    )
    assert resp.status_code == 200, f"Registration failed: {resp.text}"
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return app_client, headers, token


# --- Mock Letta client ---


@pytest.fixture
def mock_letta_client():
    """Provide a mocked Letta client that returns plausible values."""
    mock = MagicMock()

    mock_agent = MagicMock()
    mock_agent.id = "agent-test-123"
    mock_agent.name = "test-agent"
    mock_agent.created_at = "2026-01-01T00:00:00Z"
    mock.agents.create.return_value = mock_agent
    mock.agents.list.return_value = MagicMock(items=[])
    mock.agents.tools.attach.return_value = None
    mock.agents.delete.return_value = None
    mock.agents.update.return_value = None
    mock.agents.passages.create.return_value = None
    mock.agents.passages.search.return_value = []  # No existing passages (dedup returns False)

    # Mock message response for chat/workflow execution
    mock_message = MagicMock()
    mock_message.message_type = "assistant_message"
    mock_message.content = "Hello from agent"
    mock_response = MagicMock()
    mock_response.messages = [mock_message]
    mock_response.run_id = "run-test-123"
    mock_response.usage = MagicMock(step_count=1)
    mock.agents.messages.create.return_value = mock_response

    # Mock streaming response
    mock_stream = MagicMock()
    mock_stream.__iter__ = MagicMock(return_value=iter([mock_message]))
    mock.agents.messages.stream.return_value = mock_stream

    mock_tool = MagicMock()
    mock_tool.id = "tool-test-123"
    mock.tools.create.return_value = mock_tool
    mock.tools.list.return_value = MagicMock(items=[])
    mock.tools.update.return_value = mock_tool
    mock.tools.delete.return_value = None

    mock_model = MagicMock()
    mock_model.id = "model-test-123"
    mock_model.name = "gemma4"
    mock.models.list.return_value = MagicMock(data=[mock_model])

    return mock


# --- Admin user fixture ---


@pytest_asyncio.fixture
async def admin_client(app_client):
    """Return an httpx client with an admin user and auth token."""
    # Register first user (becomes admin automatically)
    resp = await app_client.post(
        "/api/auth/register",
        json={
            "username": "admin",
            "password": "AdminPass123!",
        },
    )
    assert resp.status_code == 200, f"Admin registration failed: {resp.text}"
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return app_client, headers, token


# --- Skill content fixture ---

SKILL_MD_CONTENT = """---
name: test-skill
description: A test skill for unit testing
---

# Test Skill

This is a test skill for unit testing.
"""
