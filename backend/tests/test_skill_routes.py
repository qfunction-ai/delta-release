"""Tests for skill routes — CRUD, upload, GitHub import, skill files, and unit helpers."""

import io
import zipfile

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.skills.github_fetch import extract_description_from_frontmatter, extract_name_from_frontmatter
from app.skills.importer import _guess_mime_type, _split_text_binary, parse_skill_zip
from app.skills.models import SkillFile
from app.skills.routes import validate_skill_name
from tests.conftest import SKILL_MD_CONTENT


def _make_skill_zip(name: str = "test-skill") -> bytes:
    """Create a zip file containing a SKILL.md with frontmatter."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        skill_md = f"---\nname: {name}\ndescription: A test skill\n---\n\n# {name}\n"
        zf.writestr(f"{name}/SKILL.md", skill_md)
    return buf.getvalue()


class TestSkillCreate:
    """Tests for POST /api/skills/ (manual skill creation)."""

    @pytest.mark.asyncio
    async def test_create_skill(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/skills/",
            json={
                "name": "test-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-skill"
        assert data["description"] == "A test skill for unit testing"

    @pytest.mark.asyncio
    async def test_reject_invalid_name(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/skills/",
            json={
                "name": "bad skill!",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        # Pydantic schema validation rejects at 422 level
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_duplicate_name(self, registered_client):
        client, headers, _ = registered_client
        resp1 = await client.post(
            "/api/skills/",
            json={
                "name": "dup-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/skills/",
            json={
                "name": "dup-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        assert resp2.status_code == 409


class TestSkillList:
    """Tests for GET /api/skills/."""

    @pytest.mark.asyncio
    async def test_list_skills_empty(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/skills/", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_skills_after_create(self, registered_client):
        client, headers, _ = registered_client
        await client.post(
            "/api/skills/",
            json={
                "name": "my-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )

        resp = await client.get("/api/skills/", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "my-skill"


class TestSkillDetail:
    """Tests for GET /api/skills/{skill_id}."""

    @pytest.mark.asyncio
    async def test_get_skill_detail(self, registered_client):
        client, headers, _ = registered_client
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "detail-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        resp = await client.get(f"/api/skills/{skill_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "detail-skill"


class TestSkillUpdate:
    """Tests for PUT /api/skills/{skill_id}."""

    @pytest.mark.asyncio
    async def test_update_skill_name(self, registered_client):
        client, headers, _ = registered_client
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "old-name",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/skills/{skill_id}",
            json={
                "name": "new-name",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    @pytest.mark.asyncio
    async def test_update_skill_content(self, registered_client):
        """PUT with new content updates skill.content."""
        client, headers, _ = registered_client
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "content-update",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        new_content = "---\nname: content-update\ndescription: Updated\n---\n\n# Updated\n"
        resp = await client.put(
            f"/api/skills/{skill_id}",
            json={
                "content": new_content,
            },
            headers=headers,
        )
        assert resp.status_code == 200

        # Verify content was updated by fetching it
        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert content_resp.status_code == 200
        assert "Updated" in content_resp.json()["content"]


class TestSkillContent:
    """Tests for GET /api/skills/{skill_id}/content."""

    @pytest.mark.asyncio
    async def test_get_skill_content(self, registered_client):
        """Content is returned from the database."""
        client, headers, _ = registered_client
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "content-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "content-skill"
        assert "E2E Test Skill" in data["content"] or "test skill" in data["content"].lower()

    @pytest.mark.asyncio
    async def test_get_skill_content_empty_raises_503(self, registered_client):
        """Skill with empty content returns 503."""
        client, headers, _ = registered_client
        # Create a skill, then manually clear its content
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "empty-content",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        # Update content to empty
        await client.put(
            f"/api/skills/{skill_id}",
            json={
                "content": "",
            },
            headers=headers,
        )

        resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert resp.status_code == 503


class TestSkillDelete:
    """Tests for DELETE /api/skills/{skill_id}."""

    @pytest.mark.asyncio
    async def test_delete_skill(self, registered_client):
        client, headers, _ = registered_client
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "to-delete",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/skills/{skill_id}", headers=headers)
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get(f"/api/skills/{skill_id}", headers=headers)
        assert resp.status_code == 404


class TestSkillUpload:
    """Tests for POST /api/skills/upload (zip upload)."""

    @pytest.mark.asyncio
    async def test_upload_skill_zip(self, registered_client):
        client, headers, _ = registered_client
        zip_bytes = _make_skill_zip("zip-skill")
        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("zip-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "zip-skill"

    @pytest.mark.asyncio
    async def test_upload_skill_zip_no_skill_md(self, registered_client):
        """Zip without SKILL.md returns 400."""
        client, headers, _ = registered_client
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("no-skill/README.md", "# No skill here")
        zip_bytes = buf.getvalue()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("no-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_skill_zip_path_traversal(self, registered_client):
        """Zip with ../ entries are skipped."""
        client, headers, _ = registered_client
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Normal skill entry
            zf.writestr("traversal-skill/SKILL.md", "---\nname: traversal-skill\ndescription: test\n---\n\n# Test\n")
            # Path traversal entry — should be skipped
            zf.writestr("../etc/passwd", "root:x:0:0:root:/root:/bin/bash")
        zip_bytes = buf.getvalue()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("traversal.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        # Should succeed — the traversal entry is skipped, but SKILL.md is valid
        assert resp.status_code == 201
        assert resp.json()["name"] == "traversal-skill"


class TestSkillGithubImport:
    """Tests for POST /api/skills/github (GitHub URL import)."""

    @pytest.mark.asyncio
    async def test_reject_invalid_github_url(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/skills/github",
            json={
                "github_url": "not-a-github-url",
            },
            headers=headers,
        )
        # Should reject non-GitHub URLs
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_malformed_github_url(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/skills/github",
            json={
                "github_url": "https://github.com/onlyonepart",
            },
            headers=headers,
        )
        # URL doesn't match the expected pattern
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_github_import_response_includes_tool_ids(self, registered_client, mock_letta_client):
        """POST /api/skills/github returns skill with tool_ids when tool.yaml is present."""
        from unittest.mock import AsyncMock, patch

        client, headers, _ = registered_client

        mock_skill_result = (
            "test-skill",  # name
            "A test skill",  # description
            "---\nname: test-skill\n---\nContent",  # skill_content
            {},  # extra_files
            True,  # has_tool_yaml
        )
        mock_tool_result = (
            "test_tool",  # name
            "A test tool",  # description
            "def test_tool(q: str) -> str:\n    return q",  # source_code
            {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "title": "TestTool"},
            None,  # tags
            None,  # pip_requirements
            False,  # _has_skill
        )

        with (
            patch("app.skills.routes.fetch_github_skill", new_callable=AsyncMock, return_value=mock_skill_result),
            patch("app.tools.github.fetch_github_tool", new_callable=AsyncMock, return_value=mock_tool_result),
            patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client),
        ):
            resp = await client.post(
                "/api/skills/github",
                json={"github_url": "https://github.com/org/repo/tree/main/skills/test-skill"},
                headers=headers,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert "skill" in data
        assert "tool" in data
        # The skill should have tool_ids populated with the co-created tool
        assert data["skill"]["tool_ids"] is not None
        assert len(data["skill"]["tool_ids"]) == 1
        # The tool should be in the response too
        assert data["tool"]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_github_import_response_empty_tool_ids_without_tool_yaml(self, registered_client):
        """POST /api/skills/github returns skill with empty tool_ids when no tool.yaml."""
        from unittest.mock import AsyncMock, patch

        client, headers, _ = registered_client

        mock_skill_result = (
            "solo-skill",
            "A solo skill",
            "---\nname: solo-skill\n---\nContent",
            {},
            False,  # has_tool_yaml = False
        )

        with patch("app.skills.routes.fetch_github_skill", new_callable=AsyncMock, return_value=mock_skill_result):
            resp = await client.post(
                "/api/skills/github",
                json={"github_url": "https://github.com/org/repo/tree/main/skills/solo-skill"},
                headers=headers,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["skill"]["tool_ids"] == []
        assert data["tool"] is None


# --- Unit tests for skill helpers ---


class TestValidateSkillName:
    """Tests for validate_skill_name."""

    def test_valid_names(self):
        """Valid names pass without raising."""
        validate_skill_name("my-skill")
        validate_skill_name("my_skill")
        validate_skill_name("MySkill123")

    def test_invalid_name_with_spaces(self):
        """Names with spaces raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_skill_name("my skill")
        assert exc_info.value.status_code == 400

    def test_invalid_name_with_special_chars(self):
        """Names with special characters raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            validate_skill_name("skill@name")
        assert exc_info.value.status_code == 400


class TestExtractNameFromFrontmatter:
    """Tests for extract_name_from_frontmatter."""

    def test_extracts_name(self):
        """Extracts name from YAML frontmatter."""
        content = "---\nname: my-skill\n---\nContent here"
        assert extract_name_from_frontmatter(content) == "my-skill"

    def test_returns_none_without_frontmatter(self):
        """Returns None when no frontmatter is present."""
        assert extract_name_from_frontmatter("Just content") is None

    def test_returns_none_with_incomplete_frontmatter(self):
        """Returns None when frontmatter is incomplete."""
        assert extract_name_from_frontmatter("---\nonly one delimiter") is None

    def test_extracts_quoted_name(self):
        """Extracts quoted name from frontmatter."""
        content = '---\nname: "my skill"\n---\nContent'
        assert extract_name_from_frontmatter(content) == "my skill"


class TestExtractDescriptionFromFrontmatter:
    """Tests for extract_description_from_frontmatter."""

    def test_extracts_description(self):
        """Extracts description from YAML frontmatter."""
        content = "---\nname: my-skill\ndescription: A test skill\n---\nContent"
        assert extract_description_from_frontmatter(content) == "A test skill"

    def test_returns_none_without_description(self):
        """Returns None when description is not in frontmatter."""
        content = "---\nname: my-skill\n---\nContent"
        assert extract_description_from_frontmatter(content) is None

    def test_returns_none_without_frontmatter(self):
        """Returns None when no frontmatter is present."""
        assert extract_description_from_frontmatter("Just content") is None


class TestParseSkillZip:
    """Tests for parse_skill_zip."""

    def _make_zip(self, files: dict[str, str]) -> bytes:
        """Create a zip file in memory from a dict of {path: content}."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, content in files.items():
                zf.writestr(path, content)
        return buf.getvalue()

    def test_valid_zip_with_skill_md(self):
        """Parses a valid zip with SKILL.md at root."""
        zip_bytes = self._make_zip(
            {
                "SKILL.md": "---\nname: test-skill\ndescription: Test\n---\nContent",
                "scripts/run.py": "print('hello')",
            }
        )
        name, desc, content, extras = parse_skill_zip(zip_bytes)
        assert name == "test-skill"
        assert desc == "Test"
        assert "SKILL.md" not in extras
        assert "scripts/run.py" in extras

    def test_zip_with_nested_skill_md(self):
        """Parses a zip with SKILL.md one level deep."""
        zip_bytes = self._make_zip(
            {
                "my-skill/SKILL.md": "---\nname: nested-skill\n---\nNested",
            }
        )
        name, desc, content, extras = parse_skill_zip(zip_bytes)
        assert name == "nested-skill"

    def test_zip_without_skill_md_raises(self):
        """Raises ValueError when no SKILL.md is found."""
        zip_bytes = self._make_zip({"readme.md": "No skill here"})
        with pytest.raises(ValueError, match="SKILL.md"):
            parse_skill_zip(zip_bytes)

    def test_invalid_zip_raises(self):
        """Raises ValueError for invalid zip data."""
        with pytest.raises(ValueError, match="Invalid zip"):
            parse_skill_zip(b"not a zip file")

    def test_zip_rejects_path_traversal(self):
        """Rejects zip entries with path traversal."""
        zip_bytes = self._make_zip(
            {
                "SKILL.md": "---\nname: traversal\n---\nContent",
                "../etc/passwd": "malicious",
            }
        )
        name, _, _, extras = parse_skill_zip(zip_bytes)
        assert "etc/passwd" not in extras

    def test_zip_without_name_frontmatter_uses_directory(self):
        """Derives name from directory when frontmatter has no name."""
        zip_bytes = self._make_zip(
            {
                "my-dir/SKILL.md": "No frontmatter here",
            }
        )
        name, _, _, _ = parse_skill_zip(zip_bytes)
        assert name == "my-dir"


