"""Tests for credentials/service.py — secret sync mechanics (F2 / D-2).

D-2 regression: the sync must retrieve the agent with include=["agent.secrets"]
and read the `secrets` field. Without the include, the Letta server omits
relationships for 1.x SDK clients, the merge reads an empty set, and every
sync deletes all non-credential secrets (including the tool-callback token).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from letta_client import BadRequestError

from app.credentials.service import sync_credential_secrets


def _env_var(key, value):
    return SimpleNamespace(key=key, value=value)


def _make_db(credentials, agents):
    """Build a mock AsyncSession whose execute() returns credentials, then agents."""
    db = MagicMock()
    cred_result = MagicMock()
    cred_result.scalars.return_value.all.return_value = credentials
    agent_result = MagicMock()
    agent_result.scalars.return_value.all.return_value = agents
    db.execute = AsyncMock(side_effect=[cred_result, agent_result])
    return db


def _make_letta_agent(secrets_list):
    agent = MagicMock()
    # D-2: the sync must read `secrets`, not the deprecated
    # tool_exec_environment_variables (which comes back empty for 1.x SDK
    # clients when include is missing).
    agent.secrets = secrets_list
    agent.tool_exec_environment_variables = None
    return agent


@pytest.mark.asyncio
class TestSyncCredentialSecrets:
    async def test_retrieves_with_agent_secrets_include(self):
        """D-2: retrieve must pass include=["agent.secrets"] or the merge reads nothing."""
        db = _make_db([], [SimpleNamespace(letta_agent_id="agent-1")])
        client = MagicMock()
        client.agents.retrieve = MagicMock(return_value=_make_letta_agent([]))
        client.agents.update = MagicMock(return_value=None)

        with (
            patch("app.credentials.service.get_letta_client", return_value=client),
            patch("app.credentials.service.run_sync", new_callable=AsyncMock) as mock_run,
            patch("app.credentials.service.get_settings") as mock_settings,
        ):
            mock_settings.return_value.service_token = "tok"
            mock_settings.return_value.backend_url = "http://backend:8000"
            mock_run.side_effect = [
                _make_letta_agent([]),
                None,
            ]
            await sync_credential_secrets("user-1", db)

        # First run_sync call is the retrieve — assert the include kwarg
        retrieve_call = mock_run.call_args_list[0]
        assert retrieve_call.args[1] == "agent-1"
        assert retrieve_call.kwargs == {"include": ["agent.secrets"]}

    async def test_preserves_non_credential_secrets(self):
        """D-2 witness (mock form): a KEEP_ME secret must survive the sync."""
        db = _make_db(
            [SimpleNamespace(name="sumo", encrypted_value=None)],
            [SimpleNamespace(letta_agent_id="agent-1")],
        )
        letta_agent = _make_letta_agent([_env_var("KEEP_ME", "keep-value"), _env_var("CREDENTIAL_OLD", "stale")])
        client = MagicMock()

        with (
            patch("app.credentials.service.get_letta_client", return_value=client),
            patch("app.credentials.service.run_sync", new_callable=AsyncMock) as mock_run,
            patch("app.credentials.service.get_settings") as mock_settings,
            patch("app.credentials.service._credential_to_env_var", return_value=("CREDENTIAL_NEW", '{"k": "v"}')),
        ):
            mock_settings.return_value.service_token = "tok"
            mock_settings.return_value.backend_url = "http://backend:8000"
            mock_run.side_effect = [letta_agent, None]
            result = await sync_credential_secrets("user-1", db)

        assert result == {"agent-1": "ok"}
        update_call = mock_run.call_args_list[1]
        merged = update_call.kwargs["secrets"]
        assert merged["KEEP_ME"] == "keep-value"  # non-credential secret survives
        assert "CREDENTIAL_OLD" not in merged  # stale credential replaced
        assert merged["CREDENTIAL_NEW"] == '{"k": "v"}'
        assert merged["DELTA_SERVICE_TOKEN"] == "tok"  # token always re-added
        assert merged["DELTA_API_BASE_URL"] == "http://backend:8000"  # G-1: base URL rides the same channel

    async def test_reads_secrets_field_not_deprecated_one(self):
        """D-2: merge source is `secrets`; tool_exec_environment_variables is ignored."""
        db = _make_db([], [SimpleNamespace(letta_agent_id="agent-1")])
        letta_agent = MagicMock()
        letta_agent.secrets = [_env_var("KEEP_ME", "keep-value")]
        # Deprecated field still populated (pre-0.16.39 servers) — must be ignored
        letta_agent.tool_exec_environment_variables = [_env_var("DEPRECATED_ONLY", "x")]

        with (
            patch("app.credentials.service.get_letta_client", return_value=MagicMock()),
            patch("app.credentials.service.run_sync", new_callable=AsyncMock) as mock_run,
            patch("app.credentials.service.get_settings") as mock_settings,
        ):
            mock_settings.return_value.service_token = "tok"
            mock_settings.return_value.backend_url = "http://backend:8000"
            mock_run.side_effect = [letta_agent, None]
            await sync_credential_secrets("user-1", db)

        merged = mock_run.call_args_list[1].kwargs["secrets"]
        assert merged["KEEP_ME"] == "keep-value"
        assert "DEPRECATED_ONLY" not in merged

    async def test_b9_400_marks_agent_failed_without_raising(self):
        """B-9: a 400 (secret value matches a protected server value) marks the
        agent failed, is logged, and does not crash the sync loop."""
        db = _make_db([], [SimpleNamespace(letta_agent_id="agent-1")])

        calls = {"n": 0}

        async def _run_sync_side_effect(func, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:  # first call is the retrieve
                return _make_letta_agent([])
            raise BadRequestError(
                "Secret value matches a protected server value",
                response=MagicMock(status_code=400, headers={}),
                body={"detail": "Secret value matches a protected server value"},
            )

        with (
            patch("app.credentials.service.get_letta_client", return_value=MagicMock()),
            patch("app.credentials.service.run_sync", side_effect=_run_sync_side_effect),
            patch("app.credentials.service.get_settings") as mock_settings,
        ):
            mock_settings.return_value.service_token = "tok"
            mock_settings.return_value.backend_url = "http://backend:8000"
            result = await sync_credential_secrets("user-1", db)

        assert result == {"agent-1": "failed"}
