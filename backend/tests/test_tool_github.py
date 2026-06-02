"""Tests for tools/github.py — GitHub tool import."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.tools.github import TOOL_YAML_FILENAME, fetch_github_tool


class TestFetchGitHubTool:
    """Tests for fetch_github_tool function."""

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock httpx.AsyncClient."""
        return MagicMock()

    @pytest.fixture
    def valid_tool_yaml(self):
        """A valid tool.yaml content."""
        return """
name: test-tool
description: A test tool
source: tool.py
entry_point: run
schema: schema.json
tags:
  - test
"""

    @pytest.fixture
    def valid_source_code(self):
        """Valid source code with entry point."""
        return """
def run(arg1: str) -> str:
    return arg1.upper()
"""

    @pytest.fixture
    def valid_schema(self):
        """Valid JSON schema."""
        return '{"type": "object", "properties": {"arg1": {"type": "string"}}}'

    @pytest.mark.asyncio
    async def test_fetch_github_tool_success(self, mock_http_client, valid_tool_yaml, valid_source_code, valid_schema):
        """Full happy path — tool.yaml, source.py, schema.json."""
        gh_headers = {}

        # Mock directory contents
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://raw.../tool.yaml"},
            {"name": "tool.py", "type": "file", "download_url": "https://raw.../tool.py"},
            {"name": "schema.json", "type": "file", "download_url": "https://raw.../schema.json"},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, valid_schema]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.name = "test-tool"
                        mock_manifest.description = "A test tool"
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.tags = ["test"]
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)

        name, description, source, schema, tags, pip_reqs, has_skill_md = result
        assert name == "test-tool"
        assert description == "A test tool"
        assert source == valid_source_code
        assert schema == {"type": "object", "properties": {"arg1": {"type": "string"}}}
        assert tags == ["test"]
        assert pip_reqs is None
        assert has_skill_md is False

    @pytest.mark.asyncio
    async def test_missing_tool_yaml_raises_400(self, mock_http_client):
        """Missing tool.yaml raises 400."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.py", "type": "file"},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with pytest.raises(HTTPException) as exc:
                    await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)
        assert exc.value.status_code == 400
        assert TOOL_YAML_FILENAME in exc.value.detail

    @pytest.mark.asyncio
    async def test_invalid_tool_yaml_raises_400(self, mock_http_client):
        """Invalid tool.yaml raises 400."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch(
                    "app.tools.github.fetch_file_from_github", new_callable=AsyncMock, return_value="invalid yaml"
                ):
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        from app.tools.tool_yaml import ToolYamlError

                        mock_parse.side_effect = ToolYamlError("missing required field")
                        with pytest.raises(HTTPException) as exc:
                            await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_source_file_not_found_raises_400(self, mock_http_client, valid_tool_yaml):
        """Source file not in directory raises 400."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            # Missing tool.py
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch(
                    "app.tools.github.fetch_file_from_github", new_callable=AsyncMock, return_value=valid_tool_yaml
                ):
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with pytest.raises(HTTPException) as exc:
                            await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)
        assert exc.value.status_code == 400
        assert "Source file" in exc.value.detail

    @pytest.mark.asyncio
    async def test_schema_file_not_found_auto_generates(self, mock_http_client, valid_tool_yaml, valid_source_code):
        """Schema file not in directory — auto-generates from source code."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "tool.py", "type": "file", "download_url": "https://..."},
            # Missing schema.json — should auto-generate
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)
        # result is (name, description, source_code, json_schema, tags, pip_reqs, has_skill_yaml)
        json_schema = result[3]
        # Auto-generated schema should have properties from the function signature
        assert "properties" in json_schema

    @pytest.mark.asyncio
    async def test_invalid_schema_json_raises_400(self, mock_http_client, valid_tool_yaml, valid_source_code):
        """Invalid JSON in schema file raises 400."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "tool.py", "type": "file", "download_url": "https://..."},
            {"name": "schema.json", "type": "file", "download_url": "https://..."},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, "not valid json"]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                with pytest.raises(HTTPException) as exc:
                                    await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)
        assert exc.value.status_code == 400
        assert "Invalid JSON" in exc.value.detail

    @pytest.mark.asyncio
    async def test_source_in_subdir(self, mock_http_client, valid_tool_yaml, valid_source_code, valid_schema):
        """Source file in a subdirectory is found correctly."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "src", "type": "dir", "url": "https://api.github.com/repos/.../src"},
        ]
        subdir_contents = [
            {"name": "tool.py", "type": "file", "download_url": "https://.../src/tool.py"},
            {"name": "schema.json", "type": "file", "download_url": "https://.../src/schema.json"},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch(
                    "app.tools.github.fetch_github_subdir_contents",
                    new_callable=AsyncMock,
                    return_value=subdir_contents,
                ):
                    with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                        mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, valid_schema]
                        with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                            mock_manifest = MagicMock()
                            mock_manifest.name = "test-tool"
                            mock_manifest.description = "A test tool"
                            mock_manifest.source = "src/tool.py"
                            mock_manifest.entry_point = "run"
                            mock_manifest.schema = "src/schema.json"
                            mock_manifest.tags = []
                            mock_manifest.requirements = "requirements.txt"
                            mock_parse.return_value = mock_manifest
                            with patch("app.tools.github.validate_entry_point"):
                                with patch("app.tools.github.validate_tool_source_code"):
                                    result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)

        name, description, source, schema, tags, pip_reqs, has_skill_md = result
        assert name == "test-tool"

    @pytest.mark.asyncio
    async def test_optional_requirements_missing(
        self, mock_http_client, valid_tool_yaml, valid_source_code, valid_schema
    ):
        """Missing requirements.txt returns None for pip_requirements."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "tool.py", "type": "file", "download_url": "https://..."},
            {"name": "schema.json", "type": "file", "download_url": "https://..."},
            # No requirements.txt
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, valid_schema]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.tags = []
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)

        name, description, source, schema, tags, pip_reqs, has_skill_md = result
        assert pip_reqs is None

    @pytest.mark.asyncio
    async def test_has_skill_md_detection(self, mock_http_client, valid_tool_yaml, valid_source_code, valid_schema):
        """SKILL.md present in directory sets has_skill_md=True."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "tool.py", "type": "file", "download_url": "https://..."},
            {"name": "schema.json", "type": "file", "download_url": "https://..."},
            {"name": "SKILL.md", "type": "file", "download_url": "https://..."},
        ]

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, valid_schema]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.tags = []
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)

        name, description, source, schema, tags, pip_reqs, has_skill_md = result
        assert has_skill_md is True

    @pytest.mark.asyncio
    async def test_requirements_parsed_correctly(
        self, mock_http_client, valid_tool_yaml, valid_source_code, valid_schema
    ):
        """requirements.txt is parsed into a list of packages."""
        gh_headers = {}
        dir_contents = [
            {"name": "tool.yaml", "type": "file", "download_url": "https://..."},
            {"name": "tool.py", "type": "file", "download_url": "https://..."},
            {"name": "schema.json", "type": "file", "download_url": "https://..."},
            {"name": "requirements.txt", "type": "file", "download_url": "https://..."},
        ]
        requirements_content = "requests>=2.0\n# comment\nhttpx\n\n"

        with patch("app.tools.github.detect_default_branch", new_callable=AsyncMock, return_value="main"):
            with patch("app.tools.github.fetch_github_directory", new_callable=AsyncMock, return_value=dir_contents):
                with patch("app.tools.github.fetch_file_from_github", new_callable=AsyncMock) as mock_fetch:
                    mock_fetch.side_effect = [valid_tool_yaml, valid_source_code, valid_schema, requirements_content]
                    with patch("app.tools.github.parse_tool_yaml") as mock_parse:
                        mock_manifest = MagicMock()
                        mock_manifest.source = "tool.py"
                        mock_manifest.entry_point = "run"
                        mock_manifest.schema = "schema.json"
                        mock_manifest.tags = []
                        mock_manifest.requirements = "requirements.txt"
                        mock_parse.return_value = mock_manifest
                        with patch("app.tools.github.validate_entry_point"):
                            with patch("app.tools.github.validate_tool_source_code"):
                                result = await fetch_github_tool("owner", "repo", "main", "tools/test", gh_headers)

        name, description, source, schema, tags, pip_reqs, has_skill_md = result
        assert pip_reqs == ["requests>=2.0", "httpx"]
