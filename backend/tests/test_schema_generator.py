"""Tests for tool schema generation from Python source code."""

import pytest

from app.tools.routes import generate_schema_from_source


class TestSchemaGeneration:
    def test_simple_function(self):
        """Generates schema from a simple function with typed args."""
        source = '''
def search_logs(query: str, limit: int = 10) -> str:
    """Search logs for a query."""
    return "results"
'''
        schema = generate_schema_from_source(source)
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["properties"]["limit"]["type"] == "integer"
        assert "query" in schema["required"]
        assert "limit" not in schema["required"]

    def test_docstring_description(self):
        """Extracts description from function docstring."""
        source = '''
def my_tool(name: str) -> str:
    """This is the tool description."""
    return name
'''
        schema = generate_schema_from_source(source)
        assert (
            "tool description" in schema["properties"]["name"]["description"].lower()
            or "name parameter" in schema["properties"]["name"]["description"].lower()
        )

    def test_defaults_not_required(self):
        """Arguments with defaults are not in the required list."""
        source = '''
def my_tool(required_arg: str, optional_arg: int = 5) -> str:
    """A tool."""
    return "ok"
'''
        schema = generate_schema_from_source(source)
        assert "required_arg" in schema["required"]
        assert "optional_arg" not in schema["required"]
        assert schema["properties"]["optional_arg"]["default"] == 5

    def test_invalid_syntax(self):
        """Invalid Python syntax raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Python syntax"):
            generate_schema_from_source("def (broken syntax")

    def test_no_function(self):
        """Source without a function definition raises ValueError."""
        with pytest.raises(ValueError, match="No function definition"):
            generate_schema_from_source("x = 1")

    def test_skips_self(self):
        """Self parameter is excluded from the schema."""
        source = '''
class MyClass:
    def my_method(self, name: str) -> str:
        """A method."""
        return name
'''
        schema = generate_schema_from_source(source)
        assert "self" not in schema["properties"]
        assert "name" in schema["properties"]

    def test_list_annotation(self):
        """list[str] annotation maps to array type."""
        source = '''
def my_tool(items: list[str]) -> str:
    """Process items."""
    return "ok"
'''
        schema = generate_schema_from_source(source)
        assert schema["properties"]["items"]["type"] == "array"

    def test_no_annotations(self):
        """Arguments without annotations default to string type."""
        source = '''
def my_tool(name) -> str:
    """A tool."""
    return name
'''
        schema = generate_schema_from_source(source)
        assert schema["properties"]["name"]["type"] == "string"

    def test_none_default(self):
        """Default value of None is handled."""
        source = '''
def my_tool(name: str = None) -> str:
    """A tool."""
    return name
'''
        schema = generate_schema_from_source(source)
        assert "name" not in schema["required"]
        assert schema["properties"]["name"]["default"] is None
