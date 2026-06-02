"""Tests for run preparation helpers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.run_prep import prepare_chat_run, prepare_prompt_context, prepare_workflow_run


def _make_workflow(
    workflow_id="wf-1",
    agent_id="agent-1",
    user_id="user-1",
    prompt_template="Search for {{query}}",
    skill_ids_list=None,
    tool_ids_list=None,
    include_reasoning=False,
):
    """Create a mock workflow object."""
    wf = MagicMock()
    wf.id = workflow_id
    wf.agent_id = agent_id
    wf.user_id = user_id
    wf.prompt_template = prompt_template
    wf.skill_ids_list = skill_ids_list or []
    wf.tool_ids_list = tool_ids_list or []
    wf.include_reasoning = include_reasoning
    wf.default_variables = json.dumps({"query": "test"})
    return wf


class TestPreparePromptContext:
    """Tests for prepare_prompt_context."""

    @pytest.mark.asyncio
    async def test_no_skills_no_lessons(self):
        """Workflow with no skills or lessons returns prompt unchanged."""
        workflow = _make_workflow(skill_ids_list=[])
        client = MagicMock()
        db = AsyncMock()

        with (
            patch("app.agents.run_prep.get_lessons_for_workflow", new_callable=AsyncMock, return_value=[]),
        ):
            result = await prepare_prompt_context(workflow, "agent-1", "test prompt", client, db)

        assert result == "test prompt"

    @pytest.mark.asyncio
    async def test_with_skills_prepends_prefix(self):
        """Skills are inserted into archival memory and prefix is prepended."""
        skill = MagicMock()
        skill.name = "threat-hunt"
        skill.content = "Step 1: Do thing\nStep 2: Do other thing"

        workflow = _make_workflow(skill_ids_list=["skill-1"])
        client = MagicMock()
        db = AsyncMock()

        with (
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[skill]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_skills_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["threat-hunt"],
            ),
            patch("app.agents.run_prep.get_lessons_for_workflow", new_callable=AsyncMock, return_value=[]),
            patch("app.agents.run_prep._fetch_skill_files", new_callable=AsyncMock, return_value={}),
        ):
            result = await prepare_prompt_context(workflow, "agent-1", "test prompt", client, db)

        assert "threat-hunt" in result
        assert "test prompt" in result
        # Skill prefix should come before the original prompt
        assert result.index("threat-hunt") < result.index("test prompt")

    @pytest.mark.asyncio
    async def test_with_lessons_prepends_prefix(self):
        """Lessons are inserted into archival memory and prefix is prepended."""
        lesson = MagicMock()
        lesson.category = "strategy"
        lesson.content = "Past approach worked well"
        lesson.times_used = 0

        workflow = _make_workflow(skill_ids_list=[])
        client = MagicMock()
        db = AsyncMock()

        with (
            patch("app.agents.run_prep.get_lessons_for_workflow", new_callable=AsyncMock, return_value=[lesson]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_lessons_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["strategy"],
            ),
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[]),
        ):
            result = await prepare_prompt_context(workflow, "agent-1", "test prompt", client, db)

        assert "lesson" in result.lower()
        assert "test prompt" in result

    @pytest.mark.asyncio
    async def test_skills_always_prepended_inline(self):
        """Skill prefix is always prepended inline, even if archival insertion fails."""
        skill = MagicMock()
        skill.name = "broken-skill"
        skill.content = "content"

        workflow = _make_workflow(skill_ids_list=["skill-1"])
        client = MagicMock()
        db = AsyncMock()

        with (
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[skill]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch("app.agents.run_prep.insert_skills_into_archival_memory", new_callable=AsyncMock, return_value=[]),
            patch("app.agents.run_prep.get_lessons_for_workflow", new_callable=AsyncMock, return_value=[]),
            patch("app.agents.run_prep._fetch_skill_files", new_callable=AsyncMock, return_value={}),
        ):
            result = await prepare_prompt_context(workflow, "agent-1", "test prompt", client, db)

        assert "broken-skill" in result
        assert "test prompt" in result

    @pytest.mark.asyncio
    async def test_lesson_times_used_incremented(self):
        """Lesson times_used is incremented after insertion."""
        lesson = MagicMock()
        lesson.category = "strategy"
        lesson.content = "Good approach"
        lesson.times_used = 2

        workflow = _make_workflow(skill_ids_list=[])
        client = MagicMock()
        db = AsyncMock()

        with (
            patch("app.agents.run_prep.get_lessons_for_workflow", new_callable=AsyncMock, return_value=[lesson]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_lessons_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["strategy"],
            ),
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[]),
        ):
            await prepare_prompt_context(workflow, "agent-1", "test prompt", client, db)

        assert lesson.times_used == 3
        db.flush.assert_called()


class TestPrepareWorkflowRun:
    """Tests for prepare_workflow_run."""

    @pytest.mark.asyncio
    async def test_basic_workflow_run(self):
        """Creates run record, renders prompt, returns client."""
        workflow = _make_workflow(
            prompt_template="Search for {{query}}",
            skill_ids_list=[],
            tool_ids_list=[],
        )
        client = MagicMock()

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.workflows.template.render_template", return_value="Search for test"),
            patch("app.agents.run_prep.prepare_prompt_context", new_callable=AsyncMock, return_value="Search for test"),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock),
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
        ):
            db = AsyncMock()
            rendered_prompt, run, returned_client = await prepare_workflow_run(
                workflow, {"query": "test"}, "user-1", db
            )

        assert rendered_prompt == "Search for test"
        assert returned_client == client
        db.add.assert_called_once()
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_with_tool_ids_attaches_tools(self):
        """Tool IDs are attached to the agent."""
        workflow = _make_workflow(
            tool_ids_list=["tool-1"],
            skill_ids_list=[],
        )
        client = MagicMock()

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.workflows.template.render_template", return_value="prompt"),
            patch("app.agents.run_prep.prepare_prompt_context", new_callable=AsyncMock, return_value="prompt"),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock) as mock_attach,
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
        ):
            db = AsyncMock()
            await prepare_workflow_run(workflow, {}, "user-1", db)

        mock_attach.assert_called_once_with(client, "agent-1", ["tool-1"], "user-1", db)


class TestPrepareChatRun:
    """Tests for prepare_chat_run."""

    @pytest.mark.asyncio
    async def test_basic_chat_run(self):
        """Returns rendered message and client."""
        client = MagicMock()

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock),
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
        ):
            db = AsyncMock()
            rendered_message, returned_client = await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=[],
                skill_ids=[],
                user_id="user-1",
                db=db,
                message="Hello agent",
            )

        assert rendered_message == "Hello agent"
        assert returned_client == client

    @pytest.mark.asyncio
    async def test_propose_tool_status_prepended(self):
        """Propose tool status note is prepended to message."""
        client = MagicMock()
        status_note = "[System: Tool creation ENABLED]\n"

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock),
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=status_note),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
        ):
            db = AsyncMock()
            rendered_message, _ = await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=[],
                skill_ids=[],
                user_id="user-1",
                db=db,
                message="Hello",
            )

        assert rendered_message.startswith("[System:")
        assert "Hello" in rendered_message

    @pytest.mark.asyncio
    async def test_web_search_status_prepended(self):
        """Web search status note is prepended to message."""
        client = MagicMock()
        status_note = "[System: Web search ENABLED]\n"

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock),
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=status_note),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
        ):
            db = AsyncMock()
            rendered_message, _ = await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=[],
                skill_ids=[],
                user_id="user-1",
                db=db,
                message="Search",
            )

        assert rendered_message.startswith("[System:")
        assert "Search" in rendered_message

    @pytest.mark.asyncio
    async def test_with_skills_inserts_into_archival_memory(self):
        """Skills are inserted into archival memory and prefix prepended."""
        client = MagicMock()
        skill = MagicMock()
        skill.name = "test-skill"
        skill.content = "Skill content"

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock),
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[skill]),
            patch("app.agents.run_prep.get_skill_tool_ids", new_callable=AsyncMock, return_value=[]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_skills_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["test-skill"],
            ),
            patch("app.agents.run_prep._fetch_skill_files", new_callable=AsyncMock, return_value={}),
        ):
            db = AsyncMock()
            rendered_message, _ = await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=[],
                skill_ids=["skill-1"],
                user_id="user-1",
                db=db,
                message="Hello",
            )

        assert "test-skill" in rendered_message

    @pytest.mark.asyncio
    async def test_skill_tool_ids_merged_into_attach(self):
        """Skill-linked tools are merged with user-selected tools and attached."""
        client = MagicMock()
        skill = MagicMock()
        skill.name = "test-skill"
        skill.content = "Skill content"
        skill.id = "skill-uuid-1"

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock) as mock_attach,
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[skill]),
            patch("app.agents.run_prep.get_skill_tool_ids", new_callable=AsyncMock, return_value=["tool-from-skill"]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_skills_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["test-skill"],
            ),
            patch("app.agents.run_prep._fetch_skill_files", new_callable=AsyncMock, return_value={}),
        ):
            db = AsyncMock()
            rendered_message, _ = await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=["user-tool"],
                skill_ids=["skill-1"],
                user_id="user-1",
                db=db,
                message="Hello",
            )

        # Both user-selected and skill-linked tools should be attached
        mock_attach.assert_awaited_once()
        attached_tool_ids = mock_attach.call_args[0][2]
        assert "user-tool" in attached_tool_ids
        assert "tool-from-skill" in attached_tool_ids

    @pytest.mark.asyncio
    async def test_skill_tool_ids_deduped(self):
        """Skill-linked tools that overlap with user-selected tools are deduped."""
        client = MagicMock()
        skill = MagicMock()
        skill.name = "test-skill"
        skill.content = "Skill content"
        skill.id = "skill-uuid-1"

        with (
            patch("app.letta_client.get_letta_client", return_value=client),
            patch("app.agents.run_prep.attach_tools_to_agent", new_callable=AsyncMock) as mock_attach,
            patch("app.agents.run_prep.ensure_propose_tool", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_web_search", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.ensure_fetch_docs", new_callable=AsyncMock, return_value=None),
            patch("app.agents.run_prep.get_skills_by_ids", new_callable=AsyncMock, return_value=[skill]),
            patch("app.agents.run_prep.get_skill_tool_ids", new_callable=AsyncMock, return_value=["shared-tool"]),
            patch("app.agents.run_prep.ensure_archival_memory_search", new_callable=AsyncMock),
            patch(
                "app.agents.run_prep.insert_skills_into_archival_memory",
                new_callable=AsyncMock,
                return_value=["test-skill"],
            ),
            patch("app.agents.run_prep._fetch_skill_files", new_callable=AsyncMock, return_value={}),
        ):
            db = AsyncMock()
            await prepare_chat_run(
                agent_id="agent-1",
                tool_ids=["shared-tool"],
                skill_ids=["skill-1"],
                user_id="user-1",
                db=db,
                message="Hello",
            )

        mock_attach.assert_awaited_once()
        attached_tool_ids = mock_attach.call_args[0][2]
        # shared-tool should appear only once
        assert attached_tool_ids.count("shared-tool") == 1
