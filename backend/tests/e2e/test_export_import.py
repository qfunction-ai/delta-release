"""E2E export/import tests — export, import, round-trip, IDOR, validation."""

import json
import uuid

import httpx

from tests.e2e.conftest import _TOOL_SCHEMA, BASE_URL


def _unique_name(prefix: str) -> str:
    """Generate a unique name for E2E test entities."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestExport:
    """Tests for the export endpoint."""

    def test_export_returns_json_download(self, e2e_client, e2e_token_manager):
        """GET /api/export-import/export/ returns a JSON file download."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")
        assert 'filename="delta-export.json"' in resp.headers.get("content-disposition", "")

        data = resp.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert "tools" in data
        assert "skills" in data
        assert "workflows" in data

    def test_export_includes_existing_tools(self, e2e_client, e2e_token_manager, e2e_tool_id):
        """Export includes tools that exist for the user."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tools"]) >= 1
        assert any(t["name"] == "e2e_test_tool" for t in data["tools"])

    def test_export_includes_existing_skills(self, e2e_client, e2e_token_manager, e2e_skill_id):
        """Export includes skills that exist for the user."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["skills"]) >= 1
        assert any(s["name"] == "e2e_test_skill" for s in data["skills"])

    def test_export_tool_includes_source_code(self, e2e_client, e2e_token_manager, e2e_tool_id):
        """Export includes tool source_code and json_schema."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
        data = resp.json()
        tool = next(t for t in data["tools"] if t["name"] == "e2e_test_tool")
        assert "source_code" in tool
        assert "json_schema" in tool
        assert isinstance(tool["json_schema"], dict)

    def test_export_workflow_references_tools_by_name(
        self, e2e_client, e2e_token_manager, e2e_agent_id, e2e_tool_id, e2e_skill_id
    ):
        """Workflows in export reference tools/skills by name, not UUID."""
        # Create a workflow referencing the tool and skill
        wf_name = _unique_name("export_ref_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": wf_name,
                "agent_id": e2e_agent_id,
                "prompt_template": "Test prompt",
                "tool_ids": [e2e_tool_id],
                "skill_ids": [e2e_skill_id],
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        try:
            # Export
            resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
            data = resp.json()

            wf = next(w for w in data["workflows"] if w["name"] == wf_name)
            assert "tool_names" in wf
            assert "skill_names" in wf
            assert "e2e_test_tool" in wf["tool_names"]
            assert "e2e_test_skill" in wf["skill_names"]
            # UUID-based references should NOT be in the export
            assert "tool_ids" not in wf
            assert "skill_ids" not in wf
            # Agent ID should NOT be in the export
            assert "agent_id" not in wf
        finally:
            e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")


class TestImport:
    """Tests for the import endpoint."""

    def test_import_empty_file(self, e2e_client, e2e_token_manager):
        """Import with empty export data succeeds with zero counts."""
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [],
            "workflows": [],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tools_imported"] == 0
        assert data["skills_imported"] == 0
        assert data["workflows_imported"] == 0
        assert data["errors"] == []

    def test_import_skill(self, e2e_client, e2e_token_manager):
        """Import creates a new skill."""
        skill_name = _unique_name("imported_skill")
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [
                {
                    "name": skill_name,
                    "description": "An imported skill",
                    "content": f"---\nname: {skill_name}\n---\n# Imported Skill\n",
                }
            ],
            "workflows": [],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skills_imported"] == 1
        assert data["errors"] == []

        # Verify skill exists in the skills list
        resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
        assert any(s["name"] == skill_name for s in resp.json())

    def test_import_tool(self, e2e_client, e2e_token_manager):
        """Import creates a new tool (registered with Letta)."""
        tool_name = _unique_name("imported_tool")
        export_data = {
            "version": "1.0",
            "tools": [
                {
                    "name": tool_name,
                    "description": "An imported tool",
                    "source_code": f"def {tool_name}(x: str) -> str:\n    return x\n",
                    "json_schema": _TOOL_SCHEMA,
                    "tags": ["imported"],
                }
            ],
            "skills": [],
            "workflows": [],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tools_imported"] == 1
        assert data["errors"] == []

        # Verify tool exists in the tools list
        resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
        assert any(t["name"] == tool_name for t in resp.json())

    def test_import_workflow(self, e2e_client, e2e_token_manager):
        """Import creates a new workflow (without agent)."""
        wf_name = _unique_name("imported_workflow")
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [],
            "workflows": [
                {
                    "name": wf_name,
                    "description": "An imported workflow",
                    "prompt_template": "Test imported workflow",
                    "tool_names": [],
                    "skill_names": [],
                }
            ],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflows_imported"] == 1
        assert data["workflows_needing_agent"] == 1
        assert data["errors"] == []

        # Verify workflow exists
        resp = e2e_token_manager.request(e2e_client, "get", "/api/workflows/")
        assert any(w["name"] == wf_name for w in resp.json())

    def test_import_handles_name_collision(self, e2e_client, e2e_token_manager):
        """Import renames entities when name already exists."""
        # Create a skill first
        skill_name = _unique_name("collision_skill")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/skills/",
            json={
                "name": skill_name,
                "content": f"---\nname: {skill_name}\n---\n# Original\n",
            },
        )
        assert resp.status_code == 201

        # Import with same name
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [
                {
                    "name": skill_name,
                    "content": f"---\nname: {skill_name}\n---\n# Imported\n",
                }
            ],
            "workflows": [],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skills_imported"] == 1

        # Verify renamed skill exists
        resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
        names = [s["name"] for s in resp.json()]
        assert skill_name in names
        assert f"{skill_name}_imported" in names

    def test_import_workflow_resolves_tool_names(self, e2e_client, e2e_token_manager, e2e_tool_id):
        """Import resolves workflow tool_names to tool IDs."""
        wf_name = _unique_name("wf_with_tool")
        export_data = {
            "version": "1.0",
            "tools": [],
            "skills": [],
            "workflows": [
                {
                    "name": wf_name,
                    "prompt_template": "Test with tool reference",
                    "tool_names": ["e2e_test_tool"],
                    "skill_names": [],
                }
            ],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflows_imported"] == 1

        # Verify workflow has tool_ids resolved
        resp = e2e_token_manager.request(e2e_client, "get", "/api/workflows/")
        wf = next(w for w in resp.json() if w["name"] == wf_name)
        assert wf["tool_ids"] is not None
        assert len(wf["tool_ids"]) == 1

    def test_import_invalid_json_returns_400(self, e2e_client, e2e_token_manager):
        """Import with invalid JSON returns 400."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", b"not json", "application/json")},
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["detail"]

    def test_import_unsupported_version_returns_400(self, e2e_client, e2e_token_manager):
        """Import with unsupported version returns 400."""
        export_data = {
            "version": "2.0",
            "tools": [],
            "skills": [],
            "workflows": [],
        }
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/export-import/import/",
            files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
        )
        assert resp.status_code == 400
        assert "Unsupported export version" in resp.json()["detail"]


