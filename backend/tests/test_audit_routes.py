"""Tests for audit log routes."""

import pytest


class TestAuditList:
    """Tests for GET /api/audit-logs/."""

    @pytest.mark.asyncio
    async def test_list_audit_logs(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/audit-logs/", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_audit_logs_scoped_to_user(self, registered_client):
        client, headers, _ = registered_client
        # New user should have no audit logs (no middleware in test app)
        resp = await client.get("/api/audit-logs/", headers=headers)
        assert resp.status_code == 200
        # The test app doesn't include AuditMiddleware, so no logs are created
        assert resp.json() == []


class TestAuditExport:
    """Tests for GET /api/audit-logs/export."""

    @pytest.mark.asyncio
    async def test_export_audit_logs_csv(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/audit-logs/export", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


class TestAuditStats:
    """Tests for GET /api/audit-logs/stats."""

    @pytest.mark.asyncio
    async def test_audit_stats(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/audit-logs/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_actions" in data
        assert "by_action" in data