class TestSkillFileHelpers:
    """Tests for _split_text_binary and _guess_mime_type."""

    def test_split_text_binary_utf8(self):
        """UTF-8 decodable bytes return (text, None)."""
        text, binary = _split_text_binary("hello world".encode("utf-8"))
        assert text == "hello world"
        assert binary is None

    def test_split_text_binary_non_utf8(self):
        """Non-UTF-8 bytes return (None, bytes)."""
        data = b"\x89PNG\r\n\x1a\n"
        text, binary = _split_text_binary(data)
        assert text is None
        assert binary == data

    def test_split_text_binary_null_bytes(self):
        """Data with null bytes is treated as binary."""
        data = b"hello\x00world"
        text, binary = _split_text_binary(data)
        assert text is None
        assert binary == data

    def test_guess_mime_type_python(self):
        assert _guess_mime_type("scripts/run.py") == "text/x-python"

    def test_guess_mime_type_markdown(self):
        assert _guess_mime_type("references/api-docs.md") == "text/markdown"

    def test_guess_mime_type_yaml(self):
        assert _guess_mime_type("config.yaml") == "application/yaml"

    def test_guess_mime_type_png(self):
        assert _guess_mime_type("assets/diagram.png") == "image/png"

    def test_guess_mime_type_unknown(self):
        assert _guess_mime_type("data.xyz123") == "application/octet-stream"


