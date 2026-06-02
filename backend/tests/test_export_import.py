"""Tests for export/import functionality."""

import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _create_agent_via_api(client, headers, mock_letta_client, name="test-agent"):
    """Helper to create an agent via the API with a mocked Letta client."""
    mock_model = MagicMock()
    mock_model.id = "ollama/gemma4:latest"
    mock_letta_client.models.list.return_value = MagicMock(data=[mock_model])

    with patch("app.agents.routes.get_letta_client", return_value=mock_letta_client):
        resp = await client.post(
            "/api/agents/",
            headers=headers,
            json={
                "name": name,
                "model": "ollama/gemma4:latest",
                "embedding": "ollama/embeddinggemma:latest",
            },
        )
    assert resp.status_code == 201, f"Agent creation failed: {resp.text}"
    return resp.json()["letta_agent_id"]


@pytest.mark.asyncio
class TestExport:
    """Tests for export endpoint."""

    async def test_export_empty_returns_valid_json(self, registered_client, mock_letta_client):
        """Export with no data returns valid empty export."""
        client, headers, _ = registered_client
        resp = await client.get("/api/export-import/export/", headers=headers)

        assert resp.status_code == 200
        assert resp.headers["content-disposition"] == 'attachment; filename="delta-export.json"'

        data = resp.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert data["tools"] == []
        assert data["skills"] == []
        assert data["workflows"] == []

    async def test_export_includes_tools(self, registered_client, mock_letta_client):
        """Export includes all user's tools."""
        client, headers, _ = registered_client

        # Create a tool (mock_letta_client handles Letta side)
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "test_tool",
                    "description": "Test tool",
                    "source_code": "def test_tool(): pass",
                    "json_schema": {"type": "object"},
                    "tags": ["test"],
                },
            )
        assert resp.status_code == 201

        # Export
        resp = await client.get("/api/export-import/export/", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "test_tool"
        assert data["tools"][0]["source_code"] == "def test_tool(): pass"

    async def test_export_includes_skills(self, registered_client, mock_letta_client):
        """Export includes all user's skills."""
        client, headers, _ = registered_client

        # Create a skill
        resp = await client.post(
            "/api/skills/",
            headers=headers,
            json={
                "name": "test-skill",
                "content": "---\nname: test-skill\n---\n# Test Skill\n",
            },
        )
        assert resp.status_code == 201

        # Export
        resp = await client.get("/api/export-import/export/", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["skills"]) == 1
        assert data["skills"][0]["name"] == "test-skill"
        assert "Test Skill" in data["skills"][0]["content"]

    async def test_export_includes_workflows(self, registered_client, mock_letta_client):
        """Export includes all user's workflows."""
        client, headers, _ = registered_client

        # Create an agent first
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "test-agent")

        # Create a workflow
        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "test-workflow",
                "agent_id": agent_id,
                "prompt_template": "Hello {{name}}",
            },
        )
        assert resp.status_code == 201

        # Export
        resp = await client.get("/api/export-import/export/", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["workflows"]) == 1
        assert data["workflows"][0]["name"] == "test-workflow"
        assert data["workflows"][0]["prompt_template"] == "Hello {{name}}"
        # Agent ID should NOT be in export
        assert "agent_id" not in data["workflows"][0]

    async def test_export_workflow_references_tools_by_name(self, registered_client, mock_letta_client):
        """Workflows reference tools by name, not UUID."""
        client, headers, _ = registered_client

        # Create a tool (mock_letta_client handles Letta side)
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "my_tool",
                    "source_code": "def my_tool(): pass",
                    "json_schema": {"type": "object"},
                },
            )
        assert resp.status_code == 201
        tool_id = resp.json()["id"]

        # Create an agent
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "test-agent")

        # Create a workflow with tool
        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "workflow-with-tool",
                "agent_id": agent_id,
                "prompt_template": "Test",
                "tool_ids": [tool_id],
            },
        )
        assert resp.status_code == 201

        # Export
        resp = await client.get("/api/export-import/export/", headers=headers)
        data = resp.json()

        # Workflow should reference tool by name
        assert data["workflows"][0]["tool_names"] == ["my_tool"]
        assert "tool_ids" not in data["workflows"][0]


