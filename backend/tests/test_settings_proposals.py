"""Tests for user settings and tool proposal flow."""

import pytest

from app.settings.schemas import UserSettingsResponse, UserSettingsUpdate
from app.tools.schemas import ToolProposeRequest


class TestUserSettingsSchemas:
    """Test settings schema validation."""

    def test_default_response(self):
        resp = UserSettingsResponse()
        assert resp.agent_tool_creation is False

    def test_update_partial(self):
        update = UserSettingsUpdate()
        assert update.agent_tool_creation is None

    def test_update_toggle_on(self):
        update = UserSettingsUpdate(agent_tool_creation=True)
        assert update.agent_tool_creation is True


class TestToolProposeRequest:
    """Test tool proposal request schema validation."""

    def test_valid_proposal(self):
        req = ToolProposeRequest(
            name="query_splunk",
            description="Search Splunk",
            source_code="def query_splunk(q: str) -> str:\n    return q",
            json_schema={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        )
        assert req.name == "query_splunk"
        assert req.pip_requirements is None

    def test_invalid_name(self):
        with pytest.raises(ValueError):
            ToolProposeRequest(
                name="QuerySplunk",
                description="Search",
                source_code="def f(): pass",
                json_schema={"type": "object"},
            )

    def test_empty_source_code(self):
        with pytest.raises(ValueError):
            ToolProposeRequest(
                name="test",
                description="Test",
                source_code="",
                json_schema={"type": "object"},
            )

    def test_no_function_def(self):
        with pytest.raises(ValueError):
            ToolProposeRequest(
                name="test",
                description="Test",
                source_code="x = 1",
                json_schema={"type": "object"},
            )

    def test_with_pip_requirements(self):
        req = ToolProposeRequest(
            name="fetch_data",
            description="Fetch data from API",
            source_code="def fetch_data(url: str) -> str:\n    return url",
            json_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            pip_requirements=["httpx", "requests"],
        )
        assert req.pip_requirements == ["httpx", "requests"]


class TestSettingsRoutes:
    """Tests for settings routes."""

    @pytest.mark.asyncio
    async def test_get_settings_auto_creates(self, registered_client, mock_letta_client):
        """First access to settings creates default values."""
        client, headers, _ = registered_client

        resp = await client.get("/api/settings/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_tool_creation"] is False
        assert data["eval_enabled"] is False
        assert data["web_search_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_settings_agent_tool_creation(self, registered_client, mock_letta_client):
        """PUT /api/settings/ toggles agent_tool_creation."""
        client, headers, _ = registered_client

        # First get settings to ensure they exist
        await client.get("/api/settings/", headers=headers)

        # Update agent_tool_creation
        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={
                "agent_tool_creation": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_tool_creation"] is True

        # Verify persistence
        resp = await client.get("/api/settings/", headers=headers)
        assert resp.json()["agent_tool_creation"] is True

    @pytest.mark.asyncio
    async def test_update_settings_eval_enabled(self, registered_client, mock_letta_client):
        """PUT /api/settings/ toggles eval_enabled."""
        client, headers, _ = registered_client

        await client.get("/api/settings/", headers=headers)

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={
                "eval_enabled": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["eval_enabled"] is True

    @pytest.mark.asyncio
    async def test_update_settings_web_search_enabled(self, registered_client, mock_letta_client):
        """PUT /api/settings/ toggles web_search_enabled."""
        client, headers, _ = registered_client

        await client.get("/api/settings/", headers=headers)

        resp = await client.put(
            "/api/settings/",
            headers=headers,
            json={
                "web_search_enabled": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["web_search_enabled"] is True

    @pytest.mark.asyncio
    async def test_eval_update_settings_requires_service_token(self, registered_client, mock_letta_client, app_client):
        """PUT /api/settings/eval requires X-Service-Token."""
        client, headers, _ = registered_client

        # No service token
        resp = await client.put(
            "/api/settings/eval?agent_id=test",
            headers=headers,
            json={
                "eval_enabled": True,
            },
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_eval_update_settings_requires_agent_id(self, registered_client, mock_letta_client, app_client):
        """PUT /api/settings/eval requires agent_id query param."""
        client, headers, _ = registered_client

        # Override the service token dependency via the test app
        from app.auth.dependencies import verify_service_token

        test_app = app_client._transport.app  # Access the FastAPI app from the ASGI transport
        test_app.dependency_overrides[verify_service_token] = lambda: None

        try:
            # Missing agent_id
            resp = await client.put(
                "/api/settings/eval",
                headers={
                    "X-Service-Token": "any-token",
                },
                json={
                    "eval_enabled": True,
                },
            )
            assert resp.status_code == 400
        finally:
            test_app.dependency_overrides.pop(verify_service_token, None)

    @pytest.mark.asyncio
    async def test_eval_update_settings_allows_all_toggles(self, registered_client, mock_letta_client, app_client):
        """PUT /api/settings/eval accepts agent_tool_creation and web_search_enabled."""
        client, headers, _ = registered_client

        # First, create an agent to use for the eval endpoint
        from unittest.mock import patch

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            agent_resp = await client.post(
                "/api/agents/",
                json={
                    "name": "eval-test-agent",
                    "model": "gemma4",
                    "embedding": "embeddinggemma",
                },
                headers=headers,
            )
        agent_id = agent_resp.json()["letta_agent_id"]

        # Override the service token dependency via the test app
        from app.auth.dependencies import verify_service_token

        test_app = client._transport.app
        test_app.dependency_overrides[verify_service_token] = lambda: None

        try:
            # Set all three toggles via eval endpoint
            resp = await client.put(
                f"/api/settings/eval?agent_id={agent_id}",
                headers={
                    "X-Service-Token": "any-token",
                },
                json={
                    "eval_enabled": True,
                    "agent_tool_creation": True,
                    "web_search_enabled": True,
                },
            )
        finally:
            test_app.dependency_overrides.pop(verify_service_token, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["eval_enabled"] is True
        assert data["agent_tool_creation"] is True
        assert data["web_search_enabled"] is True

        # Verify settings persisted
        settings_resp = await client.get("/api/settings/", headers=headers)
        assert settings_resp.json()["agent_tool_creation"] is True
        assert settings_resp.json()["web_search_enabled"] is True
