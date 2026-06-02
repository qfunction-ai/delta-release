"""E2E test fixtures — requires Docker Compose running."""

import os
from datetime import datetime, timedelta, timezone

import httpx
import jwt as pyjwt
import pytest

# Gate E2E tests behind an env var so they don't accidentally run in CI
# without the Docker stack
pytestmark = pytest.mark.skipif(
    os.getenv("DELTA_E2E") != "1",
    reason="E2E tests require DELTA_E2E=1 and a running Docker Compose stack",
)

BASE_URL = os.getenv("DELTA_E2E_URL", "http://localhost:8000")

# Credentials for the E2E test user
_TEST_USERNAME = "e2e_test_user"
_TEST_PASSWORD = "E2eTestPass123!"


def _get_jwt_config() -> tuple[str, str]:
    """Read JWT secret and algorithm from the running backend's settings.

    The unit test conftest (tests/conftest.py) sets DELTA_JWT_SECRET as an
    env var to a test-only value, overriding the container's real secret.
    We need the real secret that the live backend is using so that forged
    JWT tokens are accepted.

    Resolution order:
    1. /proc/1/environ (Linux containers — the backend process's initial env)
    2. Project .env file (local dev on macOS — read directly before settings)
    3. Settings fallback (clears the unit-test override and re-reads)
    """
    _jwt_secret = None

    # 1. Read from /proc/1/environ — the backend process's initial environment
    try:
        with open("/proc/1/environ", "r") as f:
            for entry in f.read().split("\0"):
                if entry.startswith("DELTA_JWT_SECRET="):
                    _jwt_secret = entry.split("=", 1)[1].strip()
                    break
    except (OSError, FileNotFoundError, PermissionError):
        pass

    # 2. Read from project .env file (local dev on macOS where /proc doesn't exist)
    if not _jwt_secret:
        from pathlib import Path

        env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("JWT_SECRET=") and not line.startswith("#"):
                    _jwt_secret = line.split("=", 1)[1].strip()
                    break

    # 3. Fallback: clear the unit test override and re-read settings
    if not _jwt_secret:
        from app.config import get_settings

        get_settings.cache_clear()
        _saved = os.environ.pop("DELTA_JWT_SECRET", None)
        try:
            settings = get_settings()
            _jwt_secret = settings.jwt_secret
        finally:
            if _saved is not None:
                os.environ["DELTA_JWT_SECRET"] = _saved

    return _jwt_secret, "HS256"


_JWT_SECRET, _JWT_ALGORITHM = _get_jwt_config()

# Minimal tool source code for E2E tests
_TOOL_SOURCE = '''def e2e_test_tool(query: str) -> str:
    """A simple test tool.

    Args:
        query: The search query.

    Returns:
        The query string echoed back.
    """
    return query
'''

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query."},
    },
    "required": ["query"],
    "title": "E2eTestTool",
}

# Minimal skill content for E2E tests (must have YAML frontmatter)
_SKILL_CONTENT = """---
name: e2e_test_skill
---

# E2E Test Skill

## Purpose
A test skill for E2E testing.

## Steps
1. Receive the query
2. Process it
3. Return results
"""


