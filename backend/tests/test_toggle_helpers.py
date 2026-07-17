"""Tests for ensure_tool_creation toggle helper.

This function attaches/detaches propose_tool, fetch_docs, list_github_repo,
and read_github_file from agents based on the agent_tool_creation user setting.
All four tools are controlled by a single toggle. They are called on every
chat/workflow execution to sync the agent's tool list with the current toggle
state.

Since these functions use call_letta() which wraps sync Letta client
calls through run_sync, we mock call_letta directly instead of trying
to mock the underlying client methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.tools import ensure_tool_creation


def _make_mock_tool(name: str, tool_id: str = "tool-123"):
    """Create a mock tool object with name and id attributes."""
    tool = MagicMock()
    tool.name = name
    tool.id = tool_id
    return tool


def _make_mock_settings(**kwargs):
    """Create a mock UserSettings object."""
    settings = MagicMock()
    settings.agent_tool_creation = kwargs.get("agent_tool_creation", False)
    return settings


def _make_mock_db(settings=None):
    """Create a mock AsyncSession that returns the given settings.

    The real code does:
        result = await db.execute(select(...))
        settings = result.scalar_one_or_none()

    So db.execute is an async method that returns an object with
    scalar_one_or_none (a sync method).
    """
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = settings
    db.execute.return_value = result_mock
    return db


def _make_call_letta_side_effect(agent_tools=None, all_tools=None, new_tool=None):
    """Build a side_effect for mock call_letta.

    Routes calls based on the function being called:
    - client.agents.tools.list → returns agent_tools
    - client.tools.list → returns all_tools
    - client.tools.create → returns new_tool
    - client.agents.tools.attach → returns success
    - client.agents.tools.detach → returns success
    - client.agents.blocks.update → returns success
    """
    if agent_tools is None:
        agent_tools = []
    if all_tools is None:
        all_tools = MagicMock(items=[])

    async def _call_letta(func, *args, **kwargs):
        # Match by checking the function's qualified name or string representation
        func_str = str(func)
        if "tools.list" in func_str and "agents" not in func_str:
            return all_tools
        if "agents.tools.list" in func_str:
            return agent_tools
        if "tools.create" in func_str:
            return new_tool or MagicMock(id="new-tool-456")
        if "agents.tools.attach" in func_str:
            return MagicMock()
        if "agents.tools.detach" in func_str:
            return MagicMock()
        if "blocks.update" in func_str:
            return MagicMock()
        return MagicMock()

    return _call_letta


# --- ensure_tool_creation tests ---


class TestEnsureToolCreation:
    """Tests for ensure_tool_creation — attach/detach propose_tool, fetch_docs, list_github_repo, and read_github_file based on setting."""

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_attach_all_four_when_enabled_and_not_present(self, mock_call_letta):
        """Setting on + no tools → creates and attaches all four tools."""
        settings = _make_mock_settings(agent_tool_creation=True)
        db = _make_mock_db(settings)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],  # No tools on agent
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "ENABLED" in result
        # Should have called: tools.list (agent) x4, tools.create x4, agents.tools.attach x4, blocks.update x4
        assert mock_call_letta.call_count >= 12

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_enabled_and_all_present(self, mock_call_letta):
        """Setting on + all four tools already attached → does nothing."""
        settings = _make_mock_settings(agent_tool_creation=True)
        db = _make_mock_db(settings)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        fetch_docs = _make_mock_tool("fetch_docs", "fetch-docs-tool-id")
        list_repo = _make_mock_tool("list_github_repo", "list-repo-tool-id")
        read_file = _make_mock_tool("read_github_file", "read-file-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool, fetch_docs, list_repo, read_file],
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_all_four_when_disabled_and_present(self, mock_call_letta):
        """Setting off + all four tools attached → detaches all four."""
        settings = _make_mock_settings(agent_tool_creation=False)
        db = _make_mock_db(settings)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        fetch_docs = _make_mock_tool("fetch_docs", "fetch-docs-tool-id")
        list_repo = _make_mock_tool("list_github_repo", "list-repo-tool-id")
        read_file = _make_mock_tool("read_github_file", "read-file-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool, fetch_docs, list_repo, read_file],
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result
        # Should have called: agents.tools.list x4, agents.tools.detach x4, blocks.update x4
        assert mock_call_letta.call_count >= 8

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_disabled_and_not_present(self, mock_call_letta):
        """Setting off + no tools → does nothing."""
        settings = _make_mock_settings(agent_tool_creation=False)
        db = _make_mock_db(settings)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_no_settings(self, mock_call_letta):
        """No settings record → treated as disabled, no-op if tools not present."""
        db = _make_mock_db(settings=None)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_when_no_settings_but_tools_present(self, mock_call_letta):
        """No settings record + tools present → detaches all four (treated as disabled)."""
        db = _make_mock_db(settings=None)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        fetch_docs = _make_mock_tool("fetch_docs", "fetch-docs-tool-id")
        list_repo = _make_mock_tool("list_github_repo", "list-repo-tool-id")
        read_file = _make_mock_tool("read_github_file", "read-file-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool, fetch_docs, list_repo, read_file],
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_attaches_missing_tools_when_some_present(self, mock_call_letta):
        """Setting on + only propose_tool present → attaches fetch_docs, list_github_repo, and read_github_file."""
        settings = _make_mock_settings(agent_tool_creation=True)
        db = _make_mock_db(settings)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool],  # fetch_docs, list_github_repo, read_github_file missing
        )

        result = await ensure_tool_creation(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "ENABLED" in result
