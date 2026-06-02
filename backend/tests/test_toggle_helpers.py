"""Tests for ensure_propose_tool and ensure_web_search toggle helpers.

These functions attach/detach tools from agents based on user settings.
They are called on every chat/workflow execution to sync the agent's
tool list with the current toggle state.

Since these functions use call_letta() which wraps sync Letta client
calls through run_sync, we mock call_letta directly instead of trying
to mock the underlying client methods.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.tools import ensure_propose_tool, ensure_web_search


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
    settings.web_search_enabled = kwargs.get("web_search_enabled", False)
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


# --- ensure_propose_tool tests ---


class TestEnsureProposeTool:
    """Tests for ensure_propose_tool — attach/detach propose_tool based on setting."""

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_attach_when_enabled_and_not_present(self, mock_call_letta):
        """Setting on + no propose_tool → creates and attaches tool."""
        settings = _make_mock_settings(agent_tool_creation=True)
        db = _make_mock_db(settings)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],  # No tools on agent
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "ENABLED" in result
        # Should have called: tools.list (agent), tools.create, agents.tools.attach, blocks.update
        assert mock_call_letta.call_count >= 3

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_enabled_and_already_present(self, mock_call_letta):
        """Setting on + propose_tool already attached → does nothing."""
        settings = _make_mock_settings(agent_tool_creation=True)
        db = _make_mock_db(settings)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool],
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_when_disabled_and_present(self, mock_call_letta):
        """Setting off + propose_tool attached → detaches tool."""
        settings = _make_mock_settings(agent_tool_creation=False)
        db = _make_mock_db(settings)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool],
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result
        # Should have called: agents.tools.list, agents.tools.detach, blocks.update
        assert mock_call_letta.call_count >= 2

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_disabled_and_not_present(self, mock_call_letta):
        """Setting off + no propose_tool → does nothing."""
        settings = _make_mock_settings(agent_tool_creation=False)
        db = _make_mock_db(settings)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_no_settings(self, mock_call_letta):
        """No settings record → treated as disabled, no-op if tool not present."""
        db = _make_mock_db(settings=None)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_when_no_settings_but_tool_present(self, mock_call_letta):
        """No settings record + tool present → detaches (treated as disabled)."""
        db = _make_mock_db(settings=None)
        propose_tool = _make_mock_tool("propose_tool", "propose-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[propose_tool],
        )

        result = await ensure_propose_tool(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result


# --- ensure_web_search tests ---


class TestEnsureWebSearch:
    """Tests for ensure_web_search — attach/detach web_search based on setting."""

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_attach_when_enabled_and_not_present(self, mock_call_letta):
        """Setting on + no web_search + EXA_API_KEY set → attaches built-in tool."""
        settings = _make_mock_settings(web_search_enabled=True)
        db = _make_mock_db(settings)
        web_search_tool = _make_mock_tool("web_search", "ws-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
            all_tools=MagicMock(items=[web_search_tool]),
        )

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}):
            result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "ENABLED" in result
        assert "EXA_API_KEY" not in result  # Key is configured, no warning

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_attach_warns_when_no_exa_key(self, mock_call_letta):
        """Setting on + no EXA_API_KEY → attaches tool but warns about missing key."""
        settings = _make_mock_settings(web_search_enabled=True)
        db = _make_mock_db(settings)
        web_search_tool = _make_mock_tool("web_search", "ws-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
            all_tools=MagicMock(items=[web_search_tool]),
        )

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EXA_API_KEY", None)
            result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "ENABLED" in result
        assert "EXA_API_KEY" in result  # Warning about missing key

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_enabled_and_already_present(self, mock_call_letta):
        """Setting on + web_search already attached → does nothing."""
        settings = _make_mock_settings(web_search_enabled=True)
        db = _make_mock_db(settings)
        web_search_tool = _make_mock_tool("web_search", "ws-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[web_search_tool],
        )

        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}):
            result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_when_disabled_and_present(self, mock_call_letta):
        """Setting off + web_search attached → detaches tool."""
        settings = _make_mock_settings(web_search_enabled=False)
        db = _make_mock_db(settings)
        web_search_tool = _make_mock_tool("web_search", "ws-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[web_search_tool],
        )

        result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_disabled_and_not_present(self, mock_call_letta):
        """Setting off + no web_search → does nothing."""
        settings = _make_mock_settings(web_search_enabled=False)
        db = _make_mock_db(settings)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_noop_when_no_settings(self, mock_call_letta):
        """No settings record → treated as disabled, no-op if tool not present."""
        db = _make_mock_db(settings=None)
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[],
        )

        result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.agents.tools.call_letta")
    async def test_detach_when_no_settings_but_tool_present(self, mock_call_letta):
        """No settings record + tool present → detaches (treated as disabled)."""
        db = _make_mock_db(settings=None)
        web_search_tool = _make_mock_tool("web_search", "ws-tool-id")
        mock_call_letta.side_effect = _make_call_letta_side_effect(
            agent_tools=[web_search_tool],
        )

        result = await ensure_web_search(MagicMock(), "agent-1", "user-1", db)

        assert result is not None
        assert "DISABLED" in result
