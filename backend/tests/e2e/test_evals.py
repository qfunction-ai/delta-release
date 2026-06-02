"""E2E eval scenario tests — create, list, list runs."""

import time


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class TestEvalScenarios:
    def test_create_scenario(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Create an eval scenario."""
        name = _unique_name("e2e_scenario")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/evals/scenarios",
            json={
                "name": name,
                "description": "A test eval scenario",
                "agent_id": e2e_agent_id,
                "definition": {
                    "interactions": [{"input": "Hello"}],
                    "checks": [
                        {
                            "type": "StringMatching",
                            "name": "contains_hello",
                            "keyword": "hello",
                        }
                    ],
                },
            },
        )
        assert resp.status_code == 201
        self.__class__.scenario_id = resp.json()["id"]

    def test_list_scenarios(self, e2e_client, e2e_token_manager):
        """List eval scenarios includes the created one."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/evals/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        scenarios = data["scenarios"]
        assert any(s["id"] == self.__class__.scenario_id for s in scenarios)

    def test_list_eval_runs(self, e2e_client, e2e_token_manager):
        """List eval runs returns paginated results."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/evals/runs?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "runs" in data
        assert "total" in data

    def test_run_scenario(self, e2e_client, e2e_token_manager):
        """Run an eval scenario — expect 200 (success) or 503 (eval container down)."""
        scenario_id = self.__class__.scenario_id
        resp = e2e_token_manager.request(e2e_client, "post", f"/api/evals/scenarios/{scenario_id}/run")
        # Eval container may not be running in E2E — accept 503
        assert resp.status_code in (200, 503), f"Unexpected status: {resp.status_code} {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "status" in data
            assert "scenario_id" in data
