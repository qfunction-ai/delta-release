"""Tests for dashboard helpers and endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.dashboard.routes import _check_health, _dt_to_str


class TestDtToStr:
    """Tests for _dt_to_str helper."""

    def test_datetime_to_iso(self):
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _dt_to_str(dt)
        assert "2024-01-15" in result

    def test_string_passthrough(self):
        result = _dt_to_str("already a string")
        assert result == "already a string"

    def test_none_returns_empty(self):
        result = _dt_to_str(None)
        assert result == ""


class TestCheckHealth:
    """Tests for _check_health helper."""

    @pytest.mark.asyncio
    async def test_healthy(self):
        with patch("app.dashboard.routes.httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await _check_health("http://test:8080/health")
            assert result == "healthy"

    @pytest.mark.asyncio
    async def test_degraded(self):
        with patch("app.dashboard.routes.httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.status_code = 503
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await _check_health("http://test:8080/health")
            assert result == "degraded"

    @pytest.mark.asyncio
    async def test_unreachable(self):
        import httpx

        with patch("app.dashboard.routes.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await _check_health("http://test:8080/health")
            assert result == "unreachable"


@pytest.mark.asyncio
class TestDashboardEndpoint:
    async def test_get_dashboard(self, registered_client, mock_letta_client):
        """GET /api/dashboard/ returns dashboard data."""
        client, headers, _ = registered_client
        with patch("app.dashboard.routes._check_health", new_callable=AsyncMock, return_value="unreachable"):
            resp = await client.get("/api/dashboard/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "stats" in data
        assert "recent_runs" in data
        assert "health" in data
