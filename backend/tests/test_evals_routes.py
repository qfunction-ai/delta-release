"""Integration tests for eval scenario CRUD endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def _create_agent_via_api(client, headers, mock_letta_client, name="eval-agent"):
    """Helper to create an agent via the API."""
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


EVAL_SCENARIO = {
    "name": "test-scenario",
    "agent_id": None,  # Set dynamically
    "definition": {
        "interactions": [{"input": "hello"}],
        "checks": [{"type": "StringMatching", "name": "greeting", "keyword": "hello"}],
    },
}


@pytest.mark.asyncio
class TestEvalScenarioCreate:
    async def test_create_scenario(self, registered_client, mock_letta_client):
        """POST /api/evals/scenarios creates a scenario."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-create-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id}
        resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-scenario"
        assert data["agent_id"] == agent_id

    async def test_create_scenario_nonexistent_agent(self, registered_client, mock_letta_client):
        """POST /api/evals/scenarios returns 404 for nonexistent agent."""
        client, headers, _ = registered_client
        payload = {**EVAL_SCENARIO, "agent_id": "nonexistent-agent"}
        resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestEvalScenarioList:
    async def test_list_scenarios(self, registered_client, mock_letta_client):
        """GET /api/evals/scenarios lists scenarios."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-list-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id}
        await client.post("/api/evals/scenarios", headers=headers, json=payload)

        resp = await client.get("/api/evals/scenarios", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "scenarios" in data
        assert "total" in data
        assert data["total"] >= 1


@pytest.mark.asyncio
class TestEvalScenarioGet:
    async def test_get_scenario(self, registered_client, mock_letta_client):
        """GET /api/evals/scenarios/{id} returns scenario."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-get-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id}
        create_resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        scenario_id = create_resp.json()["id"]

        resp = await client.get(f"/api/evals/scenarios/{scenario_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-scenario"

    async def test_get_nonexistent_scenario(self, registered_client, mock_letta_client):
        """GET /api/evals/scenarios/{id} returns 404 for nonexistent."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/evals/scenarios/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestEvalScenarioUpdate:
    async def test_update_scenario(self, registered_client, mock_letta_client):
        """PUT /api/evals/scenarios/{id} updates scenario."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-update-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id}
        create_resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        scenario_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/evals/scenarios/{scenario_id}",
            headers=headers,
            json={"name": "updated-scenario"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "updated-scenario"


@pytest.mark.asyncio
class TestEvalScenarioDelete:
    async def test_delete_scenario(self, registered_client, mock_letta_client):
        """DELETE /api/evals/scenarios/{id} deletes scenario."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-delete-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id}
        create_resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        scenario_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/evals/scenarios/{scenario_id}", headers=headers)
        assert resp.status_code in (200, 204)

        # Verify gone
        resp = await client.get(f"/api/evals/scenarios/{scenario_id}", headers=headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestEvalRunExecution:
    async def test_run_scenario(self, registered_client, mock_letta_client):
        """POST /api/evals/scenarios/{id}/run executes a scenario."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-run-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id, "name": "run-scenario"}
        create_resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        scenario_id = create_resp.json()["id"]

        # Mock the eval container call
        mock_eval_result = {"passed": True, "details": "All checks passed"}
        with patch(
            "app.evals.routes._call_eval_container",
            new_callable=AsyncMock,
            return_value=mock_eval_result,
        ):
            resp = await client.post(
                f"/api/evals/scenarios/{scenario_id}/run",
                headers=headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "passed"

    async def test_run_scenario_eval_error(self, registered_client, mock_letta_client):
        """POST /api/evals/scenarios/{id}/run handles eval container errors."""
        client, headers, _ = registered_client
        agent_id = await _create_agent_via_api(client, headers, mock_letta_client, "eval-err-agent")

        payload = {**EVAL_SCENARIO, "agent_id": agent_id, "name": "err-scenario"}
        create_resp = await client.post("/api/evals/scenarios", headers=headers, json=payload)
        scenario_id = create_resp.json()["id"]

        # Mock the eval container call to raise an error
        from fastapi import HTTPException

        with patch(
            "app.evals.routes._call_eval_container",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=503, detail="Eval runner unavailable"),
        ):
            resp = await client.post(
                f"/api/evals/scenarios/{scenario_id}/run",
                headers=headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


@pytest.mark.asyncio
class TestEvalRunHistory:
    async def test_list_runs(self, registered_client, mock_letta_client):
        """GET /api/evals/runs returns run list."""
        client, headers, _ = registered_client
        resp = await client.get("/api/evals/runs", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data

    async def test_get_run_not_found(self, registered_client, mock_letta_client):
        """GET /api/evals/runs/{id} returns 404 for nonexistent."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/evals/runs/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestCallEvalContainer:
    """Tests for _call_eval_container helper."""

    async def test_timeout_raises_504(self):
        """TimeoutException raises 504."""
        import httpx
        from fastapi import HTTPException

        from app.evals.routes import _call_eval_container

        mock_definition = MagicMock()
        mock_definition.interactions = []
        mock_definition.checks = []
        mock_definition.route_through_backend = False
        mock_definition.settings = None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.evals.routes.get_settings") as mock_settings,
            patch("app.evals.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.eval_url = "http://eval:8000"
            mock_settings.return_value.service_token = "test-token"

            with pytest.raises(HTTPException) as exc_info:
                await _call_eval_container("test", "agent-1", mock_definition)
            assert exc_info.value.status_code == 504

    async def test_connect_error_raises_503(self):
        """ConnectError raises 503."""
        import httpx
        from fastapi import HTTPException

        from app.evals.routes import _call_eval_container

        mock_definition = MagicMock()
        mock_definition.interactions = []
        mock_definition.checks = []
        mock_definition.route_through_backend = False
        mock_definition.settings = None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.evals.routes.get_settings") as mock_settings,
            patch("app.evals.routes.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.eval_url = "http://eval:8000"
            mock_settings.return_value.service_token = "test-token"

            with pytest.raises(HTTPException) as exc_info:
                await _call_eval_container("test", "agent-1", mock_definition)
            assert exc_info.value.status_code == 503
