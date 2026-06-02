"""Tests for rate limiting utilities."""

from unittest.mock import MagicMock, patch

from app.rate_limit import (
    _is_rate_limiting_relaxed,
    get_user_identifier,
    rate_limit_exceeded_handler,
)


class TestGetUserIdentifier:
    """Tests for get_user_identifier."""

    def test_authenticated_user(self):
        request = MagicMock()
        request.state.user_id = "user-123"
        result = get_user_identifier(request)
        assert result == "user:user-123"

    def test_forwarded_for_header(self):
        request = MagicMock()
        del request.state.user_id  # No user_id
        request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        result = get_user_identifier(request)
        assert result == "ip:5.6.7.8"

    def test_no_forwarded_for(self):
        request = MagicMock()
        del request.state.user_id
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        result = get_user_identifier(request)
        assert "ip:" in result


class TestRateLimitExceededHandler:
    """Tests for rate_limit_exceeded_handler."""

    def test_raises_http_exception(self):
        request = MagicMock()
        request.state.user_id = "test-user"
        exc = MagicMock()  # Mock RateLimitExceeded
        try:
            rate_limit_exceeded_handler(request, exc)
            assert False, "Should have raised"
        except Exception as e:
            assert e.status_code == 429


class TestIsRateLimitingRelaxed:
    """Tests for _is_rate_limiting_relaxed."""

    def test_relaxed_with_high_limit(self):
        with patch("app.rate_limit._default_limit", "1000/minute"):
            assert _is_rate_limiting_relaxed() is True

    def test_not_relaxed_with_normal_limit(self):
        with patch("app.rate_limit._default_limit", "100/minute"):
            assert _is_rate_limiting_relaxed() is False

    def test_invalid_format(self):
        with patch("app.rate_limit._default_limit", "invalid"):
            assert _is_rate_limiting_relaxed() is False
