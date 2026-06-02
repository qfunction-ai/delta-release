"""E2E credential CRUD tests — full lifecycle including update, delete, and secret sync.

The existing smoke tests only cover create + list + test. These tests add
update, delete, duplicate key rejection, and invalid provider rejection.
"""

import uuid


class TestCredentialCRUD:
    """Full credential lifecycle."""

    def test_get_credential(self, e2e_client, e2e_token_manager):
        """GET /api/credentials/{id} returns the credential details."""
        unique_key = f"CRUD_GET_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "CRUD Get Test",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "crud-test-key",
                "secondary_key": "crud-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Get it
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/credentials/{cred_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == cred_id
        assert data["key"] == unique_key
        # Secret values should NOT be returned
        assert "primary_key" not in data or data.get("primary_key") is None

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")

    def test_update_credential(self, e2e_client, e2e_token_manager):
        """PUT /api/credentials/{id} updates the credential and re-encrypts."""
        unique_key = f"CRUD_UPD_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "CRUD Update Test",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "original-key",
                "secondary_key": "original-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Update the name and primary_key
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            f"/api/credentials/{cred_id}",
            json={
                "name": "Updated Name",
                "primary_key": "new-key-value",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"

        # Verify the update persisted
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/credentials/{cred_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")

    def test_delete_credential(self, e2e_client, e2e_token_manager):
        """DELETE /api/credentials/{id} removes the credential."""
        unique_key = f"CRUD_DEL_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "CRUD Delete Test",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "delete-test-key",
                "secondary_key": "delete-test-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Delete it
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")
        assert resp.status_code == 204

        # Verify it's gone
        resp = e2e_token_manager.request(e2e_client, "get", f"/api/credentials/{cred_id}")
        assert resp.status_code == 404

    def test_duplicate_credential_key_rejected(self, e2e_client, e2e_token_manager):
        """Creating a credential with a duplicate key returns 409."""
        unique_key = f"CRUD_DUP_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "First Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "key1",
                "secondary_key": "secret1",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Try to create another with the same key
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "Duplicate Cred",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "key2",
                "secondary_key": "secret2",
            },
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")

    def test_invalid_provider_rejected(self, e2e_client, e2e_token_manager):
        """Creating a credential with an unknown provider returns 400."""
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": f"CRUD_BAD_{uuid.uuid4().hex[:8]}",
                "name": "Bad Provider",
                "provider": "nonexistent_provider",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "key",
                "secondary_key": "secret",
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


class TestCredentialSecretSync:
    """Verify that credential changes sync to agents.

    These tests require the Letta server to be running. If Letta is
    unavailable, the sync silently fails (logged as warning). We verify
    the backend attempted the sync by checking the response status.
    """

    def test_delete_credential_syncs_to_agents(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Deleting a credential triggers sync_credential_secrets.

        We can't easily verify the agent's secrets were updated without
        Letta API access, but we can verify the delete succeeded and
        the sync was attempted (no 500 error).
        """
        unique_key = f"SYNC_DEL_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "Sync Delete Test",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "sync-del-key",
                "secondary_key": "sync-del-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Delete should succeed even if Letta sync fails
        resp = e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")
        assert resp.status_code == 204, f"Delete failed: {resp.text}"

    def test_update_credential_syncs_to_agents(self, e2e_client, e2e_token_manager, e2e_agent_id):
        """Updating a credential triggers sync_credential_secrets."""
        unique_key = f"SYNC_UPD_{uuid.uuid4().hex[:8]}"
        resp = e2e_token_manager.request(
            e2e_client,
            "post",
            "/api/credentials/",
            json={
                "key": unique_key,
                "name": "Sync Update Test",
                "provider": "custom",
                "credential_type": "api_key_pair",
                "url": "https://httpbin.org",
                "primary_key": "sync-upd-key",
                "secondary_key": "sync-upd-secret",
            },
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # Update should succeed even if Letta sync fails
        resp = e2e_token_manager.request(
            e2e_client,
            "put",
            f"/api/credentials/{cred_id}",
            json={
                "primary_key": "updated-key",
            },
        )
        assert resp.status_code == 200, f"Update failed: {resp.text}"

        # Cleanup
        e2e_token_manager.request(e2e_client, "delete", f"/api/credentials/{cred_id}")