class TestSkillFileUpload:
    """Tests for skill file persistence on upload."""

    def _make_zip_with_files(self, name: str = "file-skill") -> bytes:
        """Create a zip with SKILL.md plus extra files in various directories."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                f"{name}/SKILL.md",
                f"---\nname: {name}\ndescription: A skill with files\n---\n\n# {name}\n",
            )
            zf.writestr(f"{name}/scripts/run.py", "def run(): pass\n")
            zf.writestr(f"{name}/references/api.md", "# API Reference\n")
            zf.writestr(f"{name}/assets/diagram.png", b"\x89PNG\r\n\x1a\nfake")
            zf.writestr(f"{name}/examples/demo.py", "print('demo')\n")
            zf.writestr(f"{name}/config.yaml", "key: value\n")
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_upload_persists_skill_files(self, registered_client):
        """Uploading a zip with extra files persists them as SkillFile rows."""
        client, headers, _ = registered_client
        zip_bytes = self._make_zip_with_files()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("file-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        assert resp.status_code == 201
        skill_id = resp.json()["id"]

        # Fetch content — should include files list
        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert content_resp.status_code == 200
        data = content_resp.json()
        assert len(data["files"]) == 5

        # Verify file paths
        paths = {f["path"] for f in data["files"]}
        assert "scripts/run.py" in paths
        assert "references/api.md" in paths
        assert "assets/diagram.png" in paths
        assert "examples/demo.py" in paths
        assert "config.yaml" in paths

    @pytest.mark.asyncio
    async def test_upload_text_file_has_content_text(self, registered_client, db_session):
        """Text files are stored in content_text, not content_bytes."""
        client, headers, _ = registered_client
        zip_bytes = self._make_zip_with_files()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("file-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        # Query the DB directly via the test session
        result = await db_session.execute(select(SkillFile).where(SkillFile.skill_id == skill_id))
        files = result.scalars().all()

        text_files = [f for f in files if f.content_text is not None]
        binary_files = [f for f in files if f.content_bytes is not None]

        # scripts/run.py, references/api.md, examples/demo.py, config.yaml are text
        assert len(text_files) == 4
        # assets/diagram.png is binary
        assert len(binary_files) == 1
        assert binary_files[0].path == "assets/diagram.png"

    @pytest.mark.asyncio
    async def test_upload_file_mime_types(self, registered_client):
        """Files have correct MIME types."""
        client, headers, _ = registered_client
        zip_bytes = self._make_zip_with_files()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("file-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        files = content_resp.json()["files"]
        mime_map = {f["path"]: f["mime_type"] for f in files}

        assert mime_map["scripts/run.py"] == "text/x-python"
        assert mime_map["references/api.md"] == "text/markdown"
        assert mime_map["assets/diagram.png"] == "image/png"
        assert mime_map["config.yaml"] == "application/yaml"


class TestSkillFileDownload:
    """Tests for GET /api/skills/{skill_id}/files/{file_id}."""

    def _make_zip_with_files(self, name: str = "dl-skill") -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                f"{name}/SKILL.md",
                f"---\nname: {name}\ndescription: Download test\n---\n\n# {name}\n",
            )
            zf.writestr(f"{name}/scripts/run.py", "def run(): pass\n")
            zf.writestr(f"{name}/assets/icon.png", b"\x89PNG\r\n\x1a\nfake-png")
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_download_text_file(self, registered_client):
        """Downloading a text file returns the correct content and MIME type."""
        client, headers, _ = registered_client
        zip_bytes = self._make_zip_with_files()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("dl-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        # Get file ID from content endpoint
        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        files = content_resp.json()["files"]
        py_file = next(f for f in files if f["path"] == "scripts/run.py")

        # Download the file
        dl_resp = await client.get(f"/api/skills/{skill_id}/files/{py_file['id']}", headers=headers)
        assert dl_resp.status_code == 200
        assert "text/x-python" in dl_resp.headers["content-type"]
        assert "run.py" in dl_resp.headers["content-disposition"]
        assert "def run(): pass" in dl_resp.text

    @pytest.mark.asyncio
    async def test_download_binary_file(self, registered_client):
        """Downloading a binary file returns the correct content and MIME type."""
        client, headers, _ = registered_client
        zip_bytes = self._make_zip_with_files()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("dl-skill.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        files = content_resp.json()["files"]
        png_file = next(f for f in files if f["path"] == "assets/icon.png")

        dl_resp = await client.get(f"/api/skills/{skill_id}/files/{png_file['id']}", headers=headers)
        assert dl_resp.status_code == 200
        assert "image/png" in dl_resp.headers["content-type"]
        assert "icon.png" in dl_resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_download_nonexistent_file_404(self, registered_client):
        """Requesting a nonexistent file ID returns 404."""
        client, headers, _ = registered_client
        # Create a skill first
        create_resp = await client.post(
            "/api/skills/",
            json={"name": "dl-404", "content": SKILL_MD_CONTENT},
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        dl_resp = await client.get(
            f"/api/skills/{skill_id}/files/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert dl_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_sanitizes_content_disposition(self, registered_client, db_session):
        """Content-Disposition header is sanitized — no quotes or newlines."""
        from app.skills.models import SkillFile

        client, headers, _ = registered_client

        # Create a skill
        resp = await client.post(
            "/api/skills/",
            json={"name": "header-inject", "content": SKILL_MD_CONTENT},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        # Insert a SkillFile with a malicious path directly in the DB
        malicious_file = SkillFile(
            skill_id=skill_id,
            path='file"name\r\nX-Injected: true.txt',
            content_text="<script>alert(1)</script>",
            mime_type="text/html",
        )
        db_session.add(malicious_file)
        await db_session.flush()
        file_id = str(malicious_file.id)

        # Download the file
        dl_resp = await client.get(f"/api/skills/{skill_id}/files/{file_id}", headers=headers)
        assert dl_resp.status_code == 200

        # Verify Content-Disposition has no quotes or newlines
        # (the actual header injection vector — newlines let you add new headers)
        cd = dl_resp.headers.get("content-disposition", "")
        assert '"' not in cd.split('filename="')[-1].rstrip('"') if 'filename="' in cd else True
        assert "\r" not in cd
        assert "\n" not in cd

        # Verify text/html mime_type was downgraded to application/octet-stream
        assert "text/html" not in dl_resp.headers.get("content-type", "")


class TestSkillFileCascadeDelete:
    """Tests that deleting a skill cascades to its files."""

    @pytest.mark.asyncio
    async def test_delete_skill_cascades_to_files(self, registered_client):
        """Deleting a skill removes all associated files."""
        client, headers, _ = registered_client
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("cascade-skill/SKILL.md", "---\nname: cascade-skill\n---\n# Test\n")
            zf.writestr("cascade-skill/scripts/run.py", "pass\n")
        zip_bytes = buf.getvalue()

        resp = await client.post(
            "/api/skills/upload",
            files={"file": ("cascade.zip", zip_bytes, "application/zip")},
            headers=headers,
        )
        skill_id = resp.json()["id"]

        # Verify files exist
        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert len(content_resp.json()["files"]) == 1

        # Delete the skill
        del_resp = await client.delete(f"/api/skills/{skill_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify files are gone (skill is gone, so content endpoint returns 404)
        content_resp2 = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert content_resp2.status_code == 404


class TestSkillToolLinking:
    """Tests for skill-tool association via the skill_tools join table."""

    @pytest.mark.asyncio
    async def test_create_skill_with_tool_ids(self, registered_client, mock_letta_client):
        """POST /api/skills/ with tool_ids creates skill-tool links."""
        from unittest.mock import patch

        client, headers, _ = registered_client

        # Create a tool first
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "linked_tool",
                    "source_code": 'def linked_tool(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "LinkedTool",
                    },
                },
            )
        assert tool_resp.status_code == 201
        tool_id = tool_resp.json()["id"]

        # Create skill with tool_ids
        resp = await client.post(
            "/api/skills/",
            json={
                "name": "skill-with-tool",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_id],
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tool_ids"] == [tool_id]

    @pytest.mark.asyncio
    async def test_list_skills_includes_tool_ids(self, registered_client, mock_letta_client):
        """GET /api/skills/ returns tool_ids for each skill."""
        from unittest.mock import patch

        client, headers, _ = registered_client

        # Create a tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "list_tool",
                    "source_code": 'def list_tool(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "ListTool",
                    },
                },
            )
        tool_id = tool_resp.json()["id"]

        # Create skill with tool_ids
        await client.post(
            "/api/skills/",
            json={
                "name": "linked-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_id],
            },
            headers=headers,
        )

        # List skills
        resp = await client.get("/api/skills/", headers=headers)
        assert resp.status_code == 200
        skills = resp.json()
        linked = [s for s in skills if s["name"] == "linked-skill"]
        assert len(linked) == 1
        assert linked[0]["tool_ids"] == [tool_id]

    @pytest.mark.asyncio
    async def test_get_skill_includes_tool_ids(self, registered_client, mock_letta_client):
        """GET /api/skills/{id} returns tool_ids."""
        from unittest.mock import patch

        client, headers, _ = registered_client

        # Create a tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "detail_tool",
                    "source_code": 'def detail_tool(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "DetailTool",
                    },
                },
            )
        tool_id = tool_resp.json()["id"]

        # Create skill with tool_ids
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "detail-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_id],
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        # Get skill detail
        resp = await client.get(f"/api/skills/{skill_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["tool_ids"] == [tool_id]

    @pytest.mark.asyncio
    async def test_get_skill_content_includes_tool_ids(self, registered_client, mock_letta_client):
        """GET /api/skills/{id}/content returns tool_ids."""
        from unittest.mock import patch

        client, headers, _ = registered_client

        # Create a tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "content_tool",
                    "source_code": 'def content_tool(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "ContentTool",
                    },
                },
            )
        tool_id = tool_resp.json()["id"]

        # Create skill with tool_ids
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "content-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_id],
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        # Get skill content
        resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["tool_ids"] == [tool_id]

    @pytest.mark.asyncio
    async def test_update_skill_tool_ids(self, registered_client, mock_letta_client):
        """PUT /api/skills/{id} with tool_ids replaces the tool links."""
        from unittest.mock import patch

        client, headers, _ = registered_client

        # Create two tools
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool1_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "update_tool_1",
                    "source_code": 'def update_tool_1(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "UpdateTool1",
                    },
                },
            )
            tool2_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "update_tool_2",
                    "source_code": 'def update_tool_2(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "UpdateTool2",
                    },
                },
            )
        tool1_id = tool1_resp.json()["id"]
        tool2_id = tool2_resp.json()["id"]

        # Create skill with tool1
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "update-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool1_id],
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        # Update to tool2 instead
        update_resp = await client.put(
            f"/api/skills/{skill_id}",
            json={"tool_ids": [tool2_id]},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["tool_ids"] == [tool2_id]

    @pytest.mark.asyncio
    async def test_skill_without_tools_has_empty_tool_ids(self, registered_client):
        """Skills with no tool links return empty tool_ids list."""
        client, headers, _ = registered_client

        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "no-tools-skill",
                "content": SKILL_MD_CONTENT,
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["tool_ids"] == []

    @pytest.mark.asyncio
    async def test_delete_skill_cascades_to_skill_tools(self, registered_client, mock_letta_client):
        """Deleting a skill cascades to skill_tools rows."""
        from unittest.mock import patch

        client, headers, user_id = registered_client

        # Create a tool
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            tool_resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "cascade_tool",
                    "source_code": 'def cascade_tool(query: str) -> str:\n    """A tool."""\n    return query',
                    "json_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                        "title": "CascadeTool",
                    },
                },
            )
        tool_id = tool_resp.json()["id"]

        # Create skill with tool_ids
        create_resp = await client.post(
            "/api/skills/",
            json={
                "name": "cascade-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_id],
            },
            headers=headers,
        )
        skill_id = create_resp.json()["id"]

        # Delete the skill
        del_resp = await client.delete(f"/api/skills/{skill_id}", headers=headers)
        assert del_resp.status_code == 204

        # Verify skill_tools rows are gone (skill is gone, so content endpoint returns 404)
        content_resp = await client.get(f"/api/skills/{skill_id}/content", headers=headers)
        assert content_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_skill_rejects_other_users_tool(self, registered_client, mock_letta_client, db_session):
        """IDOR: User cannot link a skill to another user's tool."""

        from app.auth.models import User
        from app.tools.models import Tool

        client_a, headers_a, user_a_id = registered_client

        # Create a second user directly in the DB
        user_b = User(username="idor_b_test", password_hash="$2b$12$fakehash")
        db_session.add(user_b)
        await db_session.flush()
        user_b_id = str(user_b.id)

        # Create a tool owned by user B directly in the DB
        tool_b = Tool(
            user_id=user_b_id,
            name="idor_tool_b",
            description="User B's tool",
            letta_tool_id="tool-idor-b-fake",
            source_code="def idor_tool(q: str) -> str: return q",
            json_schema='{"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "title": "IdorTool"}',
            source="manual",
        )
        db_session.add(tool_b)
        await db_session.flush()
        tool_b_id = str(tool_b.id)

        # User A tries to create a skill linked to User B's tool
        resp = await client_a.post(
            "/api/skills/",
            json={
                "name": "idor-skill",
                "content": SKILL_MD_CONTENT,
                "tool_ids": [tool_b_id],
            },
            headers=headers_a,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_skill_rejects_other_users_tool(self, registered_client, mock_letta_client, db_session):
        """IDOR: User cannot update a skill to link another user's tool."""

        from app.auth.models import User
        from app.tools.models import Tool

        client_a, headers_a, user_a_id = registered_client

        # Create a skill owned by user A
        create_resp = await client_a.post(
            "/api/skills/",
            json={"name": "idor-update-skill", "content": SKILL_MD_CONTENT},
            headers=headers_a,
        )
        skill_id = create_resp.json()["id"]

        # Create a second user and their tool
        user_b = User(username="idor_update_b_test", password_hash="$2b$12$fakehash")
        db_session.add(user_b)
        await db_session.flush()
        user_b_id = str(user_b.id)

        tool_b = Tool(
            user_id=user_b_id,
            name="idor_update_tool_b",
            description="User B's tool",
            letta_tool_id="tool-idor-update-b-fake",
            source_code="def idor_update_tool(q: str) -> str: return q",
            json_schema='{"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "title": "IdorUpdateTool"}',
            source="manual",
        )
        db_session.add(tool_b)
        await db_session.flush()
        tool_b_id = str(tool_b.id)

        # User A tries to update their skill to link User B's tool
        resp = await client_a.put(
            f"/api/skills/{skill_id}",
            json={"tool_ids": [tool_b_id]},
            headers=headers_a,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
