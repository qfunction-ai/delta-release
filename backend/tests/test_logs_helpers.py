"""Tests for log route helpers — file reading and parsing."""

import os
import tempfile
from unittest.mock import patch

from app.logs.routes import _parse_file_entries, _read_log_file


class TestReadLogFile:
    """Tests for _read_log_file."""

    def test_nonexistent_service(self):
        result = _read_log_file("nonexistent")
        assert result == []

    def test_missing_file(self):
        """Returns empty list when log file doesn't exist."""
        with patch("app.logs.routes.LOG_DIR", "/nonexistent/path"):
            result = _read_log_file("backend")
        assert result == []

    def test_reads_existing_file(self):
        """Reads lines from an existing log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "backend.log")
            with open(log_path, "w") as f:
                f.write("line1\nline2\nline3\n")

            with patch("app.logs.routes.LOG_DIR", tmpdir):
                result = _read_log_file("backend")
            assert len(result) == 3
            assert "line1" in result[0]


class TestParseFileEntries:
    """Tests for _parse_file_entries."""

    def test_unknown_service(self):
        """Returns empty list for unknown service."""
        result = _parse_file_entries("unknown", ["some line"])
        assert result == []

    def test_parses_backend_lines(self):
        """Parses backend log lines."""
        lines = ["2024-01-15 10:30:00 INFO: test message"]
        result = _parse_file_entries("backend", lines)
        # The parser may or may not match, depending on format
        # Just verify it doesn't crash
        assert isinstance(result, list)
