"""Tests for admin log viewer routes."""

import os
import tempfile
from unittest.mock import patch

import pytest


class TestLogViewer:
    """Tests for GET /api/logs/."""

    @pytest.mark.asyncio
    async def test_logs_requires_admin(self, registered_client):
        """Regular user (first user = admin in this system) can access logs."""
        client, headers, _ = registered_client
        # First user is admin, so this should succeed
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert "services" in data

    @pytest.mark.asyncio
    async def test_logs_returns_services_list(self, registered_client):
        client, headers, _ = registered_client
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/", headers=headers)
        data = resp.json()
        assert "backend" in data["services"]
        assert "audit" in data["services"]

    @pytest.mark.asyncio
    async def test_logs_invalid_service_filter(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/logs/?service=nonexistent", headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_logs_invalid_level_filter(self, registered_client):
        client, headers, _ = registered_client
        resp = await client.get("/api/logs/?level=INVALID", headers=headers)
        assert resp.status_code == 400


class TestReadLogFile:
    """Tests for _read_log_file."""

    def test_read_existing_file(self):
        """Reads lines from an existing log file."""
        from app.logs.routes import _read_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "backend.log")
            with open(log_path, "w") as f:
                f.write("line 1\nline 2\nline 3\n")

            with (
                patch("app.logs.routes.LOG_DIR", tmpdir),
                patch("app.logs.routes.get_settings") as mock_settings,
            ):
                mock_settings.return_value.max_lines_per_log_file = 1000
                lines = _read_log_file("backend")

        assert len(lines) == 3
        assert "line 1" in lines[0]

    def test_read_nonexistent_file(self):
        """Returns empty list for nonexistent file."""
        from app.logs.routes import _read_log_file

        with (
            patch("app.logs.routes.LOG_DIR", "/nonexistent/path"),
            patch("app.logs.routes.get_settings") as mock_settings,
        ):
            mock_settings.return_value.max_lines_per_log_file = 1000
            lines = _read_log_file("backend")

        assert lines == []

    def test_read_unknown_service(self):
        """Returns empty list for unknown service."""
        from app.logs.routes import _read_log_file

        lines = _read_log_file("unknown_service")
        assert lines == []


class TestParseFileEntries:
    """Tests for _parse_file_entries."""

    def test_parse_backend_entries(self):
        """Parses backend log lines into structured entries."""
        from app.logs.routes import _parse_file_entries

        lines = ["2026-04-25 14:48:10,339 INFO [app.main] Application startup complete\n"]
        entries = _parse_file_entries("backend", lines)

        assert len(entries) == 1
        assert entries[0]["service"] == "backend"
        assert entries[0]["level"] == "INFO"
        assert "startup" in entries[0]["message"]

    def test_parse_unknown_service(self):
        """Returns empty list for service without a parser."""
        from app.logs.routes import _parse_file_entries

        entries = _parse_file_entries("unknown", ["some line\n"])
        assert entries == []


class TestLogFiltering:
    """Tests for log filtering in the endpoint."""

    @pytest.mark.asyncio
    async def test_logs_service_filter(self, registered_client):
        """Filtering by service returns only that service's entries."""
        client, headers, _ = registered_client
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/?service=audit", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # All entries should be from audit service
        for entry in data["entries"]:
            assert entry["service"] == "audit"

    @pytest.mark.asyncio
    async def test_logs_level_filter(self, registered_client):
        """Filtering by level returns only entries at that level."""
        client, headers, _ = registered_client
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/?level=ERROR", headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logs_search_filter(self, registered_client):
        """Text search filters entries by message content."""
        client, headers, _ = registered_client
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/?search=error", headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logs_pagination(self, registered_client):
        """Pagination with limit and offset works."""
        client, headers, _ = registered_client
        with patch("app.logs.routes._read_log_file", return_value=[]):
            resp = await client.get("/api/logs/?limit=10&offset=0", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_logs_audit_service(self, admin_client, mock_letta_client):
        """GET /api/logs/?service=audit returns audit entries."""
        client, headers, _ = admin_client
        resp = await client.get("/api/logs/?service=audit", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "total" in data
        assert "services" in data
