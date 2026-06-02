"""E2E security header tests — verify response headers and error sanitization.

Tests that security headers are present on all responses and that
500 errors don't leak stack traces.
"""


class TestSecurityHeaders:
    """Verify security headers are set on all responses."""

    def test_x_content_type_options(self, e2e_client):
        """All responses include X-Content-Type-Options: nosniff."""
        resp = e2e_client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff", (
            f"Missing X-Content-Type-Options: {dict(resp.headers)}"
        )

    def test_x_frame_options(self, e2e_client):
        """All responses include X-Frame-Options: DENY."""
        resp = e2e_client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY", f"Missing X-Frame-Options: {dict(resp.headers)}"

    def test_referrer_policy(self, e2e_client):
        """All responses include Referrer-Policy header."""
        resp = e2e_client.get("/health")
        assert "referrer-policy" in resp.headers, f"Missing Referrer-Policy: {dict(resp.headers)}"

    def test_permissions_policy(self, e2e_client):
        """All responses include Permissions-Policy header."""
        resp = e2e_client.get("/health")
        assert "permissions-policy" in resp.headers, f"Missing Permissions-Policy: {dict(resp.headers)}"


class TestErrorSanitization:
    """Verify error responses don't leak internal details."""

    def test_500_no_stack_trace(self, e2e_client):
        """500 errors return a generic message without stack traces."""
        # Send malformed JSON to trigger a 500 or 422
        resp = e2e_client.post(
            "/api/auth/login",
            content=b"{invalid json",
            headers={
                "Content-Type": "application/json",
            },
        )
        # Either 422 (malformed JSON) or 500 (if the parser chokes)
        body = resp.text.lower()
        # Should NOT contain Python traceback patterns
        assert "traceback" not in body, f"Stack trace leaked in error: {resp.text[:200]}"
        assert "file " not in body or "file not found" in body, f"File path leaked in error: {resp.text[:200]}"
        assert '.py"' not in body, f"Python file path leaked: {resp.text[:200]}"

    def test_401_no_internal_details(self, e2e_client):
        """401 responses don't leak internal auth details.

        Uses a fresh client to avoid cookie leakage from the session-scoped
        e2e_client.
        """
        import httpx

        with httpx.Client(base_url=e2e_client.base_url, timeout=e2e_client.timeout) as fresh:
            resp = fresh.get("/api/agents/")
            assert resp.status_code in (401, 403)
            body = resp.json()
            # Should be a generic message, not internal details
            assert "detail" in body
            detail = body["detail"].lower()
            # Should NOT contain DB query details, user IDs, etc.
            assert "select" not in detail
            assert "sqlalchemy" not in detail
