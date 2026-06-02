"""Tests for dashboard routes — health check and dashboard data."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCheckHealth:
    """Tests for _check_health helper."""

    @pytest.mark.asyncio
    async def test_healthy_service(self):
        """Returns 'healthy' when service responds 200."""
        from app.dashboard.routes import _check_health

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.dashboard.routes.httpx.AsyncClient", return_value=mock_client):
            result = await _check_health("http://test:8000/health")
        assert result == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_service(self):
        """Returns 'degraded' when service responds non-200."""
        from app.dashboard.routes import _check_health

        mock_resp = MagicMock()
        mock_resp.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.dashboard.routes.httpx.AsyncClient", return_value=mock_client):
            result = await _check_health("http://test:8000/health")
        assert result == "degraded"

    @pytest.mark.asyncio
    async def test_unreachable_service(self):
        """Returns 'unreachable' when connection fails."""
        import httpx

        from app.dashboard.routes import _check_health

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.dashboard.routes.httpx.AsyncClient", return_value=mock_client):
            result = await _check_health("http://test:8000/health")
        assert result == "unreachable"

    @pytest.mark.asyncio
    async def test_timeout_service(self):
        """Returns 'unreachable' when service times out."""
        import httpx

        from app.dashboard.routes import _check_health

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.dashboard.routes.httpx.AsyncClient", return_value=mock_client):
            result = await _check_health("http://test:8000/health")
        assert result == "unreachable"


class TestDtToStr:
    """Tests for _dt_to_str helper."""

    def test_datetime_to_iso(self):
        """Converts datetime to ISO string."""
        from app.dashboard.routes import _dt_to_str

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _dt_to_str(dt)
        assert "2026-01-15" in result

    def test_string_passthrough(self):
        """Returns string as-is."""
        from app.dashboard.routes import _dt_to_str

        assert _dt_to_str("already a string") == "already a string"

    def test_none_returns_empty(self):
        """Returns empty string for None."""
        from app.dashboard.routes import _dt_to_str

        assert _dt_to_str(None) == ""


@pytest.mark.asyncio
class TestDashboardEndpoint:
    """Integration tests for the dashboard endpoint."""

    async def test_get_dashboard(self, registered_client, mock_letta_client):
        """GET /api/dashboard/ returns dashboard data."""
        client, headers, _ = registered_client

        with patch("app.dashboard.routes._check_health", new_callable=AsyncMock, return_value="healthy"):
            resp = await client.get("/api/dashboard/", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "stats" in data
        assert "recent_runs" in data
        assert "health" in data
        assert data["health"]["backend"] == "healthy"
        assert data["health"]["postgres"] == "healthy"
