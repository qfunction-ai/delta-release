"""Tests for lesson extraction logic."""

import uuid
from unittest.mock import MagicMock

from app.lessons.extractor import (
    _classify_error,
    _truncate_at_sentence,
    extract_lesson_text,
)


def _make_workflow(name="test-workflow"):
    w = MagicMock()
    w.name = name
    w.id = uuid.uuid4()
    return w


def _make_run(status="completed", output=None, error_message=None, steps_count=1):
    r = MagicMock()
    r.status = status
    r.output = output
    r.error_message = error_message
    r.steps_count = steps_count
    r.id = uuid.uuid4()
    return r


class TestClassifyError:
    def test_timeout(self):
        assert _classify_error("Connection timed out after 30s") == "timeout"

    def test_connection_refused(self):
        assert _classify_error("Connection refused on port 8080") == "connection_error"

    def test_auth_401(self):
        assert _classify_error("401 Unauthorized") == "auth_error"

    def test_auth_403(self):
        assert _classify_error("403 Forbidden") == "auth_error"

    def test_not_found_404(self):
        assert _classify_error("404 Not Found") == "not_found"

    def test_rate_limited(self):
        assert _classify_error("429 rate limit exceeded") == "rate_limited"

    def test_syntax_error(self):
        assert _classify_error("SyntaxError: invalid syntax") == "syntax_error"

    def test_generic(self):
        assert _classify_error("Something went wrong") == "execution_error"


class TestTruncateAtSentence:
    def test_short_text_unchanged(self):
        text = "Short text."
        assert _truncate_at_sentence(text, 200) == text

    def test_truncates_at_sentence(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _truncate_at_sentence(text, 30)
        assert result.endswith(".")
        # Truncation should produce something shorter than the full text
        assert len(result) < len(text)

    def test_fallback_to_ellipsis(self):
        text = "no punctuation here just a long string of words that keeps going"
        result = _truncate_at_sentence(text, 30)
        assert result.endswith("...")


class TestExtractLessonText:
    def test_failed_run_produces_recovery_lesson(self):
        run = _make_run(status="failed", error_message="Connection timed out after 30s")
        workflow = _make_workflow("splunk-search")
        result = extract_lesson_text(run, workflow)
        assert result is not None
        category, content = result
        assert category == "recovery"
        assert "splunk-search" in content
        assert "timeout" in content

    def test_completed_run_produces_strategy_lesson(self):
        run = _make_run(
            status="completed",
            output="Found 3 suspicious login attempts from IP 192.168.1.100. All attempts occurred within a 5-minute window.",
            steps_count=3,
        )
        workflow = _make_workflow("threat-hunt")
        result = extract_lesson_text(run, workflow)
        assert result is not None
        category, content = result
        assert category == "strategy"
        assert "threat-hunt" in content

    def test_high_step_count_produces_optimization_lesson(self):
        run = _make_run(
            status="completed",
            output="Completed vulnerability scan across 50 endpoints. Found 12 critical issues.",
            steps_count=15,
        )
        workflow = _make_workflow("vuln-scan")
        result = extract_lesson_text(run, workflow)
        assert result is not None
        category, content = result
        assert category == "optimization"
        assert "15 steps" in content

    def test_short_output_skipped(self):
        run = _make_run(status="completed", output="OK", steps_count=1)
        workflow = _make_workflow("short-workflow")
        result = extract_lesson_text(run, workflow)
        assert result is None

    def test_empty_output_skipped(self):
        run = _make_run(status="completed", output=None, steps_count=1)
        workflow = _make_workflow("empty-workflow")
        result = extract_lesson_text(run, workflow)
        assert result is None

    def test_failed_run_no_error_message_skipped(self):
        run = _make_run(status="failed", error_message=None, steps_count=1)
        workflow = _make_workflow("no-error-workflow")
        result = extract_lesson_text(run, workflow)
        assert result is None

    def test_recovery_lesson_includes_suggestion(self):
        run = _make_run(status="failed", error_message="401 Unauthorized")
        workflow = _make_workflow("auth-workflow")
        result = extract_lesson_text(run, workflow)
        assert result is not None
        _, content = result
        assert "credentials" in content.lower() or "auth" in content.lower()
