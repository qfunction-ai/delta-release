"""Tests for log line parsers."""

from app.logs.parser import (
    parse_letta_line,
    parse_pip_sidecar_line,
    parse_postgres_line,
    parse_python_line,
)


class TestParsePythonLine:
    """Tests for parse_python_line."""

    def test_standard_format(self):
        result = parse_python_line("2026-04-25 14:48:10,339 INFO [app.main] Application startup complete")
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "app.main"
        assert "Application startup" in result["message"]

    def test_warning_level(self):
        result = parse_python_line("2026-04-25 14:48:10,339 WARNING [app.auth] Token expired")
        assert result is not None
        assert result["level"] == "WARNING"

    def test_error_level(self):
        result = parse_python_line("2026-04-25 14:48:10,339 ERROR [app.db] Connection failed")
        assert result is not None
        assert result["level"] == "ERROR"

    def test_unmatched_line(self):
        result = parse_python_line("random text without format")
        assert result is None

    def test_sqlalchemy_debug_filtered(self):
        result = parse_python_line("2026-04-25 14:48:10,339 DEBUG [sqlalchemy.engine] SELECT 1")
        assert result is None

    def test_sqlalchemy_info_filtered(self):
        result = parse_python_line("2026-04-25 14:48:10,339 INFO [sqlalchemy.pool] Pool connected")
        assert result is None


class TestParsePostgresLine:
    """Tests for parse_postgres_line."""

    def test_log_level(self):
        result = parse_postgres_line("2026-04-25 14:48:10.339 UTC [123] LOG:  database system is ready")
        assert result is not None
        assert result["level"] == "INFO"
        assert "123" in result["module"]

    def test_error_level(self):
        result = parse_postgres_line("2026-04-25 14:48:10.339 UTC [456] ERROR:  relation not found")
        assert result is not None
        assert result["level"] == "ERROR"

    def test_fatal_level(self):
        result = parse_postgres_line("2026-04-25 14:48:10.339 UTC [789] FATAL:  connection refused")
        assert result is not None
        assert result["level"] == "ERROR"

    def test_unmatched_line(self):
        result = parse_postgres_line("random text")
        assert result is None


class TestParseLettaLine:
    """Tests for parse_letta_line."""

    def test_python_format(self):
        result = parse_letta_line("2026-04-25 14:48:10,339 INFO [letta.server] Server started")
        assert result is not None
        assert "letta" in result["module"]

    def test_letta_specific_format(self):
        result = parse_letta_line("2026-04-25 14:48:10 - letta.server.server - INFO - Message here")
        assert result is not None
        assert result["level"] == "INFO"

    def test_uvicorn_format(self):
        result = parse_letta_line("INFO:     Uvicorn running on http://0.0.0.0:8000")
        assert result is not None
        assert result["level"] == "INFO"
        assert result["timestamp"] is None

    def test_unstructured_line(self):
        result = parse_letta_line("Some random log message")
        assert result is not None
        assert result["level"] == "INFO"

    def test_empty_line(self):
        result = parse_letta_line("   ")
        assert result is None


class TestParsePipSidecarLine:
    """Tests for parse_pip_sidecar_line."""

    def test_python_format(self):
        result = parse_pip_sidecar_line("2026-04-25 14:48:10,339 INFO [pip._internal] Package installed")
        assert result is not None
        assert "pip" in result["module"]

    def test_unstructured_line(self):
        result = parse_pip_sidecar_line("Installing package xyz")
        assert result is not None
        assert result["module"] == "pip-sidecar"

    def test_empty_line(self):
        result = parse_pip_sidecar_line("   ")
        assert result is None
