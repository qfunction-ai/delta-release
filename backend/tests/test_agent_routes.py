"""Integration tests for agent CRUD endpoints (with mocked Letta client)."""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.routes import _derive_provider_type


def test_derive_provider_type():
    """_derive_provider_type must return valid Letta ProviderType enum values."""
    # Ollama returns its own provider type (needed for OllamaModelSettings with strict=false)
    assert _derive_provider_type("ollama/gemma4:latest") == "ollama"
    assert _derive_provider_type("ollama/llama3:latest") == "ollama"
    # Letta's own models also use OpenAI-compatible API
    assert _derive_provider_type("letta/letta-free") == "openai"
    # Direct OpenAI
    assert _derive_provider_type("openai/gpt-4o") == "openai"
    # Anthropic
    assert _derive_provider_type("anthropic/claude-3-opus") == "anthropic"
    # Google
    assert _derive_provider_type("google_ai/gemini-pro") == "google_ai"
    assert _derive_provider_type("google_vertex/gemini-pro") == "google_vertex"
    # Azure
    assert _derive_provider_type("azure/gpt-4o") == "azure"
    # Groq
    assert _derive_provider_type("groq/llama3") == "groq"
    # xAI
    assert _derive_provider_type("xai/grok") == "xai"
    # Unknown prefix defaults to openai
    assert _derive_provider_type("local/some-model") == "openai"
    assert _derive_provider_type("custom/model") == "openai"


@pytest.mark.asyncio
class TestAgentList:
    async def test_empty_list(self, registered_client):
        """Returns empty list for new user."""
        client, headers, _ = registered_client
        resp = await client.get("/api/agents/", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
class TestAgentCreate:
    async def test_create_agent(self, registered_client, mock_letta_client):
        """Creates an agent via mocked Letta client."""
        client, headers, _ = registered_client

        # Mock the Letta models endpoint
        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_model.name = "gemma4"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "test-agent",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-agent"
        assert "letta_agent_id" in data


@pytest.mark.asyncio
class TestAgentOwnership:
    async def test_agent_visible_to_owner(self, registered_client, mock_letta_client):
        """Agent is visible to the user who created it."""
        client, headers, _ = registered_client

        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "my-agent",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )

        assert resp.status_code == 201
        agent_id = resp.json()["id"]

        # Should be visible in list
        resp = await client.get("/api/agents/", headers=headers)
        agents = resp.json()
        assert any(a["id"] == agent_id for a in agents)


@pytest.mark.asyncio
class TestAgentUpdate:
    async def test_update_agent_name(self, registered_client, mock_letta_client):
        """PUT /api/agents/{id} updates the agent name."""
        client, headers, _ = registered_client

        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "original-name",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )
        agent_id = create_resp.json()["id"]

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.put(
                f"/api/agents/{agent_id}",
                headers=headers,
                json={
                    "name": "updated-name",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated-name"

    async def test_update_agent_noop(self, registered_client, mock_letta_client):
        """PUT with same name is a no-op (still 200)."""
        client, headers, _ = registered_client

        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "same-name",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )
        agent_id = create_resp.json()["id"]

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.put(
                f"/api/agents/{agent_id}",
                headers=headers,
                json={
                    "name": "same-name",
                },
            )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAgentDelete:
    async def test_delete_agent(self, registered_client, mock_letta_client):
        """DELETE /api/agents/{id} removes the agent."""
        client, headers, _ = registered_client

        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "to-delete",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )
        agent_id = create_resp.json()["id"]

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.delete(f"/api/agents/{agent_id}", headers=headers)
        assert resp.status_code == 204

        # Verify it's gone from the list
        resp = await client.get("/api/agents/", headers=headers)
        assert not any(a["id"] == agent_id for a in resp.json())
