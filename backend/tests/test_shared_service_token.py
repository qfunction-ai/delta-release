"""Tests for shared/service_token.py — kind-parameterized token loading (F2).

These run against the repo-root shared/ package, which the backend test
runner puts on the path via the shared package install.
"""

from unittest.mock import mock_open, patch

import pytest

import shared.service_token as st


@pytest.fixture(autouse=True)
def _reset_cache():
    """Clear the module-level token cache between tests."""
    st._SERVICE_TOKENS.clear()
    st._SERVICE_TOKENS_LOADED_AT.clear()
    yield
    st._SERVICE_TOKENS.clear()
    st._SERVICE_TOKENS_LOADED_AT.clear()


class TestKindLoading:
    def test_eval_token_from_env(self):
        with patch.dict(st.os.environ, {"DELTA_EVAL_SERVICE_TOKEN": "eval-tok"}, clear=False):
            assert st._get_service_token("eval") == "eval-tok"

    def test_sidecar_token_from_env(self):
        with patch.dict(st.os.environ, {"DELTA_SIDECAR_SERVICE_TOKEN": "side-tok"}, clear=False):
            assert st._get_service_token("sidecar") == "side-tok"

    def test_eval_token_from_file(self):
        env = {k: "" for k in ("DELTA_EVAL_SERVICE_TOKEN",)}
        with (
            patch.dict(st.os.environ, env, clear=False),
            patch("builtins.open", mock_open(read_data="file-eval-tok\n")),
        ):
            assert st._get_service_token("eval") == "file-eval-tok"

    def test_sidecar_token_from_file(self):
        env = {k: "" for k in ("DELTA_SIDECAR_SERVICE_TOKEN",)}
        with (
            patch.dict(st.os.environ, env, clear=False),
            patch("builtins.open", mock_open(read_data="file-side-tok\n")),
        ):
            assert st._get_service_token("sidecar") == "file-side-tok"

    def test_kinds_are_isolated(self):
        """The eval token must not satisfy the sidecar kind and vice versa."""
        with (
            patch.dict(st.os.environ, {"DELTA_EVAL_SERVICE_TOKEN": "eval-tok"}, clear=False),
            patch("builtins.open", mock_open(read_data="")) as m_open,
        ):
            assert st._get_service_token("eval") == "eval-tok"
            assert st._get_service_token("sidecar") is None
            # sidecar read hit its own file path
            assert "sidecar_service_token" in str(m_open.call_args)


class TestMakeVerify:
    @pytest.mark.asyncio
    async def test_verify_rejects_cross_kind_token(self):
        from fastapi import HTTPException

        verify = st.make_verify_service_token("sidecar")
        request = type("R", (), {})()
        request.headers = {"X-Service-Token": "eval-tok"}
        with patch.dict(st.os.environ, {"DELTA_SIDECAR_SERVICE_TOKEN": "side-tok"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                await verify(request)
            assert exc_info.value.status_code == 403
