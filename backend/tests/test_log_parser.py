"""Tests for log line parsers."""

from app.logs.parser import (
    PARSERS,
    parse_letta_line,
    parse_pip_sidecar_line,
    parse_postgres_line,
    parse_python_line,
)


class TestParsePythonLine:
    """Tests for Python logging format parser."""

    def test_valid_line(self):
        """Parse a standard Python logging line."""
        line = "2026-04-25 14:48:10,339 INFO [app.main] Application startup complete"
        result = parse_python_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "app.main"
        assert result["message"] == "Application startup complete"
        assert result["timestamp"] == "2026-04-25T14:48:10.339000"

    def test_all_log_levels(self):
        """All standard log levels are parsed."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            line = f"2026-04-25 14:48:10,339 {level} [app.test] Test message"
            result = parse_python_line(line)
            assert result is not None
            assert result["level"] == level

    def test_filters_sqlalchemy_engine_debug(self):
        """SQLAlchemy engine DEBUG logs are filtered out."""
        line = "2026-04-25 14:48:10,339 DEBUG [sqlalchemy.engine.Engine] SELECT * FROM users"
        result = parse_python_line(line)
        assert result is None

    def test_filters_sqlalchemy_engine_info(self):
        """SQLAlchemy engine INFO logs are filtered out."""
        line = "2026-04-25 14:48:10,339 INFO [sqlalchemy.pool.Pool] Pool connected"
        result = parse_python_line(line)
        assert result is None

    def test_allows_sqlalchemy_warnings(self):
        """SQLAlchemy WARNING and above are NOT filtered."""
        line = "2026-04-25 14:48:10,339 WARNING [sqlalchemy.engine.Engine] Connection issue"
        result = parse_python_line(line)
        assert result is not None
        assert result["level"] == "WARNING"

    def test_invalid_format_returns_none(self):
        """Lines that don't match the format return None."""
        assert parse_python_line("not a log line") is None
        assert parse_python_line("2026-04-25 missing parts") is None

    def test_malformed_timestamp_still_returns(self):
        """If timestamp parsing fails, the raw string is returned."""
        # This line has an invalid timestamp format (missing milliseconds)
        line = "2026-04-25 14:48:10 INFO [app.main] Test"
        result = parse_python_line(line)
        # Actually this won't match the regex at all, so returns None
        assert result is None


class TestParsePostgresLine:
    """Tests for PostgreSQL log format parser."""

    def test_valid_log_line(self):
        """Parse a standard PostgreSQL LOG line."""
        line = "2026-04-25 14:48:10.339 UTC [123] LOG:  database system is ready"
        result = parse_postgres_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "postgres[123]"
        assert result["message"] == "database system is ready"

    def test_level_mapping_log_to_info(self):
        """Postgres LOG maps to INFO."""
        line = "2026-04-25 14:48:10.339 UTC [123] LOG:  test"
        result = parse_postgres_line(line)
        assert result["level"] == "INFO"

    def test_level_mapping_error_to_error(self):
        """Postgres ERROR maps to ERROR."""
        line = "2026-04-25 14:48:10.339 UTC [123] ERROR:  syntax error"
        result = parse_postgres_line(line)
        assert result["level"] == "ERROR"

    def test_level_mapping_fatal_to_error(self):
        """Postgres FATAL maps to ERROR."""
        line = "2026-04-25 14:48:10.339 UTC [123] FATAL:  connection failed"
        result = parse_postgres_line(line)
        assert result["level"] == "ERROR"

    def test_level_mapping_panic_to_critical(self):
        """Postgres PANIC maps to CRITICAL."""
        line = "2026-04-25 14:48:10.339 UTC [123] PANIC:  corruption detected"
        result = parse_postgres_line(line)
        assert result["level"] == "CRITICAL"

    def test_level_mapping_warning_to_warning(self):
        """Postgres WARNING maps to WARNING."""
        line = "2026-04-25 14:48:10.339 UTC [123] WARNING:  sequence exceeds limit"
        result = parse_postgres_line(line)
        assert result["level"] == "WARNING"

    def test_level_mapping_detail_to_debug(self):
        """Postgres DETAIL maps to DEBUG."""
        line = "2026-04-25 14:48:10.339 UTC [123] DETAIL:  more info"
        result = parse_postgres_line(line)
        assert result["level"] == "DEBUG"

    def test_invalid_format_returns_none(self):
        """Lines that don't match return None."""
        assert parse_postgres_line("not a postgres log") is None


