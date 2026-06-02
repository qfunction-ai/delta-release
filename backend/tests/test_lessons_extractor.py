"""Tests for lesson extractor — text truncation, error classification, and lesson extraction."""

from unittest.mock import MagicMock

from app.lessons.extractor import (
    _classify_error,
    _truncate_at_sentence,
    extract_lesson_text,
)


class TestTruncateAtSentence:
    """Tests for _truncate_at_sentence."""

    def test_short_text_unchanged(self):
        assert _truncate_at_sentence("Short text") == "Short text"

    def test_truncates_at_sentence_boundary(self):
        text = "First sentence here. Second sentence. Third sentence that is very long."
        result = _truncate_at_sentence(text, max_len=40)
        assert result.endswith(".")
        assert len(result) <= 40

    def test_truncates_with_ellipsis_if_no_boundary(self):
        text = "No sentence boundaries here just a long continuous string"
        result = _truncate_at_sentence(text, max_len=30)
        assert result.endswith("...")
        assert len(result) == 33  # 30 + "..."

    def test_exclamation_mark(self):
        text = "Watch out! This is important. More text follows."
        result = _truncate_at_sentence(text, max_len=20)
        assert "!" in result or result.endswith("...")

    def test_question_mark(self):
        text = "Is this working? Yes it is. More text follows."
        result = _truncate_at_sentence(text, max_len=20)
        assert "?" in result or result.endswith("...")


class TestClassifyError:
    """Tests for _classify_error."""

    def test_timeout(self):
        assert _classify_error("Request timed out") == "timeout"

    def test_timed_out(self):
        assert _classify_error("The operation timed out after 30s") == "timeout"

    def test_connection_error(self):
        assert _classify_error("Connection refused to host") == "connection_error"

    def test_auth_error(self):
        assert _classify_error("401 Unauthorized") == "auth_error"

    def test_forbidden(self):
        assert _classify_error("403 Forbidden") == "auth_error"

    def test_not_found(self):
        assert _classify_error("404 Resource not found") == "not_found"

    def test_rate_limited(self):
        assert _classify_error("429 Rate limit exceeded") == "rate_limited"

    def test_syntax_error(self):
        assert _classify_error("Syntax error in query") == "syntax_error"

    def test_parse_error(self):
        assert _classify_error("Failed to parse response") == "syntax_error"

    def test_unknown_error(self):
        assert _classify_error("Something went wrong") == "execution_error"


class TestExtractLessonText:
    """Tests for extract_lesson_text."""

    def _make_run(self, status="failed", error_message=None, output=None, steps_count=0):
        run = MagicMock()
        run.status = status
        run.error_message = error_message
        run.output = output
        run.steps_count = steps_count
        return run

    def _make_workflow(self, name="test-workflow"):
        wf = MagicMock()
        wf.name = name
        return wf

    def test_failed_run_with_error(self):
        run = self._make_run(status="failed", error_message="Connection refused to host")
        wf = self._make_workflow()
        result = extract_lesson_text(run, wf)
        assert result is not None
        category, content = result
        assert category == "recovery"
        assert "connection_error" in content

    def test_timeout_error(self):
        run = self._make_run(status="failed", error_message="Request timed out")
        wf = self._make_workflow("scan-network")
        result = extract_lesson_text(run, wf)
        assert result is not None
        assert "timeout" in result[1]

    def test_completed_run_with_output(self):
        run = self._make_run(
            status="completed", output="Successfully scanned all targets and found 3 vulnerabilities", steps_count=5
        )
        wf = self._make_workflow("vuln-scan")
        result = extract_lesson_text(run, wf)
        assert result is not None
        assert result[0] == "strategy"

    def test_completed_run_high_steps(self):
        run = self._make_run(
            status="completed",
            output="Completed after many steps with detailed results and findings that are very informative",
            steps_count=15,
        )
        wf = self._make_workflow("deep-scan")
        result = extract_lesson_text(run, wf)
        assert result is not None
        assert result[0] == "optimization"

    def test_completed_run_short_output(self):
        run = self._make_run(status="completed", output="OK", steps_count=5)
        wf = self._make_workflow()
        result = extract_lesson_text(run, wf)
        assert result is None

    def test_completed_run_no_output(self):
        run = self._make_run(status="completed", output=None, steps_count=5)
        wf = self._make_workflow()
        result = extract_lesson_text(run, wf)
        assert result is None

    def test_failed_run_no_error_message(self):
        run = self._make_run(status="failed", error_message=None)
        wf = self._make_workflow()
        result = extract_lesson_text(run, wf)
        assert result is None

    def test_running_run_no_lesson(self):
        run = self._make_run(status="running")
        wf = self._make_workflow()
        result = extract_lesson_text(run, wf)
        assert result is None
