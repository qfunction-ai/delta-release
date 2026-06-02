"""Tests for agents prompts — skill/lesson prefix builders and message extraction."""

from unittest.mock import MagicMock

from app.agents.prompts import (
    build_lesson_prompt_prefix,
    build_skill_inline_block,
    build_skill_prompt_prefix,
    extract_message_parts,
)


class TestBuildSkillPromptPrefix:
    """Tests for build_skill_prompt_prefix."""

    def test_includes_skill_names(self):
        """Prefix includes the skill names."""
        result = build_skill_prompt_prefix(["search", "analyze"])
        assert "search" in result
        assert "analyze" in result

    def test_includes_inline_reference(self):
        """Prefix mentions that skill instructions are provided below."""
        result = build_skill_prompt_prefix(["search"])
        assert "instructions are provided below" in result

    def test_includes_rules(self):
        """Prefix includes skill usage rules."""
        result = build_skill_prompt_prefix(["search"])
        assert "Follow EVERY step" in result

    def test_no_archival_memory_search_instruction(self):
        """Prefix no longer tells agent to search archival memory."""
        result = build_skill_prompt_prefix(["search"])
        assert "archival_memory_search" not in result

    def test_includes_conditional_language(self):
        """Prefix says to respond directly for unrelated questions."""
        result = build_skill_prompt_prefix(["search"])
        assert "respond directly" in result


class TestBuildSkillInlineBlock:
    """Tests for build_skill_inline_block."""

    def test_includes_skill_content(self):
        """Inline block includes the skill's content."""
        skill = MagicMock()
        skill.name = "test-skill"
        skill.content = "Step 1: Do something\nStep 2: Do something else"
        result = build_skill_inline_block([skill])
        assert "Step 1: Do something" in result
        assert "Step 2: Do something else" in result

    def test_wraps_with_skill_name(self):
        """Inline block wraps content with skill name markers."""
        skill = MagicMock()
        skill.name = "my-skill"
        skill.content = "content here"
        result = build_skill_inline_block([skill])
        assert "[Skill: my-skill]" in result
        assert "End of skill: my-skill" in result

    def test_empty_for_no_skills(self):
        """Returns empty string for empty skill list."""
        result = build_skill_inline_block([])
        assert result == ""

    def test_empty_for_no_content(self):
        """Returns empty string when skill has no content."""
        skill = MagicMock()
        skill.name = "empty-skill"
        skill.content = None
        result = build_skill_inline_block([skill])
        assert result == ""

    def test_multiple_skills(self):
        """Handles multiple skills in one block."""
        s1 = MagicMock()
        s1.name = "skill-a"
        s1.content = "Content A"
        s1.id = "id-a"
        s2 = MagicMock()
        s2.name = "skill-b"
        s2.content = "Content B"
        s2.id = "id-b"
        result = build_skill_inline_block([s1, s2])
        assert "[Skill: skill-a]" in result
        assert "[Skill: skill-b]" in result

    def test_includes_skill_files(self):
        """Inline block includes text skill files."""
        skill = MagicMock()
        skill.name = "report-skill"
        skill.content = "Step 1: Get alerts"
        skill.id = "skill-123"
        files = {"skill-123": [("assets/template.md", "# Template\nFill in here")]}
        result = build_skill_inline_block([skill], files)
        assert "[Skill File: report-skill/assets/template.md]" in result
        assert "# Template" in result
        assert "End of skill file: assets/template.md" in result

    def test_ignores_skill_files_for_wrong_skill(self):
        """Skill files for a different skill ID are not included."""
        skill = MagicMock()
        skill.name = "my-skill"
        skill.content = "content"
        skill.id = "skill-abc"
        files = {"skill-xyz": [("assets/other.md", "other content")]}
        result = build_skill_inline_block([skill], files)
        assert "other content" not in result

    def test_no_files_param_works(self):
        """Works without skill_files parameter (backward compat)."""
        skill = MagicMock()
        skill.name = "simple"
        skill.content = "just content"
        skill.id = "skill-1"
        result = build_skill_inline_block([skill])
        assert "just content" in result
        assert "Skill File" not in result


class TestBuildLessonPromptPrefix:
    """Tests for build_lesson_prompt_prefix."""

    def test_includes_lesson_count(self):
        """Prefix includes the lesson count."""
        result = build_lesson_prompt_prefix(5)
        assert "5" in result

    def test_includes_archival_memory_search(self):
        """Prefix includes archival_memory_search instructions."""
        result = build_lesson_prompt_prefix(1)
        assert "archival_memory_search" in result

    def test_includes_tags_lessons(self):
        """Prefix includes the lessons tag requirement."""
        result = build_lesson_prompt_prefix(1)
        assert '"lessons"' in result


class TestExtractMessageParts:
    """Tests for extract_message_parts."""

    def test_extract_assistant_message(self):
        """Extracts assistant message content."""
        msg = MagicMock()
        msg.message_type = "assistant_message"
        msg.content = "Hello world"
        output, reasoning = extract_message_parts([msg])
        assert output == "Hello world"
        assert reasoning is None

    def test_extract_reasoning_message(self):
        """Reasoning-only messages get promoted to output when no assistant message exists."""
        msg = MagicMock()
        msg.message_type = "reasoning_message"
        msg.reasoning = "I think therefore I am"
        output, reasoning = extract_message_parts([msg], include_reasoning=True)
        # Fallback: reasoning promoted to output since no assistant_message present
        assert output == "I think therefore I am"
        assert reasoning is None

    def test_reasoning_excluded_when_not_requested(self):
        """Reasoning-only messages get promoted to output even when include_reasoning=False."""
        msg = MagicMock()
        msg.message_type = "reasoning_message"
        msg.reasoning = "thinking"
        output, reasoning = extract_message_parts([msg], include_reasoning=False)
        # Fallback: reasoning promoted to output since no assistant_message present
        assert output == "thinking"
        assert reasoning is None

    def test_empty_messages(self):
        """Returns (None, None) for empty message list."""
        output, reasoning = extract_message_parts([])
        assert output is None
        assert reasoning is None

    def test_mixed_messages(self):
        """Extracts both assistant and reasoning from mixed messages."""
        assistant_msg = MagicMock()
        assistant_msg.message_type = "assistant_message"
        assistant_msg.content = "result"

        reasoning_msg = MagicMock()
        reasoning_msg.message_type = "reasoning_message"
        reasoning_msg.reasoning = "thought process"

        output, reasoning = extract_message_parts([assistant_msg, reasoning_msg], include_reasoning=True)
        assert output == "result"
        assert reasoning == "thought process"

    def test_empty_content_skipped(self):
        """Messages with empty content are skipped."""
        msg = MagicMock()
        msg.message_type = "assistant_message"
        msg.content = ""
        output, reasoning = extract_message_parts([msg])
        assert output is None
