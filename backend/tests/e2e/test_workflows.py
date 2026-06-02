"""E2E workflow tests — create, detail, update, delete, run."""

import time


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class TestWorkflowCRUD:
    """Workflow CRUD tests that create and clean up their own workflow."""

    def test_create_workflow(self, e2e_client, e2e_token_manager, e2e_agent_id, e2e_tool_id, e2e_skill_id):
        """Create a workflow with the session-scoped agent, tool, and skill."""
        name = _unique_name("e2e_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A test workflow for E2E testing",
                "agent_id": e2e_agent_id,
                "prompt_template": "Hello, this is a test workflow.",
                "tool_ids": [e2e_tool_id],
                "skill_ids": [e2e_skill_id],
            },
        )
        assert resp.status_code == 201

    def test_workflow_detail(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create a workflow, then get its detail."""
        name = _unique_name("e2e_detail_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A workflow for detail test",
                "agent_id": e2e_agent_id,
                "prompt_template": "Hello.",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Get detail
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == name

        # Clean up
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")

    def test_update_workflow(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create a workflow, then update its description."""
        name = _unique_name("e2e_update_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "Original description",
                "agent_id": e2e_agent_id,
                "prompt_template": "Hello.",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Update
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            f"/api/workflows/{wf_id}",
            json={
                "description": "Updated description",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated description"

        # Clean up
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")

    def test_delete_workflow(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create a workflow, then delete it."""
        name = _unique_name("e2e_delete_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A workflow to delete",
                "agent_id": e2e_agent_id,
                "prompt_template": "Hello.",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Delete
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
        assert resp.status_code == 204

        # Verify gone
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/workflows/{wf_id}")
        assert resp.status_code == 404

    def test_workflow_run(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Execute a workflow (best-effort — LLM timeout is acceptable in E2E)."""
        name = _unique_name("e2e_run_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A workflow to run",
                "agent_id": e2e_agent_id,
                "prompt_template": "Say hello.",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Run it
        resp = e2e_token_manager.request(e2e_client, "post", f"/api/workflows/{wf_id}/run", json={})
        # Accept 200 (success) or 503 (LLM timeout — acceptable in E2E)
        assert resp.status_code in (200, 503), f"Workflow run failed: {resp.text}"

        # Clean up
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
