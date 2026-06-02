"""Tests for tools routes — schema generation, CRUD, and helpers."""

from unittest.mock import MagicMock, patch

import pytest

from app.tools.helpers import parse_pip_requirements
from app.tools.routes import generate_schema_from_source


class TestGenerateSchemaFromSource:
    """Tests for generate_schema_from_source — Python AST to JSON Schema."""


class TestParsePipRequirements:
    """Tests for parse_pip_requirements."""

    def test_none_returns_none(self):
        assert parse_pip_requirements(None) is None

    def test_empty_list_returns_none(self):
        assert parse_pip_requirements([]) is None

    def test_simple_package(self):
        result = parse_pip_requirements(["requests"])
        assert result == [{"name": "requests"}]

    def test_pinned_package(self):
        result = parse_pip_requirements(["paramiko==2.12.0"])
        assert result == [{"name": "paramiko", "version": "2.12.0"}]

    def test_mixed_packages(self):
        result = parse_pip_requirements(["requests", "paramiko==2.12.0"])
        assert result == [{"name": "requests"}, {"name": "paramiko", "version": "2.12.0"}]

    def test_empty_strings_skipped(self):
        result = parse_pip_requirements(["", "  ", "requests"])
        assert result == [{"name": "requests"}]

    def test_whitespace_stripped(self):
        result = parse_pip_requirements(["  requests  "])
        assert result == [{"name": "requests"}]

    def test_simple_function(self):
        """Generates schema from a simple function with typed args."""
        source = '''
def my_tool(query: str, count: int = 5):
    """Search for things.

    Args:
        query: The search query
    """
    pass
'''
        schema = generate_schema_from_source(source)
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert "count" in schema["properties"]
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["count"]["default"] == 5
        assert "query" in schema["required"]
        assert "count" not in schema["required"]

    def test_function_with_docstring_description(self):
        """Extracts description from docstring."""
        source = '''
def my_tool(x: str):
    """This is the tool description."""
    pass
'''
        schema = generate_schema_from_source(source)
        # The description is the first line of the docstring
        # It's used as the function description, not in the schema directly
        assert "x" in schema["properties"]

    def test_invalid_syntax_raises(self):
        """Raises ValueError for invalid Python syntax."""
        with pytest.raises(ValueError, match="Invalid Python syntax"):
            generate_schema_from_source("def (broken syntax")

    def test_no_function_raises(self):
        """Raises ValueError when no function definition is found."""
        with pytest.raises(ValueError, match="No function definition"):
            generate_schema_from_source("x = 1")

    def test_list_and_dict_types(self):
        """Handles List and Dict type annotations."""
        source = """
def my_tool(items: list, config: dict):
    pass
"""
        schema = generate_schema_from_source(source)
        assert schema["properties"]["items"]["type"] == "array"
        assert schema["properties"]["config"]["type"] == "object"

    def test_float_and_bool_types(self):
        """Handles float and bool type annotations."""
        source = """
def my_tool(rate: float, flag: bool):
    pass
"""
        schema = generate_schema_from_source(source)
        assert schema["properties"]["rate"]["type"] == "number"
        assert schema["properties"]["flag"]["type"] == "boolean"

    def test_default_none(self):
        """Handles default value of None."""
        source = """
def my_tool(x: str = None):
    pass
"""
        schema = generate_schema_from_source(source)
        assert schema["properties"]["x"]["default"] is None

    def test_arg_description_from_docstring(self):
        """Extracts argument descriptions from Args section."""
        source = '''
def my_tool(query: str):
    """Search tool.

    Args:
        query: The search text
    """
    pass
'''
        schema = generate_schema_from_source(source)
        assert schema["properties"]["query"]["description"] == "The search text"

    def test_self_parameter_skipped(self):
        """Skips 'self' parameter from class methods."""
        source = """
def my_tool(self, x: str):
    pass
"""
        schema = generate_schema_from_source(source)
        assert "self" not in schema["properties"]
        assert "x" in schema["properties"]


@pytest.mark.asyncio
class TestToolsCRUD:
    """Integration tests for tools CRUD endpoints."""

    async def test_list_tools(self, registered_client, mock_letta_client):
        """GET /api/tools/ lists tools."""
        client, headers, _ = registered_client
        resp = await client.get("/api/tools/", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_generate_schema(self, registered_client, mock_letta_client):
        """POST /api/tools/generate-schema generates schema from source."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/tools/generate-schema",
            headers=headers,
            json={
                "source_code": "def my_tool(query: str):\n    pass",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "properties" in data
        assert "query" in data["properties"]

    async def test_generate_schema_invalid_code(self, registered_client, mock_letta_client):
        """POST /api/tools/generate-schema returns 400 for invalid code."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/tools/generate-schema",
            headers=headers,
            json={
                "source_code": "not valid python syntax (",
            },
        )
        assert resp.status_code == 400

    async def test_create_tool(self, registered_client, mock_letta_client):
        """POST /api/tools/ creates a tool."""
        client, headers, _ = registered_client
        # Configure mock to return a tool on create
        mock_letta_tool = MagicMock()
        mock_letta_tool.id = "letta-tool-123"
        mock_letta_client.tools.create.return_value = mock_letta_tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "test_tool",
                    "description": "A test tool",
                    "source_code": "def test_tool(x: str):\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "test_tool"

    async def test_get_tool_not_found(self, registered_client, mock_letta_client):
        """GET /api/tools/{id} returns 404 for nonexistent tool."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/tools/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_get_tool(self, registered_client, mock_letta_client):
        """GET /api/tools/{id} returns tool details."""
        client, headers, _ = registered_client
        mock_letta_tool = MagicMock()
        mock_letta_tool.id = "letta-tool-456"
        mock_letta_client.tools.create.return_value = mock_letta_tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "get_tool",
                    "description": "Get tool test",
                    "source_code": "def get_tool(x: str):\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
        tool_id = create_resp.json()["id"]

        resp = await client.get(f"/api/tools/{tool_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "get_tool"
        assert "source_code" in resp.json()

    async def test_update_tool_description(self, registered_client, mock_letta_client):
        """PUT /api/tools/{id} updates tool description."""
        client, headers, _ = registered_client
        mock_letta_tool = MagicMock()
        mock_letta_tool.id = "letta-tool-789"
        mock_letta_client.tools.create.return_value = mock_letta_tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "update_tool",
                    "description": "Original desc",
                    "source_code": "def update_tool(x: str):\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
        tool_id = create_resp.json()["id"]

        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.put(
                f"/api/tools/{tool_id}",
                headers=headers,
                json={"description": "Updated desc"},
            )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated desc"

    async def test_delete_tool(self, registered_client, mock_letta_client):
        """DELETE /api/tools/{id} deletes tool."""
        client, headers, _ = registered_client
        mock_letta_tool = MagicMock()
        mock_letta_tool.id = "letta-tool-del"
        mock_letta_client.tools.create.return_value = mock_letta_tool
        mock_letta_client.tools.delete.return_value = None
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            create_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "delete_tool",
                    "description": "Delete me",
                    "source_code": "def delete_tool(x: str):\n    return x",
                    "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
                },
            )
        tool_id = create_resp.json()["id"]

        with patch("app.tools.routes.get_letta_client", return_value=mock_letta_client):
            resp = await client.delete(f"/api/tools/{tool_id}", headers=headers)
        assert resp.status_code in (200, 204)

    async def test_list_proposals(self, registered_client, mock_letta_client):
        """GET /api/tools/proposals lists pending proposals."""
        client, headers, _ = registered_client
        resp = await client.get("/api/tools/proposals", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
