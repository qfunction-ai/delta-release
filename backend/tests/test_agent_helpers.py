"""Tests for agent helpers — archival memory deduplication."""

from unittest.mock import MagicMock

import pytest

from app.agents.archival_memory import (
    _passage_tags_exist,
    insert_lessons_into_archival_memory,
    insert_skills_into_archival_memory,
)


class TestPassageTagsExist:
    """Tests for _passage_tags_exist dedup check."""

    def test_returns_true_when_passages_exist(self):
        """If search returns results, the passage exists."""
        mock_client = MagicMock()
        mock_passage = MagicMock()
        mock_client.agents.passages.search.return_value = [mock_passage]

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            _passage_tags_exist(mock_client, "agent-1", ["skills", "splunk"])
        )
        assert result is True
        mock_client.agents.passages.search.assert_called_once_with(
            agent_id="agent-1",
            query="splunk",
            tags=["skills", "splunk"],
            tag_match_mode="all",
            top_k=1,
        )

    def test_returns_false_when_no_passages(self):
        """If search returns empty, the passage doesn't exist."""
        mock_client = MagicMock()
        mock_client.agents.passages.search.return_value = []

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            _passage_tags_exist(mock_client, "agent-1", ["skills", "splunk"])
        )
        assert result is False

    def test_returns_false_on_exception(self):
        """If search throws, fail open — return False so insert proceeds."""
        import httpx

        mock_client = MagicMock()
        mock_client.agents.passages.search.side_effect = httpx.ConnectError("search failed")

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            _passage_tags_exist(mock_client, "agent-1", ["skills", "splunk"])
        )
        assert result is False


class TestInsertSkillsDedup:
    """Tests that insert_skills_into_archival_memory skips duplicates."""

    @pytest.mark.asyncio
    async def test_skips_existing_skill(self):
        """If a skill already exists in archival memory, don't insert it again."""
        mock_client = MagicMock()
        # Search returns a result — skill already exists
        mock_client.agents.passages.search.return_value = [MagicMock()]

        skill = MagicMock()
        skill.name = "splunk-search"

        result = await insert_skills_into_archival_memory("agent-1", [skill], mock_client)

        # Skill is counted as available even though it wasn't re-inserted
        assert result == ["splunk-search"]
        # create should NOT have been called
        mock_client.agents.passages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_inserts_new_skill(self):
        """If a skill doesn't exist, insert it."""
        mock_client = MagicMock()
        # Search returns empty — skill doesn't exist yet
        mock_client.agents.passages.search.return_value = []

        skill = MagicMock()
        skill.name = "splunk-search"
        skill.content = "# Splunk Search\nSteps here"

        result = await insert_skills_into_archival_memory("agent-1", [skill], mock_client)

        assert result == ["splunk-search"]
        mock_client.agents.passages.create.assert_called_once()


class TestInsertLessonsDedup:
    """Tests that insert_lessons_into_archival_memory skips duplicates."""

    @pytest.mark.asyncio
    async def test_skips_existing_lesson(self):
        """If a lesson already exists in archival memory, don't insert it again."""
        mock_client = MagicMock()
        mock_client.agents.passages.search.return_value = [MagicMock()]

        lesson = MagicMock()
        lesson.id = "lesson-1"
        lesson.category = "recovery"
        lesson.content = "Try increasing timeout"

        result = await insert_lessons_into_archival_memory("agent-1", [lesson], mock_client)

        assert result == ["recovery"]
        mock_client.agents.passages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_inserts_new_lesson(self):
        """If a lesson doesn't exist, insert it."""
        mock_client = MagicMock()
        mock_client.agents.passages.search.return_value = []

        lesson = MagicMock()
        lesson.id = "lesson-1"
        lesson.category = "recovery"
        lesson.content = "Try increasing timeout"

        result = await insert_lessons_into_archival_memory("agent-1", [lesson], mock_client)

        assert result == ["recovery"]
        mock_client.agents.passages.create.assert_called_once()
