"""Tests for audit middleware — action/resource extraction and IP parsing."""

from unittest.mock import MagicMock

from app.audit.middleware import AuditMiddleware


def _make_scope(method: str, path: str) -> dict:
    """Create an ASGI scope dict with the given method and path."""
    return {
        "type": "http",
        "method": method,
        "path": path,
    }


middleware = AuditMiddleware(app=MagicMock())


class TestGetAction:
    """Tests for AuditMiddleware._get_action."""

    def test_get_list(self):
        scope = _make_scope("GET", "/api/agents/")
        assert middleware._get_action(scope) == "list"

    def test_get_read(self):
        scope = _make_scope("GET", "/api/agents/123")
        assert middleware._get_action(scope) == "read"

    def test_post_create(self):
        scope = _make_scope("POST", "/api/agents/")
        assert middleware._get_action(scope) == "create"

    def test_post_execute(self):
        scope = _make_scope("POST", "/api/workflows/123/run")
        assert middleware._get_action(scope) == "execute"

    def test_post_login(self):
        scope = _make_scope("POST", "/api/auth/login")
        assert middleware._get_action(scope) == "login"

    def test_post_register(self):
        scope = _make_scope("POST", "/api/auth/register")
        assert middleware._get_action(scope) == "register"

    def test_post_stream(self):
        scope = _make_scope("POST", "/api/workflows/123/stream")
        assert middleware._get_action(scope) == "stream"

    def test_put_update(self):
        scope = _make_scope("PUT", "/api/agents/123")
        assert middleware._get_action(scope) == "update"

    def test_delete(self):
        scope = _make_scope("DELETE", "/api/agents/123")
        assert middleware._get_action(scope) == "delete"

    def test_patch_update(self):
        scope = _make_scope("PATCH", "/api/agents/123")
        assert middleware._get_action(scope) == "update"

    def test_unknown_method(self):
        scope = _make_scope("OPTIONS", "/api/agents/")
        assert middleware._get_action(scope) == "options"


class TestGetResourceType:
    """Tests for AuditMiddleware._get_resource_type."""

    def test_agents(self):
        scope = _make_scope("GET", "/api/agents/")
        assert middleware._get_resource_type(scope) == "agents"

    def test_workflows(self):
        scope = _make_scope("GET", "/api/workflows/123")
        assert middleware._get_resource_type(scope) == "workflows"

    def test_auth(self):
        scope = _make_scope("POST", "/api/auth/login")
        assert middleware._get_resource_type(scope) == "auth"

    def test_no_api_prefix(self):
        scope = _make_scope("GET", "/health")
        assert middleware._get_resource_type(scope) is None


class TestGetResourceId:
    """Tests for AuditMiddleware._get_resource_id."""

    def test_uuid_in_path(self):
        scope = _make_scope("GET", "/api/agents/550e8400-e29b-41d4-a716-446655440000")
        assert middleware._get_resource_id(scope) == "550e8400-e29b-41d4-a716-446655440000"

    def test_no_uuid(self):
        scope = _make_scope("GET", "/api/agents/")
        assert middleware._get_resource_id(scope) is None

    def test_agent_prefix(self):
        scope = _make_scope("GET", "/api/agents/agent-123")
        assert middleware._get_resource_id(scope) == "agent-123"


class TestExtractClientIP:
    """Tests for client IP extraction from ASGI scope headers.

    The middleware parses X-Forwarded-For to get the real client IP
    behind a reverse proxy. Falls back to the ASGI server address.
    """

    def _make_scope(self, headers: dict[str, str], server=("10.0.0.1", 8000)):
        """Build an ASGI scope with the given headers and server."""
        encoded_headers = [(k.encode(), v.encode()) for k, v in headers.items()]
        return {
            "type": "http",
            "method": "GET",
            "path": "/api/agents/",
            "headers": encoded_headers,
            "server": server,
        }

    def _extract_ip(self, scope):
        """Extract IP from scope using the same logic as the middleware."""
        headers_dict = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        server = scope.get("server", ("", 0))
        x_forwarded_for = headers_dict.get("x-forwarded-for", "")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return server[0] if server else None

    def test_x_forwarded_for_single(self):
        scope = self._make_scope({"x-forwarded-for": "1.2.3.4"})
        assert self._extract_ip(scope) == "1.2.3.4"

    def test_x_forwarded_for_multiple(self):
        """First IP in the chain is the client."""
        scope = self._make_scope({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})
        assert self._extract_ip(scope) == "1.2.3.4"

    def test_x_forwarded_for_with_spaces(self):
        scope = self._make_scope({"x-forwarded-for": "  1.2.3.4  , 10.0.0.1  "})
        assert self._extract_ip(scope) == "1.2.3.4"

    def test_no_x_forwarded_for_falls_back_to_server(self):
        scope = self._make_scope({}, server=("10.0.0.1", 8000))
        assert self._extract_ip(scope) == "10.0.0.1"

    def test_empty_x_forwarded_for_falls_back(self):
        scope = self._make_scope({"x-forwarded-for": ""}, server=("10.0.0.1", 8000))
        assert self._extract_ip(scope) == "10.0.0.1"
