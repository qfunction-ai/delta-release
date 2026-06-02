"""Tests for tool.yaml manifest parser."""

import pytest

from app.tools.tool_yaml import ToolYamlError, parse_tool_yaml, validate_entry_point


class TestParseToolYaml:
    """Test parse_tool_yaml with various valid and invalid manifests."""

    def test_minimal_manifest(self):
        """Minimal valid manifest: name + entry_point only."""
        yaml = "name: query_splunk\nentry_point: query_splunk\n"
        manifest = parse_tool_yaml(yaml)
        assert manifest.name == "query_splunk"
        assert manifest.entry_point == "query_splunk"
        assert manifest.source == "scripts/query_splunk.py"
        assert manifest.schema == "schema.json"
        assert manifest.tags == []
        assert manifest.requirements == "requirements.txt"
        assert manifest.description is None

    def test_full_manifest(self):
        """Full manifest with all fields."""
        yaml = """\
name: query_splunk
description: "Search Splunk for events"
entry_point: query_splunk
source: scripts/splunk_tool.py
schema: my_schema.json
tags: [splunk, siem]
requirements: deps.txt
"""
        manifest = parse_tool_yaml(yaml)
        assert manifest.name == "query_splunk"
        assert manifest.description == "Search Splunk for events"
        assert manifest.entry_point == "query_splunk"
        assert manifest.source == "scripts/splunk_tool.py"
        assert manifest.schema == "my_schema.json"
        assert manifest.tags == ["splunk", "siem"]
        assert manifest.requirements == "deps.txt"

    def test_tags_as_comma_string(self):
        """Tags can be a comma-separated string."""
        yaml = "name: foo\nentry_point: foo\ntags: a, b, c\n"
        manifest = parse_tool_yaml(yaml)
        assert manifest.tags == ["a", "b", "c"]

    def test_missing_name(self):
        """Missing name raises ToolYamlError."""
        yaml = "entry_point: foo\n"
        with pytest.raises(ToolYamlError, match="missing required field: name"):
            parse_tool_yaml(yaml)

    def test_missing_entry_point(self):
        """Missing entry_point raises ToolYamlError."""
        yaml = "name: foo\n"
        with pytest.raises(ToolYamlError, match="missing required field: entry_point"):
            parse_tool_yaml(yaml)

    def test_invalid_name(self):
        """Invalid name (uppercase, spaces) raises ToolYamlError."""
        yaml = "name: QuerySplunk\nentry_point: query_splunk\n"
        with pytest.raises(ToolYamlError, match="valid Python identifier"):
            parse_tool_yaml(yaml)

    def test_invalid_entry_point(self):
        """Invalid entry_point raises ToolYamlError."""
        yaml = "name: foo\nentry_point: 123bad\n"
        with pytest.raises(ToolYamlError, match="valid Python identifier"):
            parse_tool_yaml(yaml)

    def test_invalid_yaml(self):
        """Malformed YAML raises ToolYamlError."""
        yaml = "{{invalid: yaml: ["
        with pytest.raises(ToolYamlError, match="Invalid YAML"):
            parse_tool_yaml(yaml)

    def test_non_dict_yaml(self):
        """YAML list instead of dict raises ToolYamlError."""
        yaml = "- name: foo\n- entry_point: bar\n"
        with pytest.raises(ToolYamlError, match="must be a YAML mapping"):
            parse_tool_yaml(yaml)

    def test_default_source_path(self):
        """Source defaults to scripts/{entry_point}.py."""
        yaml = "name: search_logs\nentry_point: search_logs\n"
        manifest = parse_tool_yaml(yaml)
        assert manifest.source == "scripts/search_logs.py"

    def test_custom_source_path(self):
        """Custom source path overrides default."""
        yaml = "name: foo\nentry_point: foo\nsource: custom/path.py\n"
        manifest = parse_tool_yaml(yaml)
        assert manifest.source == "custom/path.py"


class TestValidateEntryPoint:
    """Test validate_entry_point function."""

    def test_valid_entry_point(self):
        """Entry point exists as a function definition."""
        source = "def query_splunk(query: str) -> str:\n    return query\n"
        # Should not raise
        validate_entry_point(source, "query_splunk")

    def test_missing_entry_point(self):
        """Entry point not found in source."""
        source = "def other_function() -> str:\n    return 'hello'\n"
        with pytest.raises(ToolYamlError, match="not found"):
            validate_entry_point(source, "query_splunk")

    def test_entry_point_as_substring(self):
        """Entry point name as substring of another function doesn't match."""
        source = "def query_splunk_v2() -> str:\n    return 'hello'\n"
        with pytest.raises(ToolYamlError, match="not found"):
            validate_entry_point(source, "query_splunk")

    def test_nested_function_def(self):
        """Function def inside a string or comment doesn't match."""
        source = '# def query_splunk():\n"""Some docs about def query_splunk"""\n'
        with pytest.raises(ToolYamlError, match="not found"):
            validate_entry_point(source, "query_splunk")
