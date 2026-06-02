"""E2E scheduling tests — scheduler status, scheduled workflow CRUD."""

import time


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class TestScheduling:
    def test_scheduler_status(self, e2e_client, e2e_token_manager):
        """Scheduler status endpoint returns running state and jobs list."""
        resp = e2e_token_manager.request(e2e_client, "get", "/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "jobs_count" in data
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_create_scheduled_workflow(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create a workflow with a cron schedule, verify scheduler picks it up."""
        name = _unique_name("e2e_sched_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A scheduled workflow for E2E testing",
                "agent_id": e2e_agent_id,
                "prompt_template": "Run the daily check.",
                "schedule_cron": "0 9 * * *",
            },
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        wf_id = resp.json()["id"]

        # Check scheduler status shows the job
        resp = e2e_token_manager.request(e2e_client, "get", "/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        job_wf_ids = [j["workflow_id"] for j in data["jobs"]]
        assert str(wf_id) in job_wf_ids

        # Clean up
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
        assert resp.status_code == 204

    def test_unschedule_on_delete(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Deleting a scheduled workflow removes it from the scheduler."""
        name = _unique_name("e2e_unsched_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "A workflow to unschedule",
                "agent_id": e2e_agent_id,
                "prompt_template": "Run the check.",
                "schedule_cron": "0 9 * * 1",
            },
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        wf_id = resp.json()["id"]

        # Verify it's scheduled
        resp = e2e_token_manager.request(e2e_client, "get", "/scheduler/status")
        job_wf_ids = [j["workflow_id"] for j in resp.json()["jobs"]]
        assert str(wf_id) in job_wf_ids

        # Delete the workflow
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
        assert resp.status_code == 204

        # Verify it's no longer scheduled
        resp = e2e_token_manager.request(e2e_client, "get", "/scheduler/status")
        job_wf_ids = [j["workflow_id"] for j in resp.json()["jobs"]]
        assert str(wf_id) not in job_wf_ids