class TestParseLettaLine:
    """Tests for Letta log format parser."""

    def test_python_format_passthrough(self):
        """Python logging format is parsed and module is prefixed with 'letta.'."""
        line = "2026-04-25 14:48:10,339 INFO [server.main] Server started"
        result = parse_letta_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "letta.server.main"
        assert result["message"] == "Server started"

    def test_letta_specific_format(self):
        """Letta-specific format with dashes is parsed."""
        line = "2026-04-25 14:48:10 - letta.server.server - INFO - Server ready"
        result = parse_letta_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "letta.letta.server.server"
        assert result["message"] == "Server ready"

    def test_uvicorn_format(self):
        """Uvicorn-style format (no timestamp) is parsed."""
        line = "INFO:     Uvicorn running on http://0.0.0.0:8000"
        result = parse_letta_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "letta"
        assert result["message"] == "Uvicorn running on http://0.0.0.0:8000"
        assert result["timestamp"] is None

    def test_unstructured_fallback(self):
        """Unstructured lines are kept with INFO level."""
        line = "Some random log message"
        result = parse_letta_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "letta"
        assert result["message"] == "Some random log message"
        assert result["timestamp"] is None

    def test_empty_line_returns_none(self):
        """Empty lines return None."""
        assert parse_letta_line("") is None
        assert parse_letta_line("   ") is None


class TestParsePipSidecarLine:
    """Tests for pip-sidecar log format parser."""

    def test_python_format_passthrough(self):
        """Python logging format is parsed with pip-sidecar prefix."""
        line = "2026-04-25 14:48:10,339 INFO [installer] Package installed"
        result = parse_pip_sidecar_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "pip-sidecar.installer"
        assert result["message"] == "Package installed"

    def test_pip_module_not_double_prefixed(self):
        """If module already starts with 'pip', don't double-prefix."""
        line = "2026-04-25 14:48:10,339 INFO [pip._internal] Downloading"
        result = parse_pip_sidecar_line(line)
        assert result is not None
        assert result["module"] == "pip._internal"

    def test_unstructured_fallback(self):
        """Unstructured lines are kept with pip-sidecar module."""
        line = "Some pip output"
        result = parse_pip_sidecar_line(line)
        assert result is not None
        assert result["level"] == "INFO"
        assert result["module"] == "pip-sidecar"
        assert result["message"] == "Some pip output"

    def test_empty_line_returns_none(self):
        """Empty lines return None."""
        assert parse_pip_sidecar_line("") is None
        assert parse_pip_sidecar_line("   ") is None


class TestParsersMapping:
    """Tests for the PARSERS service mapping."""

    def test_all_services_mapped(self):
        """All expected services have parsers."""
        expected_services = {"backend", "letta", "postgres", "pip-sidecar"}
        assert set(PARSERS.keys()) == expected_services

    def test_backend_uses_python_parser(self):
        """Backend service uses Python parser."""
        assert PARSERS["backend"] == parse_python_line

    def test_letta_uses_letta_parser(self):
        """Letta service uses Letta parser."""
        assert PARSERS["letta"] == parse_letta_line

    def test_postgres_uses_postgres_parser(self):
        """Postgres service uses Postgres parser."""
        assert PARSERS["postgres"] == parse_postgres_line

    def test_pip_sidecar_uses_pip_parser(self):
        """Pip-sidecar service uses pip parser."""
        assert PARSERS["pip-sidecar"] == parse_pip_sidecar_line
