"""Tests for auth dependencies — token extraction and service token verification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.dependencies import _extract_token, verify_service_token


@pytest.mark.asyncio
class TestExtractToken:
    """Tests for _extract_token."""

    async def test_authorization_header(self):
        request = MagicMock()
        request.cookies = {}
        mock_cred = MagicMock()
        mock_cred.credentials = "test-token"
        with patch("app.auth.dependencies._security", new_callable=AsyncMock) as mock_security:
            mock_security.return_value = mock_cred
            result = await _extract_token(request)
        assert result == "test-token"

    async def test_cookie_fallback(self):
        request = MagicMock()
        request.cookies = {"delta_token": "cookie-token"}
        with patch("app.auth.dependencies._security", new_callable=AsyncMock) as mock_security:
            mock_security.return_value = None  # No Authorization header
            result = await _extract_token(request)
        assert result == "cookie-token"

    async def test_no_token(self):
        request = MagicMock()
        request.cookies = {}
        with patch("app.auth.dependencies._security", new_callable=AsyncMock) as mock_security:
            mock_security.return_value = None
            result = await _extract_token(request)
        assert result is None


@pytest.mark.asyncio
class TestVerifyServiceToken:
    """Tests for verify_service_token."""

    async def test_valid_service_token(self):
        request = MagicMock()
        request.headers = {"X-Service-Token": "test-service-token"}
        with patch("app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.service_token = "test-service-token"
            await verify_service_token(request)
        assert request.state.auth_method == "service_token"

    async def test_invalid_service_token(self):
        request = MagicMock()
        request.headers = {"X-Service-Token": "wrong-token"}
        with patch("app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.service_token = "test-service-token"
            with pytest.raises(HTTPException) as exc_info:
                await verify_service_token(request)
            assert exc_info.value.status_code == 403

    async def test_missing_service_token(self):
        request = MagicMock()
        request.headers = {}
        with patch("app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.service_token = "test-service-token"
            with pytest.raises(HTTPException) as exc_info:
                await verify_service_token(request)
            assert exc_info.value.status_code == 403

    async def test_no_configured_service_token(self):
        request = MagicMock()
        request.headers = {"X-Service-Token": "some-token"}
        with patch("app.auth.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.service_token = ""
            with pytest.raises(HTTPException) as exc_info:
                await verify_service_token(request)
            assert exc_info.value.status_code == 403
