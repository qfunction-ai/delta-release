"""E2E IDOR tests — verify cross-user access control.

Every resource type uses get_owned_or_404 to enforce ownership, but
this was never tested end-to-end. These tests forge a valid JWT for
a non-existent user and verify that accessing another user's resources
returns 403 or 404.
"""

import uuid


class TestAgentIDOR:
    """Verify agents are scoped to their owner."""

    def test_get_agent_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers, e2e_agent_id):
        """GET /api/agents/{id} with a different user's token returns 403/404."""
        # First, get the agent's DB id from the list
        resp = e2e_token_manager.request(e2e_client, "get", "/api/agents/")
        assert resp.status_code == 200
        agents = resp.json()
        agent = next((a for a in agents if a["letta_agent_id"] == e2e_agent_id), None)
        assert agent is not None, "Agent not found in list"
        agent_id = agent["id"]

        # Now try to access it with the forged user's token
        resp = e2e_client.get(f"/api/agents/{agent_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

    def test_delete_agent_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """DELETE /api/agents/{id} with a different user's token returns 403/404."""
        # Create a throwaway agent
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/agents/",
            json={
                "name": f"idor-agent-{uuid.uuid4().hex[:6]}",
                "model": "ollama/gemma4:latest",
                "embedding": "ollama/embeddinggemma:latest",
            },
        )
        assert resp.status_code == 201
        agent_id = resp.json()["id"]

        # Try to delete it with the forged user's token
        resp = e2e_client.delete(f"/api/agents/{agent_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup: delete with the real owner's token
        e2e_token_manager.request(e2e_client, "delete", f"/api/agents/{agent_id}")


class TestCredentialIDOR:
    """Verify credentials are scoped to their owner."""

    def test_get_credential_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """GET /api/credentials/{id} with a different user's token returns 403/404."""
        # Create a credential
        unique_key = f"IDOR_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "IDOR Test Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "idor-test-key",
                "secondary_key": "idor-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Try to access it with the forged user's token
        resp = e2e_client.get(f"/api/credentials/{cred_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")

    def test_update_credential_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """PUT /api/credentials/{id} with a different user's token returns 403/404."""
        unique_key = f"IDOR_PUT_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "IDOR Update Test Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "idor-test-key",
                "secondary_key": "idor-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Try to update it with the forged user's token
        resp = e2e_client.put(
            f"/api/credentials/{cred_id}",
            headers=e2e_forged_user_headers,
            json={
                "name": "Tampered Name",
            },
        )
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")

    def test_delete_credential_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """DELETE /api/credentials/{id} with a different user's token returns 403/404."""
        unique_key = f"IDOR_DEL_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "IDOR Delete Test Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "idor-test-key",
                "secondary_key": "idor-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Try to delete it with the forged user's token
        resp = e2e_client.delete(f"/api/credentials/{cred_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")


class TestToolIDOR:
    """Verify tools are scoped to their owner."""

    def test_delete_tool_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers):
        """DELETE /api/tools/{id} with a different user's token returns 403/404."""
        # Create a throwaway tool
        name = f"idor_tool_{uuid.uuid4().hex[:6]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/tools/",
            json={
                "name": name,
                "description": "IDOR test tool",
                "source_code": f"def {name}(x: str) -> str:\n    return x",
                "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            },
        )
        assert resp.status_code == 201
        tool_id = resp.json()["id"]

        # Try to delete it with the forged user's token
        resp = e2e_client.delete(f"/api/tools/{tool_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/tools/{tool_id}")


class TestWorkflowIDOR:
    """Verify workflows are scoped to their owner."""

    def test_get_workflow_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers, e2e_agent_id):
        """GET /api/workflows/{id} with a different user's token returns 403/404."""
        # Create a throwaway workflow (no template variables — avoids sanitizer bug)
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": f"idor-workflow-{uuid.uuid4().hex[:6]}",
                "agent_id": e2e_agent_id,
                "prompt_template": "Test IDOR workflow prompt",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Try to access it with the forged user's token
        resp = e2e_client.get(f"/api/workflows/{wf_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")

    def test_delete_workflow_wrong_user(self, e2e_client, e2e_token_manager, e2e_forged_user_headers, e2e_agent_id):
        """DELETE /api/workflows/{id} with a different user's token returns 403/404."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/workflows/",
            json={
                "name": f"idor-del-workflow-{uuid.uuid4().hex[:6]}",
                "agent_id": e2e_agent_id,
                "prompt_template": "Test IDOR delete workflow prompt",
            },
        )
        assert resp.status_code == 201
        wf_id = resp.json()["id"]

        # Try to delete it with the forged user's token
        resp = e2e_client.delete(f"/api/workflows/{wf_id}", headers=e2e_forged_user_headers)
        assert resp.status_code in (403, 404), f"Expected 403/404, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/workflows/{wf_id}")
