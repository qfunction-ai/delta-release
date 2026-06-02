"""E2E audit log tests — list logs, stats."""


class TestAuditLogs:
    def test_list_audit_logs(self, e2e_client, e2e_token_manager):
        """List audit logs returns paginated results."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/audit-logs/?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_audit_stats(self, e2e_client, e2e_token_manager):
        """Audit stats endpoint returns summary data."""
        resp = e2e_token_manager.request(e2e_client, "get", "/api/audit-logs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "by_action" in data or "by_resource" in data
