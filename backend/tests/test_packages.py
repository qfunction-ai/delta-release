"""Tests for pip sidecar package management."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.tools.packages import sidecar_request


class TestSidecarRequest:
    """Tests for sidecar_request — HTTP client for the pip sidecar."""

    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Successful request returns response with service token header."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tools.packages.get_settings") as mock_settings,
            patch("app.tools.packages.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.service_token = "test-token"
            await sidecar_request("GET", "/packages")

        # Verify service token was added to headers
        call_kwargs = mock_client.request.call_args
        assert call_kwargs[1]["headers"]["X-Service-Token"] == "test-token"

    @pytest.mark.asyncio
    async def test_connect_error_raises_503(self):
        """ConnectError raises 503 Service Unavailable."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tools.packages.get_settings") as mock_settings,
            patch("app.tools.packages.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.service_token = "test-token"
            with pytest.raises(HTTPException) as exc_info:
                await sidecar_request("GET", "/packages")
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_timeout_raises_504(self):
        """TimeoutException raises 504 Gateway Timeout."""
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tools.packages.get_settings") as mock_settings,
            patch("app.tools.packages.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.service_token = "test-token"
            with pytest.raises(HTTPException) as exc_info:
                await sidecar_request("GET", "/packages")
            assert exc_info.value.status_code == 504

    @pytest.mark.asyncio
    async def test_no_service_token(self):
        """Request works without service token (empty string)."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.tools.packages.get_settings") as mock_settings,
            patch("app.tools.packages.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.return_value.service_token = ""
            await sidecar_request("GET", "/packages")

        # No X-Service-Token header when token is empty
        call_kwargs = mock_client.request.call_args
        assert "X-Service-Token" not in call_kwargs[1]["headers"]
