"""Integration tests for settings routes."""

import pytest


@pytest.mark.asyncio
class TestSettingsRoutes:
    async def test_get_settings(self, registered_client, mock_letta_client):
        """GET /api/settings/ returns user settings (auto-created)."""
        client, headers, _ = registered_client
        resp = await client.get("/api/settings/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_tool_creation" in data
        assert "eval_enabled" in data

    async def test_update_settings(self, registered_client, mock_letta_client):
        """PUT /api/settings/ updates user settings."""
        client, headers, _ = registered_client
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"eval_enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["eval_enabled"] is True

    async def test_update_tool_creation(self, registered_client, mock_letta_client):
        """PUT /api/settings/ updates agent_tool_creation."""
        client, headers, _ = registered_client
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"agent_tool_creation": False},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_tool_creation"] is False

    async def test_update_web_search(self, registered_client, mock_letta_client):
        """PUT /api/settings/ updates web_search_enabled."""
        client, headers, _ = registered_client
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={"web_search_enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["web_search_enabled"] is True

    async def test_exa_key_configured_when_set(self, registered_client, mock_letta_client, monkeypatch):
        """GET /api/settings/ returns exa_key_configured=True when EXA_API_KEY is set."""
        monkeypatch.setenv("EXA_API_KEY", "test-key-123")
        client, headers, _ = registered_client
        resp = await client.get("/api/settings/", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["exa_key_configured"] is True

    async def test_exa_key_configured_when_missing(self, registered_client, mock_letta_client, monkeypatch):
        """GET /api/settings/ returns exa_key_configured=False when EXA_API_KEY is absent."""
        monkeypatch.delenv("EXA_API_KEY", raising=False)
        client, headers, _ = registered_client
        resp = await client.get("/api/settings/", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["exa_key_configured"] is False