def forge_jwt(user_id: str, role: str = "user", token_version: int = 1) -> str:
    """Create a JWT with arbitrary claims using the known CI secret.

    Used for IDOR and admin-enforcement tests: forge a token with a
    different user_id or role to verify that the backend rejects
    cross-user or non-admin access.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _get_service_token() -> str:
    """Read the real service token for E2E tests.

    The unit-test conftest overrides DELTA_SERVICE_TOKEN with a fake value
    for SQLite-based unit tests.  It also saves the original value in
    _REAL_SERVICE_TOKEN before overriding.  We use that saved value so
    E2E tests send the correct token to the live backend.

    Resolution order:
    1. _REAL_SERVICE_TOKEN from the unit-test conftest (if set before override)
    2. Shared config volume inside the container (/data/config/service_token)
    3. Project .env file (local dev on macOS where container paths don't exist)
    4. DELTA_SERVICE_TOKEN env var (may be the overridden fake value)
    """
    from tests.conftest import _REAL_SERVICE_TOKEN

    if _REAL_SERVICE_TOKEN and _REAL_SERVICE_TOKEN != "test-service-token":
        return _REAL_SERVICE_TOKEN
    try:
        with open("/data/config/service_token") as f:
            token = f.read().strip()
        if token:
            return token
    except (OSError, FileNotFoundError):
        pass
    # Read from project .env file (local dev on macOS)
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("SERVICE_TOKEN=") and not line.startswith("#"):
                token = line.split("=", 1)[1].strip()
                if token:
                    return token
    return os.getenv("DELTA_SERVICE_TOKEN", "")


def _register_or_login(client):
    """Register the first user or log in. Returns an access token."""
    # Try login first (common case after first run)
    resp = client.post(
        "/api/auth/login",
        json={
            "username": _TEST_USERNAME,
            "password": _TEST_PASSWORD,
        },
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]

    # If login fails, try registration (first-user-only)
    resp = client.post(
        "/api/auth/register",
        json={
            "username": _TEST_USERNAME,
            "password": _TEST_PASSWORD,
        },
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]

    # Registration taken — another user exists. Try common fallback.
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "Admin123!@#",
        },
    )
    if resp.status_code == 200:
        return resp.json()["access_token"]

    raise RuntimeError(f"Cannot authenticate for E2E tests: last response {resp.status_code} {resp.text}")


@pytest.fixture(scope="session")
def e2e_client():
    """Synchronous httpx client for E2E tests against the live backend."""
    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        yield client


class _TokenManager:
    """Manages the session token, auto-refreshing on 401.

    Handles the case where logout-everywhere or password-change tests
    invalidate the session token.
    """

    def __init__(self, client):
        self._client = client
        self._token = _register_or_login(client)
        self._username = _TEST_USERNAME
        self._password = _TEST_PASSWORD

    def get_fresh_token(self):
        """Force a fresh login and return the new token."""
        resp = self._client.post(
            "/api/auth/login",
            json={
                "username": self._username,
                "password": self._password,
            },
        )
        if resp.status_code == 200:
            self._token = resp.json()["access_token"]
            return self._token

        # Fallback to admin
        resp = self._client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "Admin123!@#",
            },
        )
        if resp.status_code == 200:
            self._token = resp.json()["access_token"]
            self._username = "admin"
            self._password = "Admin123!@#"
            return self._token

        raise RuntimeError(f"Cannot refresh E2E token: {resp.status_code} {resp.text}")

    def headers(self):
        """Return auth headers dict with the current token."""
        return {"Authorization": f"Bearer {self._token}"}

    def refresh_if_401(self, resp):
        """If response is 401, refresh the token. Returns True if refreshed."""
        if resp.status_code == 401:
            self.get_fresh_token()
            return True
        return False

    def request(self, client, method, url, **kwargs):
        """Make an authenticated request, auto-refreshing on 401.

        Convenience method that handles token staleness transparently.
        """
        headers = kwargs.pop("headers", {})
        headers.update(self.headers())
        resp = getattr(client, method)(url, headers=headers, **kwargs)
        if resp.status_code == 401 and self.refresh_if_401(resp):
            headers.update(self.headers())
            resp = getattr(client, method)(url, headers=headers, **kwargs)
        return resp


@pytest.fixture(scope="session")
def e2e_token_manager(e2e_client):
    """Return a token manager for E2E tests (session-scoped, auto-refreshes)."""
    return _TokenManager(e2e_client)


@pytest.fixture(scope="session")
def e2e_token(e2e_token_manager):
    """Return an auth token string (session-scoped). May be stale after logout-everywhere."""
    return e2e_token_manager._token


@pytest.fixture
def e2e_headers(e2e_token_manager):
    """Auth headers for E2E tests. Uses the current session token."""
    return e2e_token_manager.headers()


@pytest.fixture(scope="session")
def e2e_agent_id(e2e_client, e2e_token_manager):
    """Create an agent for E2E tests and return its letta_agent_id."""
    resp = e2e_token_manager.request(
        e2e_client,
        "post",
        "/api/agents/",
        json={
            "name": "e2e-pipeline-agent",
            "model": "ollama/gemma4:latest",
            "embedding": "ollama/embeddinggemma:latest",
        },
    )
    assert resp.status_code == 201, f"Agent creation failed: {resp.text}"
    return resp.json()["letta_agent_id"]


@pytest.fixture(scope="session")
def e2e_tool_id(e2e_client, e2e_token_manager):
    """Create a tool for E2E tests and return its id — idempotent on re-run."""
    resp = e2e_token_manager.request(
        e2e_client,
        "post",
        "/api/tools/",
        json={
            "name": "e2e_test_tool",
            "description": "A simple test tool for E2E testing",
            "source_code": _TOOL_SOURCE,
            "json_schema": _TOOL_SCHEMA,
            "tags": ["e2e", "test"],
        },
    )
    if resp.status_code == 201:
        return resp.json()["id"]
    # 409 means it already exists — look it up
    if resp.status_code == 409:
        resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
        for tool in resp.json():
            if tool["name"] == "e2e_test_tool":
                return tool["id"]
    raise RuntimeError(f"Tool creation failed: {resp.text}")


@pytest.fixture(scope="session")
def e2e_skill_id(e2e_client, e2e_token_manager):
    """Create a skill for E2E tests and return its id — idempotent on re-run."""
    resp = e2e_token_manager.request(
        e2e_client,
        "post",
        "/api/skills/",
        json={
            "name": "e2e_test_skill",
            "description": "A test skill for E2E testing",
            "content": _SKILL_CONTENT,
        },
    )
    if resp.status_code == 201:
        return resp.json()["id"]
    # 409 means it already exists — look it up
    if resp.status_code == 409:
        resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
        for skill in resp.json():
            if skill["name"] == "e2e_test_skill":
                return skill["id"]
    raise RuntimeError(f"Skill creation failed: {resp.text}")


@pytest.fixture(scope="session")
def e2e_service_token():
    """Return the service token for internal service auth."""
    token = _get_service_token()
    if not token:
        pytest.skip("Service token not available")
    return token


@pytest.fixture(scope="session")
def e2e_second_user_id(e2e_client, e2e_token_manager):
    """Create a second (non-admin) user and return their user_id.

    The first registered user is admin. We need a second non-admin user
    for IDOR and admin-enforcement tests. Since registration is closed
    after the first user, we create this user via direct DB access.

    Depends on e2e_token_manager to ensure the primary test user is
    registered first (registration closes after the first user).

    Returns the user_id as a string.
    """
    import psycopg2

    # Read DB URL from the backend's settings
    from app.config import get_settings

    settings = get_settings()
    db_url = settings.database_url

    # Convert async URL to sync URL (replace asyncpg with psycopg2)
    sync_url = db_url.replace("+asyncpg", "").replace("postgresql://", "postgresql://")

    conn = psycopg2.connect(sync_url)
    try:
        with conn.cursor() as cur:
            # Check if the user already exists
            cur.execute("SELECT id FROM users WHERE username = 'e2e_second_user'")
            row = cur.fetchone()
            if row:
                return str(row[0])

            # Create the second user
            import uuid as _uuid

            from app.auth.security import hash_password

            pw_hash = hash_password("E2eSecondPass123!")
            new_id = str(_uuid.uuid4())
            from datetime import datetime as _dt
            from datetime import timezone as _tz

            now = _dt.now(_tz.utc)
            cur.execute(
                "INSERT INTO users (id, username, password_hash, role, must_change_password, token_version, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (new_id, "e2e_second_user", pw_hash, "user", False, 1, now),
            )
            user_id = cur.fetchone()[0]
            conn.commit()
            return str(user_id)
    finally:
        conn.close()


@pytest.fixture
def e2e_forged_user_headers(e2e_second_user_id):
    """Auth headers for a real second user (non-admin, non-owner).

    Used for IDOR tests: the token is valid (signed with the real secret)
    and references a real user in the DB, but that user doesn't own the
    target resources. This tests the get_owned_or_404 ownership check.
    """
    second_token = forge_jwt(e2e_second_user_id, role="user")
    return {"Authorization": f"Bearer {second_token}"}


@pytest.fixture
def e2e_non_admin_headers(e2e_second_user_id):
    """Auth headers for a real non-admin user.

    Used for admin-only endpoint tests. The user exists in the DB
    but has role='user' instead of 'admin'.
    """
    non_admin_token = forge_jwt(e2e_second_user_id, role="user")
    return {"Authorization": f"Bearer {non_admin_token}"}
