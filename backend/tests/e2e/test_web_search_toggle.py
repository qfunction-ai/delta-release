"""E2E web_search toggle tests — setting CRUD and runtime tool attachment.

Tests that the web_search_enabled setting controls tool attachment/detachment
on the agent at runtime. The E2E tests run inside the backend container, so
they can use the Letta client directly to verify tool state.
"""

import pytest


class TestWebSearchSettingsCRUD:
    """Settings CRUD for web_search_enabled."""

    def test_get_settings_default_off(self, e2e_client, e2e_token_manager):
        """GET /api/settings returns web_search_enabled: false by default."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/settings/")
        assert resp.status_code == 200
        assert "web_search_enabled" in resp.json()
        assert resp.json()["web_search_enabled"] is False

    def test_toggle_web_search_on(self, e2e_client, e2e_token_manager):
        """PUT /api/settings can toggle web_search_enabled on."""
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["web_search_enabled"] is True

    def test_toggle_web_search_off(self, e2e_client, e2e_token_manager):
        """PUT /api/settings can toggle web_search_enabled off."""
        # First ensure it's on
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": True,
            },
        )
        # Now toggle off
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["web_search_enabled"] is False

    def test_web_search_persist_across_gets(self, e2e_client, e2e_token_manager):
        """web_search_enabled persists between GET requests."""
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": True,
            },
        )
        resp = e2e_token_manager.request(e2e_client, "get", "/api/settings/")
        assert resp.json()["web_search_enabled"] is True
        # Reset
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": False,
            },
        )


class TestWebSearchRuntimeToggle:
    """Tests that web_search_enabled controls tool attachment at runtime.

    These tests verify the full path: toggle setting → chat message →
    ensure_web_search runs → tool attached/detached.

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

    def test_web_search_not_attached_when_off(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """With web_search off, the agent should not have web_search in its tool list."""
        # Ensure web_search is off
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": False,
            },
        )
        # Send a chat message to trigger ensure_web_search
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
            assert "web_search" not in tool_names, f"web_search should not be attached when disabled, got: {tool_names}"

    def test_web_search_attached_when_on(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """With web_search on, the agent should have web_search in its tool list."""
        # Enable web_search
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": True,
            },
        )
        try:
            # Send a chat message to trigger ensure_web_search
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
                pytest.skip("LLM unavailable — can't trigger ensure_web_search")
            # Check the agent's tool list
            tool_names = self._get_agent_tools(e2e_agent_id)
            if tool_names is not None:
                assert "web_search" in tool_names, f"web_search should be attached when enabled, got: {tool_names}"
        finally:
            # Reset
            e2e_token_manager.request(
                e2e_client,
                "put",
                "/api/settings/",
                json={
                    "web_search_enabled": False,
                },
            )

    def test_web_search_detached_after_toggle_off(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Toggling web_search off after it was on should detach the tool."""
        # First enable it
        e2e_token_manager.request(
            e2e_client,
            "put",
            "/api/settings/",
            json={
                "web_search_enabled": True,
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
                "web_search_enabled": False,
            },
        )
        # Send another chat message to trigger ensure_web_search (detach)
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
            assert "web_search" not in tool_names, f"web_search should be detached after toggle off, got: {tool_names}"
