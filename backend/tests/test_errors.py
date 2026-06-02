"""Tests for error handling utilities."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.errors import letta_error_detail, safe_error, sanitize_error_detail


class TestSafeError:
    """Tests for safe_error."""

    def test_returns_generic_message(self):
        result = safe_error("Internal database connection failed", "internal")
        assert result == "An internal error occurred. Please try again later."

    def test_letta_category(self):
        result = safe_error("Letta API timeout", "letta")
        assert result == "Failed to communicate with the AI service. Please try again later."

    def test_unknown_category_defaults_to_internal(self):
        result = safe_error("Something broke", "unknown")
        assert result == "An internal error occurred. Please try again later."


class TestLettaErrorDetail:
    """Tests for letta_error_detail."""

    def test_parse_error_passed_through(self):
        """Parse errors are user-actionable and passed through."""
        result = letta_error_detail(Exception("JSON parse error at line 5"))
        assert "parse" in result.lower()

    def test_syntax_error_passed_through(self):
        """Syntax errors are user-actionable and passed through."""
        result = letta_error_detail(Exception("Syntax error in tool code"))
        assert "syntax" in result.lower()

    def test_other_error_sanitized(self):
        """Non-parse/syntax/400 errors are sanitized."""
        result = letta_error_detail(Exception("Connection refused to internal host"))
        assert "Connection refused" not in result


class TestCallLettaBadRequest:
    """Tests for call_letta handling BadRequestError as 400."""

    @pytest.mark.asyncio
    async def test_bad_request_returns_400(self):
        """BadRequestError from Letta should raise HTTPException with 400, not 503."""
        from letta_client import BadRequestError

        from app.letta_client import call_letta

        # Create a mock BadRequestError by patching run_sync to raise one
        mock_response = MagicMock()
        mock_response.request = MagicMock()

        with patch(
            "app.letta_client.run_sync",
            side_effect=BadRequestError(
                message="Tool name 'foo' does not match the name in the source code",
                response=mock_response,
                body=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await call_letta(lambda: None)
            assert exc_info.value.status_code == 400
            assert "does not match" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_other_letta_error_returns_503(self):
        """Non-BadRequest Letta errors should still raise 503."""
        from letta_client import NotFoundError

        from app.letta_client import call_letta

        mock_response = MagicMock()
        mock_response.request = MagicMock()

        with patch(
            "app.letta_client.run_sync",
            side_effect=NotFoundError(
                message="Agent not found",
                response=mock_response,
                body=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await call_letta(lambda: None)
            assert exc_info.value.status_code == 503


class TestSanitizeErrorDetail:
    """Tests for sanitize_error_detail."""

    def test_strips_unix_paths(self):
        result = sanitize_error_detail("Error in /usr/local/lib/module.py")
        assert "/usr/local" not in result
        assert "[path]" in result

    def test_strips_tracebacks(self):
        result = sanitize_error_detail('Traceback (most recent call last): File "app.py", line 42')
        assert "Traceback" not in result
        assert "[path]" in result

    def test_truncates_long_messages(self):
        result = sanitize_error_detail("x" * 300, max_length=200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_short_messages_unchanged(self):
        result = sanitize_error_detail("Short error", max_length=200)
        assert result == "Short error"
