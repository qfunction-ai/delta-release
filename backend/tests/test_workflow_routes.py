"""Integration tests for workflow CRUD endpoints (with mocked Letta client)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _create_agent_via_api(client, headers, mock_letta_client, name="wf-agent"):
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
class TestWorkflowCreate:
    async def test_create_workflow(self, registered_client, mock_letta_client):
        """Creates a workflow with an agent reference."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "wf-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "test-workflow",
                "agent_id": agent_id,
                "prompt_template": "Search for indicators",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-workflow"
        assert data["agent_id"] == agent_id


@pytest.mark.asyncio
class TestWorkflowList:
    async def test_list_workflows(self, registered_client, mock_letta_client):
        """Lists workflows for the authenticated user."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "list-agent")

        await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "list-workflow",
                "agent_id": agent_id,
                "prompt_template": "Do something",
            },
        )

        resp = await client.get("/api/workflows/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(w["name"] == "list-workflow" for w in data)


@pytest.mark.asyncio
class TestWorkflowDelete:
    async def test_delete_workflow(self, registered_client, mock_letta_client):
        """Deletes a workflow."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "del-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "del-workflow",
                "agent_id": agent_id,
                "prompt_template": "Delete me",
            },
        )
        wf_id = resp.json()["id"]

        resp = await client.delete(f"/api/workflows/{wf_id}", headers=headers)
        assert resp.status_code in (200, 204)

        # Verify gone
        resp = await client.get("/api/workflows/", headers=headers)
        assert not any(w["id"] == wf_id for w in resp.json())