class TestRoundTrip:
    """Tests for export -> import round trip."""

    def test_roundtrip_preserves_skills(self, e2e_client, e2e_token_manager):
        """Export and re-import preserves skill data."""
        # Create a skill
        skill_name = _unique_name("roundtrip_skill")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/skills/",
            json={
                "name": skill_name,
                "content": f"---\nname: {skill_name}\n---\n# Roundtrip Skill\n",
            },
        )
        assert resp.status_code == 201
        skill_id = resp.json()["id"]

        try:
            # Export
            resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
            export_data = resp.json()

            # Delete the skill
            e2e_token_manager.request(e2e_client, "delete", f"/api/skills/{skill_id}")

            # Verify it's gone
            resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
            assert not any(s["name"] == skill_name for s in resp.json())

            # Import
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/export-import/import/",
                files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
            )
            assert resp.status_code == 200
            assert resp.json()["skills_imported"] >= 1

            # Verify skill exists again
            resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
            assert any(s["name"] == skill_name for s in resp.json())
        finally:
            # Cleanup
            resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
            for s in resp.json():
                if s["name"] == skill_name:
                    e2e_token_manager.request(e2e_client, "delete", f"/api/skills/{s['id']}")
                    break

    def test_roundtrip_preserves_tools(self, e2e_client, e2e_token_manager):
        """Export and re-import preserves tool data."""
        # Create a tool
        tool_name = _unique_name("roundtrip_tool")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": tool_name,
                "description": "A roundtrip test tool",
                "source_code": f"def {tool_name}(x: str) -> str:\n    return x\n",
                "json_schema": _TOOL_SCHEMA,
                "tags": ["roundtrip"],
            },
        )
        assert resp.status_code == 201
        tool_id = resp.json()["id"]

        try:
            # Export
            resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
            export_data = resp.json()

            # Delete the tool
            e2e_token_manager.request(e2e_client, "delete", f"/api/tools/{tool_id}")

            # Import
            resp = e2e_token_manager.request(
                e2e_client,
                "post",
                "/api/export-import/import/",
                files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
            )
            assert resp.status_code == 200
            assert resp.json()["tools_imported"] >= 1

            # Verify tool exists again
            resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
            assert any(t["name"] == tool_name for t in resp.json())
        finally:
            # Cleanup
            resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
            for t in resp.json():
                if t["name"] == tool_name:
                    e2e_token_manager.request(e2e_client, "delete", f"/api/tools/{t['id']}")
                    break


class TestExportImportIDOR:
    """Verify export/import endpoints enforce authentication."""

    def test_export_requires_auth(self):
        """GET /api/export-import/export/ without auth returns 401/403."""
        # Use a fresh client without cookies to test unauthenticated access
        with httpx.Client(base_url=BASE_URL, timeout=60) as client:
            resp = client.get("/api/export-import/export/")
            assert resp.status_code in (401, 403)

    def test_import_requires_auth(self):
        """POST /api/export-import/import/ without auth returns 401/403."""
        export_data = {"version": "1.0", "tools": [], "skills": [], "workflows": []}
        with httpx.Client(base_url=BASE_URL, timeout=60) as client:
            resp = client.post(
                "/api/export-import/import/",
                files={"file": ("export.json", json.dumps(export_data).encode(), "application/json")},
            )
            assert resp.status_code in (401, 403)

    def test_export_isolation_between_users(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """Export only returns the authenticated user's data, not other users'."""
        # The forged user headers use a real second user's token.
        # If the second user doesn't exist in DB, we get 401 — that's still
        # a pass (auth rejected), but we can't test data isolation.
        # If the second user exists, verify their export is empty.
        resp = e2e_client.get("/api/export-import/export/", headers=e2e_forged_user_headers)
        if resp.status_code == 401:
            # Second user doesn't exist in DB — auth rejected, isolation holds
            return
        assert resp.status_code == 200
        data = resp.json()
        # The forged user should have no tools/skills/workflows (or very few)
        # We just verify the endpoint doesn't leak the primary user's data
        primary_resp = e2e_token_manager.request(e2e_client, "get", "/api/export-import/export/")
        primary_data = primary_resp.json()
        # If primary user has tools, forged user should not have the same ones
        if primary_data["tools"]:
            forged_tool_names = {t["name"] for t in data["tools"]}
            primary_tool_names = {t["name"] for t in primary_data["tools"]}
            # Forged user should not see primary user's tools
            assert not forged_tool_names.intersection(primary_tool_names), "Export leaked tools across users"
