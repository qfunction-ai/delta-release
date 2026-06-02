"""Integration tests for tool CRUD and schema generation endpoints."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
class TestToolSchemaGeneration:
    async def test_generate_schema(self, registered_client):
        """POST /api/tools/generate-schema returns a valid schema."""
        client, headers, _ = registered_client
        source = '''
def search_logs(query: str, limit: int = 10) -> str:
    """Search logs for a query."""
    return "results"
'''
        resp = await client.post(
            "/api/tools/generate-schema",
            headers=headers,
            json={
                "source_code": source,
            },
        )
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]

    async def test_generate_schema_invalid_syntax(self, registered_client):
        """Invalid Python syntax returns 400."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/tools/generate-schema",
            headers=headers,
            json={
                "source_code": "def (broken",
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestToolCreate:
    async def test_create_tool(self, registered_client, mock_letta_client):
        """Creates a tool via mocked Letta client."""
        client, headers, _ = registered_client

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "test_tool",
                    "source_code": 'def test_tool(query: str) -> str:\n    """A test tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "TestTool",
                    },
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_tool"

    async def test_reject_dangerous_code(self, registered_client):
        """Tool with dangerous code patterns is rejected."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/tools/",
            headers=headers,
            json={
                "name": "dangerous_tool",
                "source_code": "import os\ndef dangerous_tool() -> str:\n    os.system('rm -rf /')\n    return 'done'",
                "json_schema": {"type": "object", "properties": {}, "title": "DangerousTool"},
            },
        )
        assert resp.status_code == 400
        assert "dangerous" in resp.json()["detail"].lower()

    async def test_duplicate_name_rejected(self, registered_client, mock_letta_client):
        """Duplicate tool name returns 409."""
        client, headers, _ = registered_client

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            # Create first tool
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "dup_tool",
                    "source_code": 'def dup_tool() -> str:\n    """A tool."""\n    return \'ok\'',
                    "json_schema": {"type": "object", "properties": {}, "title": "DupTool"},
                },
            )
            assert resp.status_code == 201

            # Try duplicate
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "dup_tool",
                    "source_code": 'def dup_tool2() -> str:\n    """Another tool."""\n    return \'ok\'',
                    "json_schema": {"type": "object", "properties": {}, "title": "DupTool2"},
                },
            )
            assert resp.status_code == 409


@pytest.mark.asyncio
class TestToolList:
    async def test_list_tools(self, registered_client, mock_letta_client):
        """GET /api/tools/ returns list of tools."""
        client, headers, _ = registered_client

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "list_tool",
                    "source_code": 'def list_tool() -> str:\n    """A tool."""\n    return \'ok\'',
                    "json_schema": {"type": "object", "properties": {}, "title": "ListTool"},
                },
            )

        resp = await client.get("/api/tools/", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


@pytest.mark.asyncio
class TestToolUpdate:
    async def test_update_tool_name(self, registered_client, mock_letta_client):
        """PUT /api/tools/{id} updates tool name and description."""
        client, headers, _ = registered_client

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "update_tool",
                    "source_code": 'def update_tool() -> str:\n    """A tool."""\n    return \'ok\'',
                    "json_schema": {"type": "object", "properties": {}, "title": "UpdateTool"},
                },
            )
        tool_id = create_resp.json()["id"]

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.put(
                f"/api/tools/{tool_id}",
                headers=headers,
                json={
                    "name": "updated_tool",
                    "description": "Updated description",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated_tool"


@pytest.mark.asyncio
class TestToolDelete:
    async def test_delete_tool(self, registered_client, mock_letta_client):
        """DELETE /api/tools/{id} removes the tool."""
        client, headers, _ = registered_client

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "delete_tool",
                    "source_code": 'def delete_tool() -> str:\n    """A tool."""\n    return \'ok\'',
                    "json_schema": {"type": "object", "properties": {}, "title": "DeleteTool"},
                },
            )
        tool_id = create_resp.json()["id"]

        with patch("app.tools.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.delete(f"/api/tools/{tool_id}", headers=headers)
        assert resp.status_code == 204