@pytest.mark.asyncio
class TestWorkflowDetail:
    async def test_get_workflow_detail(self, registered_client, mock_letta_client):
        """GET /api/workflows/{id} returns full workflow detail."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "detail-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "detail-workflow",
                "agent_id": agent_id,
                "prompt_template": "Detail me",
            },
        )
        wf_id = resp.json()["id"]

        resp = await client.get(f"/api/workflows/{wf_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "detail-workflow"


@pytest.mark.asyncio
class TestWorkflowUpdate:
    async def test_update_workflow(self, registered_client, mock_letta_client):
        """PUT /api/workflows/{id} updates workflow fields."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "update-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "update-workflow",
                "agent_id": agent_id,
                "prompt_template": "Original prompt",
            },
        )
        wf_id = resp.json()["id"]

        resp = await client.put(
            f"/api/workflows/{wf_id}",
            headers=headers,
            json={
                "name": "updated-workflow",
                "prompt_template": "Updated prompt",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated-workflow"


@pytest.mark.asyncio
class TestWorkflowValidation:
    async def test_reject_non_owned_tool_ids(self, registered_client, mock_letta_client):
        """Creating a workflow with tool_ids that don't exist returns 400."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "val-agent")

        # Use a random UUID that doesn't belong to this user
        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "bad-tool-wf",
                "agent_id": agent_id,
                "prompt_template": "Bad tools",
                "tool_ids": ["00000000-0000-0000-0000-000000000000"],
            },
        )
        # Returns 400 because the tool doesn't exist (not found in DB)
        assert resp.status_code in (400, 403)


@pytest.mark.asyncio
class TestWorkflowExecute:
    async def test_execute_workflow(self, registered_client, mock_letta_client):
        """POST /api/workflows/{id}/run executes a workflow synchronously."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "exec-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "exec-workflow",
                "agent_id": agent_id,
                "prompt_template": "Search for {{query}}",
            },
        )
        wf_id = resp.json()["id"]

        # Mock Letta response
        mock_message = MagicMock()
        mock_message.message_type = "assistant_message"
        mock_message.content = "Search complete"
        mock_response = MagicMock()
        mock_response.messages = [mock_message]
        mock_response.run_id = "letta-run-1"
        mock_response.usage = MagicMock(step_count=3)

        with (
            patch("app.letta_client.get_letta_client", return_value=mock_letta_client),
            patch(
                "app.agents.run_prep.prepare_workflow_run",
                new_callable=AsyncMock,
                return_value=("Search for test", MagicMock(), mock_letta_client),
            ),
            patch("app.workflows.routes.retry_letta_call", new_callable=AsyncMock, return_value=mock_response),
            patch("app.workflows.routes.extract_message_parts", return_value=("Search complete", None)),
            patch("app.workflows.routes.post_run_lesson_extraction", new_callable=AsyncMock),
        ):
            resp = await client.post(
                f"/api/workflows/{wf_id}/run",
                headers=headers,
                json={"variables": {"query": "test"}},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "Search complete"
        assert data["status"] == "completed"

    async def test_execute_nonexistent_workflow(self, registered_client, mock_letta_client):
        """POST /api/workflows/{id}/run returns 404 for nonexistent workflow."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/workflows/00000000-0000-0000-0000-000000000000/run",
            headers=headers,
            json={"variables": {}},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestWorkflowStream:
    async def test_stream_workflow(self, registered_client, mock_letta_client):
        """POST /api/workflows/{id}/stream returns SSE response."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "stream-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "stream-workflow",
                "agent_id": agent_id,
                "prompt_template": "Stream {{query}}",
            },
        )
        wf_id = resp.json()["id"]

        async def mock_stream_gen(*args, **kwargs):
            yield {"type": "content", "content": "Streaming result", "message_type": "assistant_message"}
            yield {"type": "status", "status": "completed"}

        mock_run = MagicMock()
        mock_run.id = "run-123"

        with (
            patch("app.letta_client.get_letta_client", return_value=mock_letta_client),
            patch(
                "app.agents.run_prep.prepare_workflow_run",
                new_callable=AsyncMock,
                return_value=("Stream test", mock_run, mock_letta_client),
            ),
            patch("app.workflows.routes.stream_letta_response", mock_stream_gen),
            patch("app.workflows.routes.post_run_lesson_extraction", new_callable=AsyncMock),
        ):
            resp = await client.post(
                f"/api/workflows/{wf_id}/stream",
                headers=headers,
                json={"variables": {"query": "test"}},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
class TestWorkflowRuns:
    async def test_list_workflow_runs(self, registered_client, mock_letta_client):
        """GET /api/workflows/{id}/runs returns run list."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "runs-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "runs-workflow",
                "agent_id": agent_id,
                "prompt_template": "Runs test",
            },
        )
        wf_id = resp.json()["id"]

        resp = await client.get(f"/api/workflows/{wf_id}/runs", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_run_not_found(self, registered_client, mock_letta_client):
        """GET /api/workflows/runs/{run_id} returns 404 for nonexistent run."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/workflows/runs/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestWorkflowSchedule:
    async def test_create_workflow_with_cron(self, registered_client, mock_letta_client):
        """Creating a workflow with schedule_cron schedules it."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "cron-agent")

        with patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock):
            resp = await client.post(
                "/api/workflows/",
                headers=headers,
                json={
                    "name": "cron-workflow",
                    "agent_id": agent_id,
                    "prompt_template": "Scheduled task",
                    "schedule_cron": "0 * * * *",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["schedule_cron"] == "0 * * * *"

    async def test_delete_workflow_removes_schedule(self, registered_client, mock_letta_client):
        """Deleting a workflow with a schedule removes the schedule."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "del-cron-agent")

        with patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock):
            resp = await client.post(
                "/api/workflows/",
                headers=headers,
                json={
                    "name": "del-cron-workflow",
                    "agent_id": agent_id,
                    "prompt_template": "Delete me",
                    "schedule_cron": "0 * * * *",
                },
            )
        wf_id = resp.json()["id"]

        with patch("app.workflows.routes.unschedule_workflow") as mock_unschedule:
            resp = await client.delete(f"/api/workflows/{wf_id}", headers=headers)
        assert resp.status_code in (200, 204)
        mock_unschedule.assert_called_once()


