"""E2E admin enforcement tests — verify admin-only endpoints reject non-admin users.

The first registered user is admin. These tests forge a JWT with role="user"
and verify that admin-only endpoints return 403.
"""


class TestPackageAdminEnforcement:
    """Package management endpoints require admin role."""

    def test_install_packages_requires_admin(self, e2e_client, e2e_non_admin_headers):
        """POST /api/tools/packages/install with non-admin token returns 403."""
        resp = e2e_client.post(
            "/api/tools/packages/install",
            json={
                "packages": [{"name": "requests"}],
            },
            headers=e2e_non_admin_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"

    def test_delete_package_requires_admin(self, e2e_client, e2e_non_admin_headers):
        """DELETE /api/tools/packages/{name} with non-admin token returns 403."""
        resp = e2e_client.delete("/api/tools/packages/nonexistent", headers=e2e_non_admin_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


class TestLogsAdminEnforcement:
    """Logs viewer requires admin role."""

    def test_logs_requires_admin(self, e2e_client, e2e_non_admin_headers):
        """GET /api/logs/ with non-admin token returns 403."""
        resp = e2e_client.get("/api/logs/", headers=e2e_non_admin_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


class TestSchedulerStatusAdminOnly:
    """Scheduler status requires admin role."""

    def test_scheduler_status_requires_admin(self, e2e_client, e2e_non_admin_headers):
        """GET /scheduler/status with non-admin token returns 403."""
        resp = e2e_client.get("/scheduler/status", headers=e2e_non_admin_headers)
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
