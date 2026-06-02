"""E2E full pipeline test — agent → tool → skill → workflow chain."""

import time


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


class TestFullPipeline:
    def test_agent_tool_skill_workflow_chain(
        self, e2e_client, e2e_token_manager, e2e_agent_id, e2e_tool_id, e2e_skill_id
    ):
        """Verify all session-scoped resources exist and can be listed."""
        # Agent
        resp = e2e_token_manager.request(e2e_client, "get", "/api/agents/")
        assert resp.status_code == 200
        agents = resp.json()
        assert any(a["letta_agent_id"] == e2e_agent_id for a in agents)

        # Tool
        resp = e2e_token_manager.request(e2e_client, "get", "/api/tools/")
        assert resp.status_code == 200
        tools = resp.json()
        assert any(t["id"] == e2e_tool_id for t in tools)

        # Skill
        resp = e2e_token_manager.request(e2e_client, "get", "/api/skills/")
        assert resp.status_code == 200
        skills = resp.json()
        assert any(s["id"] == e2e_skill_id for s in skills)

        # Create a workflow linking all three
        name = _unique_name("e2e_pipeline_wf")
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": name,
                "description": "Full pipeline test workflow",
                "agent_id": e2e_agent_id,
                "prompt_template": "Use the tool and skill to complete the task.",
                "tool_ids": [e2e_tool_id],
                "skill_ids": [e2e_skill_id],
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Verify the workflow references all resources
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        wf = resp.json()
        assert wf["agent_id"] == e2e_agent_id
        assert e2e_tool_id in wf.get("tool_ids", [])
        assert e2e_skill_id in wf.get("skill_ids", [])

        # Clean up
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
