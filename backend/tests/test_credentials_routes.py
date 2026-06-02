"""Tests for credentials routes — CRUD, providers, and secret syncing."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestCredentialsCRUD:
    """Integration tests for credentials CRUD endpoints."""

    async def test_list_providers(self, registered_client, mock_letta_client):
        """GET /api/credentials/providers lists supported providers."""
        client, headers, _ = registered_client
        resp = await client.get("/api/credentials/providers", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]

    async def test_list_credential_types(self, registered_client, mock_letta_client):
        """GET /api/credentials/types lists credential types."""
        client, headers, _ = registered_client
        resp = await client.get("/api/credentials/types", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_list_credentials(self, registered_client, mock_letta_client):
        """GET /api/credentials/ lists user's credentials."""
        client, headers, _ = registered_client
        resp = await client.get("/api/credentials/", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_credential(self, registered_client, mock_letta_client):
        """POST /api/credentials/ creates a credential."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "test-api-key",
                    "name": "Test API Key",
                    "provider": "splunk",
                    "primary_key": "sk-test-key-12345",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "test-api-key"
        assert data["provider"] == "splunk"

    async def test_create_credential_with_type(self, registered_client, mock_letta_client):
        """POST /api/credentials/ creates a credential with a credential type."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "token-cred",
                    "name": "Token Cred",
                    "provider": "api_key_only",
                    "primary_key": "my-token-value",
                },
            )
        assert resp.status_code == 201

    async def test_create_credential_with_url_and_secret(self, registered_client, mock_letta_client):
        """POST /api/credentials/ creates a credential with url, primary_key, and secondary_key."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "SPLUNK_CREDS",
                    "name": "Splunk Login",
                    "provider": "splunk",
                    "url": "https://splunk.example.com:8089",
                    "primary_key": "admin",
                    "secondary_key": "changeme",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "SPLUNK_CREDS"
        assert data["provider"] == "splunk"

    async def test_create_credential_unknown_provider(self, registered_client, mock_letta_client):
        """POST /api/credentials/ rejects unknown provider."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/credentials/",
            headers=headers,
            json={
                "key": "bad-provider",
                "name": "Bad Provider",
                "provider": "nonexistent_provider",
                "primary_key": "sk-test",
            },
        )
        assert resp.status_code == 400

    async def test_create_credential_requires_url(self, registered_client, mock_letta_client):
        """POST /api/credentials/ rejects splunk without url."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/credentials/",
            headers=headers,
            json={
                "key": "no-url-cred",
                "name": "No URL",
                "provider": "splunk",
                "primary_key": "sk-test",
            },
        )
        assert resp.status_code == 400

    async def test_create_credential_requires_secret(self, registered_client, mock_letta_client):
        """POST /api/credentials/ rejects crowdstrike without secondary_key."""
        client, headers, _ = registered_client
        resp = await client.post(
            "/api/credentials/",
            headers=headers,
            json={
                "key": "no-secret-cred",
                "name": "No Secret",
                "provider": "crowdstrike",
                "primary_key": "sk-test",
                "url": "https://api.crowdstrike.com",
            },
        )
        assert resp.status_code == 400

    async def test_duplicate_key_rejected(self, registered_client, mock_letta_client):
        """Duplicate credential key returns 409."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "DUP_KEY",
                    "name": "First",
                    "provider": "splunk",
                    "url": "https://splunk.example.com:8089",
                    "primary_key": "token1",
                },
            )
            resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "DUP_KEY",
                    "name": "Second",
                    "provider": "splunk",
                    "url": "https://splunk.example.com:8089",
                    "primary_key": "token2",
                },
            )
        assert resp.status_code == 409

    async def test_get_credential(self, registered_client, mock_letta_client):
        """GET /api/credentials/{id} returns credential details."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "get-cred-key",
                    "name": "Get Cred",
                    "provider": "splunk",
                    "primary_key": "sk-test-key",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        cred_id = create_resp.json()["id"]

        resp = await client.get(f"/api/credentials/{cred_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["key"] == "get-cred-key"

    async def test_update_credential(self, registered_client, mock_letta_client):
        """PUT /api/credentials/{id} updates credential."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "update-cred-key",
                    "name": "Update Cred",
                    "provider": "splunk",
                    "primary_key": "sk-test-key",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        cred_id = create_resp.json()["id"]

        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.put(
                f"/api/credentials/{cred_id}",
                headers=headers,
                json={"name": "Updated Name"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_credential_key(self, registered_client, mock_letta_client):
        """PUT /api/credentials/{id} updates credential key."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "key-to-update",
                    "name": "Key Update",
                    "provider": "splunk",
                    "primary_key": "sk-test-key",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        cred_id = create_resp.json()["id"]

        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.put(
                f"/api/credentials/{cred_id}",
                headers=headers,
                json={"key": "new-key-name"},
            )
        assert resp.status_code == 200
        assert resp.json()["key"] == "new-key-name"

    async def test_update_credential_api_key(self, registered_client, mock_letta_client):
        """PUT /api/credentials/{id} updates primary_key."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "api-key-update",
                    "name": "API Key Update",
                    "provider": "splunk",
                    "primary_key": "sk-old-key",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        cred_id = create_resp.json()["id"]

        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.put(
                f"/api/credentials/{cred_id}",
                headers=headers,
                json={"primary_key": "sk-new-key"},
            )
        assert resp.status_code == 200

    async def test_delete_credential(self, registered_client, mock_letta_client):
        """DELETE /api/credentials/{id} deletes credential."""
        client, headers, _ = registered_client
        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/credentials/",
                headers=headers,
                json={
                    "key": "delete-cred-key",
                    "name": "Delete Cred",
                    "provider": "splunk",
                    "primary_key": "sk-test-key",
                    "url": "https://test.splunkcloud.com:8089",
                },
            )
        cred_id = create_resp.json()["id"]

        with patch("app.credentials.service.sync_credential_secrets", new_callable=AsyncMock):
            resp = await client.delete(f"/api/credentials/{cred_id}", headers=headers)
        assert resp.status_code in (200, 204)

    async def test_get_credential_not_found(self, registered_client, mock_letta_client):
        """GET /api/credentials/{id} returns 404 for nonexistent."""
        client, headers, _ = registered_client
        resp = await client.get(
            "/api/credentials/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert resp.status_code == 404
