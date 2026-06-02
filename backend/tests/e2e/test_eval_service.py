"""E2E eval service tests — service-to-service endpoints and backend routing."""

import time


class TestEvalServiceEndpoints:
    """Tests for the service-to-service eval chat and settings endpoints."""

    def _get_service_token(self):
        """Get the real service token for E2E tests.

        Uses the saved real token from the unit conftest (before it was
        overridden), falling back to the shared config file.
        """
        from tests.conftest import _REAL_SERVICE_TOKEN

        if _REAL_SERVICE_TOKEN:
            return _REAL_SERVICE_TOKEN
        try:
            with open("/data/config/service_token") as f:
                return f.read().strip()
        except (OSError, FileNotFoundError):
            return ""

    def test_eval_chat_requires_service_token(self, e2e_client):
        """POST /api/chat/eval returns 403 without service token."""
        resp = e2e_client.post(
            "/api/chat/eval",
            json={
                "agent_id": "fake-agent",
                "message": "hello",
            },
        )
        assert resp.status_code == 403

    def test_eval_chat_with_bad_token(self, e2e_client):
        """POST /api/chat/eval returns 403 with invalid service token."""
        resp = e2e_client.post(
            "/api/chat/eval",
            json={
                "agent_id": "fake-agent",
                "message": "hello",
            },
            headers={"X-Service-Token": "invalid-token"},
        )
        assert resp.status_code == 403

    def test_eval_chat_with_valid_token(self, e2e_client, e2e_agent_id, e2e_token_manager):
        """POST /api/chat/eval with valid token and real agent returns 200 or 503."""
        token = self._get_service_token()
        if not token:
            return  # Can't test without service token

        # Enable eval for the user first (eval chat requires eval_enabled=True)
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "eval_enabled": True,
            },
        )

        resp = e2e_client.post(
            "/api/chat/eval",
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello from eval test",
            },
            headers={"X-Service-Token": token},
        )
        # Accept 200 (success), 404 (agent not found), or 503 (Letta unavailable)
        assert resp.status_code in (200, 404, 503), f"Unexpected: {resp.status_code} {resp.text[:200]}"

    def test_eval_settings_requires_service_token(self, e2e_client):
        """PUT /api/settings/eval returns 403 without service token."""
        resp = e2e_client.put(
            "/api/settings/eval?agent_id=fake-agent",
            json={
                "agent_tool_creation": True,
            },
        )
        assert resp.status_code == 403

    def test_eval_settings_with_valid_token(self, e2e_client, e2e_agent_id):
        """PUT /api/settings/eval can configure settings via agent_id."""
        token = self._get_service_token()
        if not token:
            return  # Can't test without service token

        # Set toggle on
        resp = e2e_client.put(
            "/api/settings/eval?agent_id=" + e2e_agent_id,
            json={
                "agent_tool_creation": True,
            },
            headers={"X-Service-Token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_tool_creation"] is True

        # Verify the setting persisted (via normal user endpoint)
        # The user's setting should now be True
        from .conftest import _TEST_PASSWORD, _TEST_USERNAME

        login_resp = e2e_client.post(
            "/api/auth/login",
            json={
                "username": _TEST_USERNAME,
                "password": _TEST_PASSWORD,
            },
        )
        if login_resp.status_code == 200:
            user_token = login_resp.json()["access_token"]
            settings_resp = e2e_client.get("/api/settings/", headers={"Authorization": f"Bearer {user_token}"})
            if settings_resp.status_code == 200:
                assert settings_resp.json()["agent_tool_creation"] is True

        # Reset toggle off
        resp = e2e_client.put(
            "/api/settings/eval?agent_id=" + e2e_agent_id,
            json={
                "agent_tool_creation": False,
            },
            headers={"X-Service-Token": token},
        )
        assert resp.status_code == 200


class TestEvalBackendRouting:
    """Tests for eval scenarios with backend routing enabled."""

    def test_scenario_with_route_through_backend(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create a scenario with route_through_backend=true and settings."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/evals/scenarios",
            json={
                "name": f"e2e_backend_routed_{int(time.time() * 1000)}",
                "description": "Test backend routing",
                "agent_id": e2e_agent_id,
                "definition": {
                    "interactions": [{"input": "Hello"}],
                    "checks": [
                        {
                            "type": "StringMatching",
                            "name": "contains_word",
                            "keyword": "hello",
                        }
                    ],
                    "route_through_backend": True,
                    "settings": {"agent_tool_creation": False},
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        # The scenario definition should preserve route_through_backend
        definition = data.get("definition", {})
        assert definition.get("route_through_backend") is True