@pytest.mark.asyncio
class TestImport:
    """Tests for import endpoint."""

    async def test_import_empty_file(self, registered_client, mock_letta_client):
        """Import with empty data succeeds."""
        client, headers, _ = registered_client

        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [],
            "workflows": [],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["tools_imported"] == 0
        assert data["skills_imported"] == 0
        assert data["workflows_imported"] == 0

    async def test_import_skills(self, registered_client, mock_letta_client):
        """Import creates skills."""
        client, headers, _ = registered_client

        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [
                {
                    "name": "imported-skill",
                    "description": "Imported skill",
                    "content": "---\nname: imported-skill\n---\n# Imported\n",
                }
            ],
            "workflows": [],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["skills_imported"] == 1
        assert data["errors"] == []

        # Verify skill exists
        resp = await client.get("/api/skills/", headers=headers)
        skills = resp.json()
        assert any(s["name"] == "imported-skill" for s in skills)

    async def test_import_handles_name_collision(self, registered_client, mock_letta_client):
        """Import renames entities on name collision."""
        client, headers, _ = registered_client

        # Create existing skill
        resp = await client.post(
            "/api/skills/",
            headers=headers,
            json={
                "name": "existing-skill",
                "content": "---\nname: existing-skill\n---\n# Existing\n",
            },
        )
        assert resp.status_code == 201

        # Import with same name
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [
                {
                    "name": "existing-skill",
                    "content": "---\nname: existing-skill\n---\n# Imported\n",
                }
            ],
            "workflows": [],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["skills_imported"] == 1

        # Verify renamed skill exists
        resp = await client.get("/api/skills/", headers=headers)
        skills = resp.json()
        names = [s["name"] for s in skills]
        assert "existing-skill" in names
        assert "existing-skill_imported" in names

    async def test_import_tools_registers_with_letta(self, registered_client, mock_letta_client):
        """Import registers tools with Letta."""
        client, headers, _ = registered_client

        export_data = {
            "version": "1.0",
            "tools": [
                {
                    "name": "imported_tool",
                    "description": "Imported tool",
                    "source_code": "def imported_tool(): pass",
                    "json_schema": {"type": "object"},
                    "tags": ["imported"],
                }
            ],
            "skills": [],
            "workflows": [],
        }

        with patch("app.export_import.routes.register_and_store_tool", new_callable=AsyncMock) as mock_register:
            mock_register.return_value = MagicMock(id="tool-new-id")
            file_content = json.dumps(export_data).encode("utf-8")
            resp = await client.post(
                "/api/export-import/import/",
                headers=headers,
                files={"file": ("export.json", BytesIO(file_content), "application/json")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["tools_imported"] == 1
        mock_register.assert_called_once()

    async def test_import_workflows_resolves_tool_names(self, registered_client, mock_letta_client):
        """Import resolves workflow tool_names to IDs."""
        client, headers, _ = registered_client

        # Create a tool first (will be referenced by name in import)
        with patch("app.tools.helpers.get_letta_client", return_value=mock_letta_client):
            resp = await client.post(
                "/api/tools/",
                headers=headers,
                json={
                    "name": "referenced_tool",
                    "source_code": "def referenced_tool(): pass",
                    "json_schema": {"type": "object"},
                },
            )
        assert resp.status_code == 201

        # Import workflow referencing the tool by name
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [],
            "workflows": [
                {
                    "name": "workflow-with-tool",
                    "prompt_template": "Test",
                    "tool_names": ["referenced_tool"],
                    "skill_names": [],
                }
            ],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["workflows_imported"] == 1
        assert data["workflows_needing_agent"] == 1

        # Verify workflow exists with correct tool_ids
        resp = await client.get("/api/workflows/", headers=headers)
        workflows = resp.json()
        wf = next(w for w in workflows if w["name"] == "workflow-with-tool")
        assert wf["tool_ids"] is not None
        assert len(wf["tool_ids"]) == 1

    async def test_import_invalid_json_returns_400(self, registered_client, mock_letta_client):
        """Import with invalid JSON returns 400."""
        client, headers, _ = registered_client

        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(b"not json"), "application/json")},
        )

        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["detail"]

    async def test_import_unsupported_version_returns_400(self, registered_client, mock_letta_client):
        """Import with unsupported version returns 400."""
        client, headers, _ = registered_client

        export_data = {
            "version": "2.0",
            "tools": [],
            "skills": [],
            "workflows": [],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 400
        assert "Unsupported export version" in resp.json()["detail"]

    async def test_import_file_too_large_returns_413(self, registered_client, mock_letta_client):
        """Import with file > 10MB returns 413."""
        client, headers, _ = registered_client

        # Create a large export (> 10MB)
        large_content = "x" * (11 * 1024 * 1024)
        export_data = {
            "version": "1.0",
            "tools": [{"name": large_content}],  # Large field
            "skills": [],
            "workflows": [],
        }

        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 413
        assert "too large" in resp.json()["detail"].lower()


@pytest.mark.asyncio
class TestRoundTrip:
    """Tests for export -> import round trip."""

    async def test_roundtrip_preserves_data(self, registered_client, mock_letta_client):
        """Export and re-import preserves data."""
        client, headers, _ = registered_client

        # Create skill
        resp = await client.post(
            "/api/skills/",
            headers=headers,
            json={
                "name": "roundtrip-skill",
                "content": "---\nname: roundtrip-skill\n---\n# Roundtrip\n",
            },
        )
        assert resp.status_code == 201

        # Export
        resp = await client.get("/api/export-import/export/", headers=headers)
        export_data = resp.json()

        # Delete the skill
        skills = (await client.get("/api/skills/", headers=headers)).json()
        skill_id = next(s["id"] for s in skills if s["name"] == "roundtrip-skill")
        await client.delete(f"/api/skills/{skill_id}", headers=headers)

        # Import
        file_content = json.dumps(export_data).encode("utf-8")
        resp = await client.post(
            "/api/export-import/import/",
            headers=headers,
            files={"file": ("export.json", BytesIO(file_content), "application/json")},
        )

        assert resp.status_code == 200
        assert resp.json()["skills_imported"] == 1

        # Verify skill exists
        skills = (await client.get("/api/skills/", headers=headers)).json()
        assert any(s["name"] == "roundtrip-skill" for s in skills)
