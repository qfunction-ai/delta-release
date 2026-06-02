"""E2E service token tests — verify X-Service-Token enforcement.

Service-to-service endpoints use X-Service-Token instead of user JWTs.
These tests verify that missing or invalid tokens are rejected.
"""


class TestProposeAgentServiceToken:
    """POST /api/tools/propose/agent — service token enforcement."""

    def test_rejects_missing_token(self, e2e_client):
        """POST /api/tools/propose/agent without X-Service-Token returns 403."""
        resp = e2e_client.post(
            "/api/tools/propose/agent",
            json={
                "agent_id": "fake-agent-id",
                "name": "st_test",
                "description": "Should be rejected",
                "source_code": "def st_test(x: str) -> str: return x",
                "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            },
        )
        assert resp.status_code == 403

    def test_rejects_invalid_token(self, e2e_client):
        """POST /api/tools/propose/agent with wrong X-Service-Token returns 403."""
        resp = e2e_client.post(
            "/api/tools/propose/agent",
            json={
                "agent_id": "fake-agent-id",
                "name": "st_test",
                "description": "Should be rejected",
                "source_code": "def st_test(x: str) -> str: return x",
                "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            },
            headers={"X-Service-Token": "invalid-token-value"},
        )
        assert resp.status_code == 403

    def test_accepts_valid_token(self, e2e_client, e2e_service_token, e2e_agent_id, e2e_token_manager):
        """POST /api/tools/propose/agent with valid token does NOT return 403 for auth.

        The request may fail for other reasons (toggle off, agent not found,
        etc.) but it should NOT be a 403 with "Invalid or missing service
        token" — that proves the token was accepted.
        """
        # Enable the toggle so the proposal can go through
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        try:
            resp = e2e_client.post(
                "/api/tools/propose/agent",
                json={
                    "agent_id": e2e_agent_id,
                    "name": "st_valid_test",
                    "description": "Token should be accepted",
                    "source_code": "def st_valid_test(x: str) -> str: return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
                headers={"X-Service-Token": e2e_service_token},
            )
            # 403 with "service token" in the detail means auth failed
            if resp.status_code == 403:
                detail = resp.json().get("detail", "").lower()
                assert "service token" not in detail, f"Token was rejected: {resp.text}"
            # Any other status (201, 400, 404, 409, 503) means auth passed
        finally:
            # Disable the toggle
            e2e_token_manager.request(
                e2e_client,
                "put",
                "/api/settings/",
                json={
                    "agent_tool_creation": False,
                },
            )


class TestEvalChatServiceToken:
    """POST /api/chat/eval — service token enforcement."""

    def test_rejects_missing_token(self, e2e_client):
        """POST /api/chat/eval without X-Service-Token returns 403."""
        resp = e2e_client.post(
            "/api/chat/eval",
            json={
                "agent_id": "fake-agent",
                "message": "hello",
            },
        )
        assert resp.status_code == 403

    def test_rejects_invalid_token(self, e2e_client):
        """POST /api/chat/eval with wrong X-Service-Token returns 403."""
        resp = e2e_client.post(
            "/api/chat/eval",
            json={
                "agent_id": "fake-agent",
                "message": "hello",
            },
            headers={"X-Service-Token": "wrong-token"},
        )
        assert resp.status_code == 403


class TestSettingsEvalServiceToken:
    """PUT /api/settings/eval — service token enforcement."""

    def test_rejects_missing_token(self, e2e_client):
        """PUT /api/settings/eval without X-Service-Token returns 403."""
        resp = e2e_client.put(
            "/api/settings/eval?agent_id=fake-agent",
            json={
                "agent_tool_creation": True,
            },
        )
        assert resp.status_code == 403

    def test_rejects_invalid_token(self, e2e_client):
        """PUT /api/settings/eval with wrong X-Service-Token returns 403."""
        resp = e2e_client.put(
            "/api/settings/eval?agent_id=fake-agent",
            json={
                "agent_tool_creation": True,
            },
            headers={"X-Service-Token": "bad-token"},
        )
        assert resp.status_code == 403
