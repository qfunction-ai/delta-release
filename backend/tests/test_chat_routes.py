"""Tests for chat routes — history and message endpoints."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
class TestChatHistory:
    """Integration tests for chat history endpoint."""

    async def test_get_chat_history_no_agent(self, registered_client, mock_letta_client):
        """GET /api/chat/history/{agent_id} returns 404 for nonexistent agent."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/chat/history/nonexistent-agent-id",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_get_chat_history_with_agent(self, registered_client, mock_letta_client):
        """GET /api/chat/history/{agent_id} returns chat history."""
        client, headers, _ = registered_client

        # Create an agent first
        mock_model = MagicMock()
        mock_model.id = "ollama/gemma4:latest"
        mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])
        mock_letta_client.agents.create.return_value = MagicMock(
            id="chat-agent-123", name="chat-agent", created_at="2026-01-01"
        )

        with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
            agent_resp = await client.post(
                "/api/agents/",
                headers=headers,
                json={
                    "name": "chat-agent",
                    "model": "ollama/gemma4:latest",
                    "embedding": "ollama/embeddinggemma:latest",
                },
            )
        assert agent_resp.status_code == 201
        agent_id = agent_resp.json()["letta_agent_id"]

        # Mock chat history
        mock_letta_client.agents.messages.list.return_value = []
        with patch("app.chat.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.get(
                f"/api/chat/history/{agent_id}",
                headers=headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
