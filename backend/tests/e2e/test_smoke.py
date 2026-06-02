"""E2E smoke tests — critical path coverage against live Docker stack.

Run with: DELTA_E2E=1 python -m pytest tests/e2e/ -v
"""

import uuid


class TestHealthCheck:
    def test_backend_healthy(self, e2e_client):
        """Backend health endpoint returns 200."""
        resp = e2e_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestRegistrationAndLogin:
    def test_setup_status(self, e2e_client):
        """Setup status endpoint returns valid response."""
        resp = e2e_client.get("/api/auth/setup-status")
        assert resp.status_code == 200
        assert "needs_setup" in resp.json()

    def test_me_with_token(self, e2e_client, e2e_token_manager):
        """Auth /me returns user info."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "username" in data
        assert data["role"] == "admin"


class TestDashboard:
    def test_dashboard(self, e2e_client, e2e_token_manager):
        """Dashboard returns health and stats."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/dashboard/")
        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data
        assert "stats" in data
        assert "agents" in data["stats"]


class TestAgentCRUD:
    def test_create_and_list_agent(self, e2e_client, e2e_token_manager):
        """Create an agent and verify it appears in the list."""
        # Create
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/agents/",
            json={
                "name": f"e2e-smoke-agent-{uuid.uuid4().hex[:6]}",
                "model": "ollama/gemma4:latest",
                "embedding": "ollama/embeddinggemma:latest",
            },
        )
        assert resp.status_code == 201
        agent_id = resp.json()["id"]

        # List
        resp = e2e_token_manager.request(e2e_client, "get", "/api/agents/")
        assert resp.status_code == 200
        agents = resp.json()
        assert any(a["id"] == agent_id for a in agents)


class TestCredentialCRUD:
    def test_create_and_list_credential(self, e2e_client, e2e_token_manager):
        """Create a credential and verify it appears in the list."""
        unique_key = f"E2E_SMOKE_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "E2E Test Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "e2e-test-key",
                "secondary_key": "e2e-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # List
        resp = e2e_token_manager.request(e2e_client, "get", "/api/credentials/")
        assert resp.status_code == 200
        creds = resp.json()
        assert any(c["id"] == cred_id for c in creds)