@pytest.mark.asyncio
class TestWorkflowUpdateSchedule:
    async def test_update_workflow_with_cron(self, registered_client, mock_letta_client):
        """PUT /api/workflows/{id} with schedule_cron reschedules."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "cron-update-agent")

        # Create workflow without schedule
        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "cron-update-wf",
                "agent_id": agent_id,
                "prompt_template": "Original",
            },
        )
        wf_id = resp.json()["id"]

        # Update with a schedule
        with (
            patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock),
        ):
            resp = await client.put(
                f"/api/workflows/{wf_id}",
                headers=headers,
                json={"schedule_cron": "0 */2 * * *"},
            )
        assert resp.status_code == 200
        assert resp.json()["schedule_cron"] == "0 */2 * * *"

    async def test_update_workflow_clear_cron_unschedules(self, registered_client, mock_letta_client):
        """PUT with explicit schedule_cron: null removes the APScheduler job."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "cron-clear-agent")

        with patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock):
            resp = await client.post(
                "/api/workflows/",
                headers=headers,
                json={
                    "name": "cron-clear-wf",
                    "agent_id": agent_id,
                    "prompt_template": "Scheduled",
                    "schedule_cron": "0 * * * *",
                },
            )
        wf_id = resp.json()["id"]

        with patch("app.workflows.routes.unschedule_workflow") as mock_unschedule:
            resp = await client.put(
                f"/api/workflows/{wf_id}",
                headers=headers,
                json={"schedule_cron": None},
            )
        assert resp.status_code == 200
        assert resp.json()["schedule_cron"] is None
        mock_unschedule.assert_called_once()

    async def test_update_workflow_absent_cron_field_no_reschedule(self, registered_client, mock_letta_client):
        """PUT without a schedule_cron key leaves the schedule untouched."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "cron-absent-agent")

        with patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock):
            resp = await client.post(
                "/api/workflows/",
                headers=headers,
                json={
                    "name": "cron-absent-wf",
                    "agent_id": agent_id,
                    "prompt_template": "Scheduled",
                    "schedule_cron": "0 * * * *",
                },
            )
        wf_id = resp.json()["id"]

        with patch("app.workflows.routes.unschedule_workflow") as mock_unschedule:
            resp = await client.put(
                f"/api/workflows/{wf_id}",
                headers=headers,
                json={"description": "updated description"},
            )
        assert resp.status_code == 200
        assert resp.json()["schedule_cron"] == "0 * * * *"
        mock_unschedule.assert_not_called()

    async def test_update_workflow_remove_cron(self, registered_client, mock_letta_client):
        """PUT /api/workflows/{id} with schedule_cron change triggers reschedule."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "cron-remove-agent")

        # Create with schedule
        with patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock):
            resp = await client.post(
                "/api/workflows/",
                headers=headers,
                json={
                    "name": "cron-remove-wf",
                    "agent_id": agent_id,
                    "prompt_template": "Scheduled",
                    "schedule_cron": "0 * * * *",
                },
            )
        wf_id = resp.json()["id"]

        # Update with a different cron — triggers reschedule
        with (
            patch("app.workflows.routes.unschedule_workflow") as mock_unschedule,
            patch("app.workflows.routes.schedule_workflow", new_callable=AsyncMock),
        ):
            resp = await client.put(
                f"/api/workflows/{wf_id}",
                headers=headers,
                json={"schedule_cron": "0 */2 * * *"},
            )
        assert resp.status_code == 200
        assert resp.json()["schedule_cron"] == "0 */2 * * *"
        mock_unschedule.assert_called_once()


@pytest.mark.asyncio
class TestWorkflowSkillValidation:
    async def test_reject_non_owned_skill_ids(self, registered_client, mock_letta_client):
        """Creating a workflow with skill_ids that don't exist returns 400."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "skill-val-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={
                "name": "bad-skill-wf",
                "agent_id": agent_id,
                "prompt_template": "Bad skills",
                "skill_ids": ["00000000-0000-0000-0000-000000000000"],
            },
        )
        assert resp.status_code in (400, 403)

    async def test_update_workflow_duplicate_name_409(self, registered_client, mock_letta_client):
        """Renaming a workflow to another workflow's name returns 409, not 500."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "dup-name-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={"name": "dup-name-first", "agent_id": agent_id, "prompt_template": "One"},
        )
        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={"name": "dup-name-second", "agent_id": agent_id, "prompt_template": "Two"},
        )
        wf2_id = resp.json()["id"]

        resp = await client.put(
            f"/api/workflows/{wf2_id}",
            headers=headers,
            json={"name": "dup-name-first"},
        )
        assert resp.status_code == 409

    async def test_update_workflow_same_name_ok(self, registered_client, mock_letta_client):
        """Updating a workflow without changing its name does not conflict."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "same-name-agent")

        resp = await client.post(
            "/api/workflows/",
            headers=headers,
            json={"name": "same-name-wf", "agent_id": agent_id, "prompt_template": "Original"},
        )
        wf_id = resp.json()["id"]

        resp = await client.put(
            f"/api/workflows/{wf_id}",
            headers=headers,
            json={"name": "same-name-wf", "description": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "same-name-wf"
