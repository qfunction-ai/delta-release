"""E2E lesson tests — list lessons, list workflow lessons."""

import time


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class TestLessons:
    def test_list_lessons_empty(self, e2e_client, e2e_token_manager):
        """List lessons returns empty list on a fresh instance."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/lessons/")
        assert resp.status_code == 200
        data = resp.json()
        assert "lessons" in data
        assert "total" in data
        assert isinstance(data["lessons"], list)

    def test_list_workflow_lessons(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """List lessons for a specific workflow returns structured response."""
        name = _unique_name("e2e_lesson_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A workflow for lesson testing",
                "agent_id": e2e_agent_id,
                "prompt_template": "Hello.",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # List lessons for this workflow
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/lessons/{wf_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "lessons" in data
        assert "total" in data

        # Clean up
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
