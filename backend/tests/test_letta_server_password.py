"""Tests for the Letta server-password plumbing (v0.16.39 adoption item 1).

Consumers send Authorization: Bearer ONLY when a password is configured —
empty password means unauthenticated (fake-letta CI, pre-0.16.39 pins).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import letta_client as lc
from app.config import Settings, _load_letta_server_password


class TestLoadLettaServerPassword:
    def test_env_var_wins(self):
        settings = Settings(letta_server_password="from-env")
        with patch("builtins.open", side_effect=AssertionError("must not read the file")):
            _load_letta_server_password(settings)
        assert settings.letta_server_password == "from-env"

    def test_file_fallback(self):
        from unittest.mock import mock_open

        settings = Settings()
        with patch("builtins.open", mock_open(read_data="file-password\n")):
            _load_letta_server_password(settings)
        assert settings.letta_server_password == "file-password"

    def test_empty_file_ignored(self):
        from unittest.mock import mock_open

        settings = Settings()
        with patch("builtins.open", mock_open(read_data="  \n")):
            _load_letta_server_password(settings)
        assert settings.letta_server_password == ""

    def test_missing_file_is_empty(self):
        settings = Settings()
        with patch("builtins.open", side_effect=OSError("no such file")):
            _load_letta_server_password(settings)
        assert settings.letta_server_password == ""


class TestClientPassword:
    def test_client_sends_password_as_api_key(self):
        """With a password set, the SDK api_key carries it — the SDK turns
        api_key into Authorization: Bearer, which the fork's middleware
        accepts."""
        lc.get_letta_client.cache_clear()
        try:
            with patch("app.letta_client.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    letta_base_url="http://localhost:9999",
                    letta_server_password="sekrit",
                )
                client = lc.get_letta_client()
            assert client.agents._client.auth_headers == {"Authorization": "Bearer sekrit"}
        finally:
            lc.get_letta_client.cache_clear()

    def test_client_without_password_suppresses_env_fallback(self):
        """Empty password must yield a harmless empty Bearer, NOT the
        machine's LETTA_API_KEY — the SDK falls back to the env var when
        api_key is None, which is a different credential and would 401
        against the fork's password check."""
        lc.get_letta_client.cache_clear()
        try:
            with patch("app.letta_client.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    letta_base_url="http://localhost:9999",
                    letta_server_password="",
                )
                client = lc.get_letta_client()
            auth = client.agents._client.auth_headers.get("Authorization", "")
            assert auth in ("", "Bearer "), f"unexpected credential: {auth!r}"
        finally:
            lc.get_letta_client.cache_clear()


@pytest.mark.asyncio
class TestProxyPassword:
    async def test_proxy_header_follows_password(self):
        from app.agents.letta_proxy import _proxy_request

        captured_headers = {}

        class _Resp:
            content = b"{}"
            status_code = 200
            headers = {}

        async def _req(method=None, url=None, headers=None, content=None):
            captured_headers.update(headers or {})
            return _Resp()

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, **kwargs):
                return await _req(**kwargs)

        request = AsyncMock()
        request.headers = {}
        request.body.return_value = None
        agent = MagicMock()

        with (
            patch("app.agents.letta_proxy.get_settings") as mock_settings,
            patch("app.agents.letta_proxy.httpx.AsyncClient", return_value=_Client()),
        ):
            mock_settings.return_value = MagicMock(
                letta_base_url="http://letta:8283",
                letta_server_password="",
            )
            await _proxy_request("GET", "/v1/x", agent, request)

        assert "Authorization" not in captured_headers

        # And with a password, the header IS sent
        captured_headers.clear()
        with (
            patch("app.agents.letta_proxy.get_settings") as mock_settings,
            patch("app.agents.letta_proxy.httpx.AsyncClient", return_value=_Client()),
        ):
            mock_settings.return_value = MagicMock(
                letta_base_url="http://letta:8283",
                letta_server_password="sekrit",
            )
            await _proxy_request("GET", "/v1/x", agent, request)

        assert captured_headers.get("Authorization") == "Bearer sekrit"
