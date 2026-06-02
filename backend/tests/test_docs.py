"""Tests for documentation fetch functionality."""

from app.docs.sanitize import (
    _is_allowed_docs_domain,
    html_to_text,
    truncate_docs,
    validate_docs_url,
)


class TestIsAllowedDocsDomain:
    """Tests for documentation domain allowlist."""

    def test_exact_match(self):
        assert _is_allowed_docs_domain("readthedocs.io") is True
        assert _is_allowed_docs_domain("pypi.org") is True
        assert _is_allowed_docs_domain("github.com") is True

    def test_subdomain_match(self):
        assert _is_allowed_docs_domain("falconpy.readthedocs.io") is True
        assert _is_allowed_docs_domain("docs.python.org") is True  # exact match
        assert _is_allowed_docs_domain("something.github.com") is True

    def test_blocked_domain(self):
        assert _is_allowed_docs_domain("evil.com") is False
        assert _is_allowed_docs_domain("notdocs.io") is False
        assert _is_allowed_docs_domain("internal.company.com") is False

    def test_raw_githubusercontent_blocked(self):
        """raw.githubusercontent.com removed — raw text bypasses HTML sanitization."""
        assert _is_allowed_docs_domain("raw.githubusercontent.com") is False

    def test_ultrasaurus_blocked(self):
        """docs.ultrasaurus.com removed — legacy entry with no justification."""
        assert _is_allowed_docs_domain("docs.ultrasaurus.com") is False

    def test_case_insensitive(self):
        assert _is_allowed_docs_domain("ReadTheDocs.io") is True
        assert _is_allowed_docs_domain("GITHUB.COM") is True


class TestValidateDocsUrl:
    """Tests for documentation URL validation."""

    def test_empty_url(self):
        is_valid, error, _ = validate_docs_url("")
        assert is_valid is False
        assert "required" in error.lower()

    def test_blocked_domain(self):
        is_valid, error, _ = validate_docs_url("https://evil.com/docs")
        assert is_valid is False
        assert "not in the documentation allowlist" in error

    def test_invalid_scheme(self):
        is_valid, error, _ = validate_docs_url("ftp://readthedocs.io/docs")
        assert is_valid is False
        assert "scheme" in error.lower()

    def test_localhost_blocked(self):
        is_valid, error, _ = validate_docs_url("http://localhost:8000/docs")
        assert is_valid is False


class TestHtmlToText:
    """Tests for HTML-to-text conversion."""

    def test_simple_html(self):
        html = "<html><body><p>Hello world</p></body></html>"
        text = html_to_text(html)
        assert "Hello world" in text

    def test_strips_scripts(self):
        html = "<html><body><script>alert('xss')</script><p>Content</p></body></html>"
        text = html_to_text(html)
        assert "alert" not in text
        assert "Content" in text

    def test_strips_styles(self):
        html = "<html><body><style>body{color:red}</style><p>Content</p></body></html>"
        text = html_to_text(html)
        assert "color" not in text
        assert "Content" in text

    def test_preserves_link_text(self):
        html = '<p>Click <a href="https://example.com">here</a> for docs</p>'
        text = html_to_text(html)
        assert "here" in text
        assert "docs" in text

    def test_block_elements_add_newlines(self):
        html = "<div>Line 1</div><div>Line 2</div>"
        text = html_to_text(html)
        assert "Line 1" in text
        assert "Line 2" in text
        assert "\n" in text

    def test_empty_html(self):
        text = html_to_text("")
        assert text == ""

    def test_entity_decoding(self):
        html = "<p>&amp; &lt; &gt;</p>"
        text = html_to_text(html)
        assert "& < >" in text


class TestTruncateDocs:
    """Tests for documentation truncation."""

    def test_short_text_unchanged(self):
        text = "Short documentation"
        result = truncate_docs(text, max_length=100)
        assert result == text

    def test_long_text_truncated(self):
        text = "x" * 6000
        result = truncate_docs(text, max_length=5000)
        assert len(result) < 6000
        assert "truncated" in result

    def test_default_max_length(self):
        text = "x" * 25000
        result = truncate_docs(text)
        assert len(result) < 25000


class TestFetchDocsTool:
    """Tests for the fetch_docs tool source code generation."""

    def test_build_source_contains_agent_id(self):
        from app.docs.fetch_docs_tool import build_fetch_docs_source

        source = build_fetch_docs_source(agent_id="agent-123")
        assert "agent-123" in source

    def test_build_source_contains_httpx(self):
        from app.docs.fetch_docs_tool import build_fetch_docs_source

        source = build_fetch_docs_source(agent_id="agent-123")
        assert "httpx" in source

    def test_build_source_calls_agent_endpoint(self):
        from app.docs.fetch_docs_tool import build_fetch_docs_source

        source = build_fetch_docs_source(agent_id="agent-123")
        assert "/api/docs/fetch/agent" in source

    def test_schema_has_url_required(self):
        from app.docs.fetch_docs_tool import FETCH_DOCS_SCHEMA

        assert "url" in FETCH_DOCS_SCHEMA["properties"]
        assert "url" in FETCH_DOCS_SCHEMA["required"]

    def test_schema_has_package_optional(self):
        from app.docs.fetch_docs_tool import FETCH_DOCS_SCHEMA

        assert "package" in FETCH_DOCS_SCHEMA["properties"]
        assert "package" not in FETCH_DOCS_SCHEMA["required"]

    def test_tool_docstring_warns_about_untrusted_content(self):
        from app.docs.fetch_docs_tool import _FETCH_DOCS_TOOL_TEMPLATE

        assert "adversarial" in _FETCH_DOCS_TOOL_TEMPLATE
        assert "do not follow" in _FETCH_DOCS_TOOL_TEMPLATE.lower()

    def test_description_warns_about_untrusted_content(self):
        from app.docs.fetch_docs_tool import FETCH_DOCS_DESCRIPTION

        assert "adversarial" in FETCH_DOCS_DESCRIPTION
        assert "do not follow" in FETCH_DOCS_DESCRIPTION.lower()
