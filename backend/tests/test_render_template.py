"""Tests for workflow template rendering."""

from app.workflows.routes import render_template


class TestRenderTemplate:
    def test_simple_substitution(self):
        """Single variable is substituted."""
        result = render_template("Search for {{query}}", {"query": "error"})
        assert result == "Search for error"

    def test_whitespace_around_variable(self):
        """Whitespace inside {{ }} is handled."""
        result = render_template("Search for {{ query }}", {"query": "error"})
        assert result == "Search for error"

    def test_multiple_variables(self):
        """Multiple variables are substituted."""
        result = render_template(
            "Search {{source}} for {{query}}",
            {"source": "splunk", "query": "error"},
        )
        assert result == "Search splunk for error"

    def test_unmatched_variable(self):
        """Variables not in the dict are left as-is."""
        result = render_template("Search for {{query}}", {"other": "value"})
        assert "{{query}}" in result

    def test_backreference_in_value(self):
        """Variable values containing backreference-like strings don't break rendering."""
        # \1 would be a backreference in re.sub replacement strings
        result = render_template("Path: {{path}}", {"path": r"test\1value"})
        assert r"test\1value" in result

    def test_empty_variables(self):
        """Empty variables dict leaves template unchanged."""
        template = "Search for {{query}}"
        result = render_template(template, {})
        assert result == template

    def test_special_chars_in_value(self):
        """Special regex characters in values are handled safely."""
        result = render_template("Search {{query}}", {"query": "$5.00 (group)"})
        assert "$5.00 (group)" in result
