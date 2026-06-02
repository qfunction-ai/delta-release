"""E2E tool tests — create, generate schema, list, delete."""


class TestToolCRUD:
    def test_create_tool(self, e2e_tool_id):
        """Tool was created by the fixture and has a valid ID."""
        assert e2e_tool_id is not None

    def test_generate_schema(self, e2e_client, e2e_token_manager):
        """Schema generation from Python source code returns a valid schema."""
        source = 'def hello_tool(name: str) -> str:\n    """Say hello.\n\n    Args:\n        name: The name.\n\n    Returns:\n        Greeting string.\n    """\n    return f"Hello {name}"\n'
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/generate-schema",
            json={
                "source_code": source,
            },
        )
        assert resp.status_code == 200
        schema = resp.json()
        assert "properties" in schema
        assert "name" in schema["properties"]

    def test_list_tools(self, e2e_client, e2e_token_manager, e2e_tool_id):
        """List tools includes the session-scoped tool."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
        assert resp.status_code == 200
        tools = resp.json()
        assert any(t["id"] == e2e_tool_id for t in tools)

    def test_delete_tool(self, e2e_client, e2e_token_manager):
        """Create a tool, then delete it."""
        # Create a tool to delete
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": "e2e_delete_tool",
                "description": "A tool to be deleted",
                "source_code": 'def e2e_delete_tool(x: int) -> int:\n    """Return x.\n\n    Args:\n        x: A number.\n\n    Returns:\n        The same number.\n    """\n    return x\n',
                "json_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer", "description": "A number."}},
                    "required": ["x"],
                    "title": "E2eDeleteTool",
                },
            },
        )
        assert resp.status_code == 201
        tool_id = resp.json()["id"]

        # Delete it
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/tools/{tool_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/tools/{tool_id}")
        assert resp.status_code == 404
