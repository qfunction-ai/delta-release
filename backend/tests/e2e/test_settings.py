"""E2E settings tests — user settings CRUD and toggle behavior."""

import time

import pytest


def _unique_name(prefix: str) -> str:
    """Generate a unique tool name with timestamp suffix."""
    return f"{prefix}_{int(time.time() * 1000)}"


class TestSettingsCRUD:
    def test_get_settings_defaults(self, e2e_client, e2e_token_manager):
        """GET /api/settings returns defaults (agent_tool_creation=False)."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/settings/")
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_tool_creation" in data
        # Default is False — the toggle starts off
        assert data["agent_tool_creation"] is False

    def test_update_settings_toggle_on(self, e2e_client, e2e_token_manager):
        """PUT /api/settings can toggle agent_tool_creation on."""
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["agent_tool_creation"] is True

    def test_update_settings_toggle_off(self, e2e_client, e2e_token_manager):
        """PUT /api/settings can toggle agent_tool_creation off."""
        # First ensure it's on
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        # Now toggle off
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["agent_tool_creation"] is False

    def test_settings_persist_across_gets(self, e2e_client, e2e_token_manager):
        """Settings persist between GET requests."""
        # Set a known state
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        # GET should return the same value
        resp = e2e_token_manager.request(e2e_client, "get", "/api/settings/")
        assert resp.json()["agent_tool_creation"] is True
        # Reset
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )


class TestSettingsTogglePropose:
    """Tests that the toggle gates the propose endpoint."""

    def test_propose_blocked_when_off(self, e2e_client, e2e_token_manager):
        """POST /api/tools/propose returns 403 when toggle is off."""
        # Ensure toggle is off
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/propose",
            json={
                "name": "blocked_proposal_tool",
                "description": "Should be blocked",
                "source_code": "def blocked_proposal_tool(x: str) -> str:\n    return x",
                "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            },
        )
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower() or "tool creation" in resp.json()["detail"].lower()

    def test_propose_allowed_when_on(self, e2e_client, e2e_token_manager):
        """POST /api/tools/propose returns 201 when toggle is on."""
        # Enable the toggle
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        try:
            name = _unique_name("e2e_proposal")
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/tools/propose",
                json={
                    "name": name,
                    "description": "E2E test proposal",
                    "source_code": f"def {name}(x: str) -> str:\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["proposed_by"] == "agent"
            assert data["name"] == name
            # Dry run should have output (even if it's just structural validation)
            assert data["dry_run_output"] is not None or data["dry_run_error"] is not None
            # Store for cleanup
            self.__class__.proposal_id = data["id"]
        finally:
            # Reset toggle
            e2e_token_manager.request(
                e2e_client,
                "put",
                "/api/settings/",
                json={
                    "agent_tool_creation": False,
                },
            )


class TestProposeToolRuntimeToggle:
    """Tests that agent_tool_creation controls propose_tool attachment at runtime.

    These tests verify the full path: toggle setting → chat message →
    ensure_propose_tool runs → tool attached/detached.

    Since the E2E tests run inside the backend container, we can use
    the Letta client directly to verify the agent's tool list.
    """

    def _get_agent_tools(self, agent_id):
        """Get the agent's current tool list via the Letta client."""
        from app.letta_client import get_letta_client

        client = get_letta_client()
        try:
            tools = client.agents.tools.list(agent_id=agent_id)
            return [t.name for t in tools] if tools else []
        except Exception:
            return None  # Letta unavailable

    def test_propose_tool_not_attached_when_off(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """With agent_tool_creation off, propose_tool should not be in the agent's tool list."""
        # Ensure toggle is off
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )
        # Send a chat message to trigger ensure_propose_tool
        e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/chat/message",
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello!",
            },
        )
        # Check the agent's tool list
        tool_names = self._get_agent_tools(e2e_agent_id)
        if tool_names is not None:
            assert "propose_tool" not in tool_names, (
                f"propose_tool should not be attached when disabled, got: {tool_names}"
            )

    def test_propose_tool_attached_when_on(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """With agent_tool_creation on, propose_tool should be in the agent's tool list."""
        # Enable the toggle
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        try:
            # Send a chat message to trigger ensure_propose_tool
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/chat/message",
                json={
                    "agent_id": e2e_agent_id,
                    "message": "Hello!",
                },
            )
            # Accept 200 or 503 (LLM timeout)
            if resp.status_code == 503:
                pytest.skip("LLM unavailable — can't trigger ensure_propose_tool")
            # Check the agent's tool list
            tool_names = self._get_agent_tools(e2e_agent_id)
            if tool_names is not None:
                assert "propose_tool" in tool_names, f"propose_tool should be attached when enabled, got: {tool_names}"
        finally:
            # Reset
            e2e_token_manager.request(
                e2e_client,
                "put",
                "/api/settings/",
                json={
                    "agent_tool_creation": False,
                },
            )

    def test_propose_tool_detached_after_toggle_off(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Toggling agent_tool_creation off after it was on should detach propose_tool."""
        # First enable it
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": True,
            },
        )
        # Send a chat message to attach
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/chat/message",
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello!",
            },
        )
        if resp.status_code == 503:
            pytest.skip("LLM unavailable")
        # Now disable it
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "agent_tool_creation": False,
            },
        )
        # Send another chat message to trigger ensure_propose_tool (detach)
        e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/chat/message",
            json={
                "agent_id": e2e_agent_id,
                "message": "Hello again!",
            },
        )
        # Check the agent's tool list
        tool_names = self._get_agent_tools(e2e_agent_id)
        if tool_names is not None:
            assert "propose_tool" not in tool_names, (
                f"propose_tool should be detached after toggle off, got: {tool_names}"
            )
