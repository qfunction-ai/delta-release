"""Documentation URL validation and content sanitization.

Provides SSRF-safe fetching of documentation pages for agent tool proposals.
Only allows known documentation domains and strips all HTML to plain text.
"""

import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.ssrf import validate_api_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain allowlist — only these domains may be fetched for documentation
# ---------------------------------------------------------------------------
_ALLOWED_DOCS_DOMAINS: dict[str, list[str]] = {
    # domain: [description]
    "readthedocs.io": ["Read the Docs — hosted documentation"],
    "pypi.org": ["Python Package Index"],
    "pythonhosted.org": ["PyPI package files"],
    "files.pythonhosted.org": ["PyPI package file hosting"],
    "github.com": ["GitHub — README and docs in repos"],
    "raw.githubusercontent.com": ["GitHub raw file hosting — README and source files"],
    "docs.python.org": ["Official Python documentation"],
    "developers.google.com": ["Google API documentation"],
    "docs.microsoft.com": ["Microsoft documentation"],
    "learn.microsoft.com": ["Microsoft Learn documentation"],
    "docs.aws.amazon.com": ["AWS documentation"],
}

# Maximum response size for documentation fetch (1 MB)
MAX_DOCS_RESPONSE_SIZE = 1_048_576

# Maximum text length returned to the agent (characters)
# 20k is enough for most API reference pages — the agent needs to see
# actual class names, method signatures, and usage examples, not just
# the intro paragraph.  If the page is longer, the truncation notice
# tells the agent to fetch a more specific subpage.
MAX_DOCS_TEXT_LENGTH = 20_000


def _is_allowed_docs_domain(hostname: str) -> bool:
    """Check if a hostname is in the documentation domain allowlist.

    Supports exact matches and subdomain matches (e.g., any project on
    readthedocs.io like my-project.readthedocs.io).
    """
    hostname = hostname.lower()
    for allowed_domain in _ALLOWED_DOCS_DOMAINS:
        if hostname == allowed_domain:
            return True
        # Allow subdomains: my-project.readthedocs.io
        if hostname.endswith(f".{allowed_domain}"):
            return True
    return False


def validate_docs_url(url: str) -> tuple[bool, str, str]:
    """Validate a documentation URL for safe fetching.

    Checks:
    1. URL is well-formed
    2. Hostname is in the documentation domain allowlist
    3. URL resolves to a public IP (SSRF protection via validate_api_url)

    Returns (is_valid, error_message, resolved_ip) same as validate_api_url.
    """
    if not url:
        return False, "URL is required", ""

    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Invalid URL format", ""

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a hostname", ""

    # Check scheme
    if parsed.scheme not in ("http", "https"):
        return False, f"URL scheme '{parsed.scheme}' is not allowed. Use http:// or https://", ""

    # Check domain allowlist
    if not _is_allowed_docs_domain(hostname):
        allowed = ", ".join(sorted(_ALLOWED_DOCS_DOMAINS.keys()))
        return False, f"Domain '{hostname}' is not in the documentation allowlist. Allowed domains: {allowed}", ""

    # SSRF protection: resolve and validate IP
    return validate_api_url(url)


class _HTMLToText(HTMLParser):
    """Simple HTML-to-text converter.

    Strips all tags, converts block elements to newlines, and decodes
    entities. No external dependencies required.
    """

    BLOCK_TAGS = frozenset(
        {
            "p",
            "div",
            "br",
            "hr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "table",
            "tr",
            "td",
            "th",
            "pre",
            "blockquote",
            "section",
            "article",
            "header",
            "footer",
            "nav",
            "main",
        }
    )

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip = False  # skip content inside script/style tags

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag in self.BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self._skip = False
        elif tag in self.BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str):
        if not self._skip:
            self._pieces.append(data)

    def handle_entityref(self, name: str):
        if not self._skip:
            from html import unescape

            self._pieces.append(unescape(f"&{name};"))

    def handle_charref(self, name: str):
        if not self._skip:
            from html import unescape

            self._pieces.append(unescape(f"&#{name};"))

    def get_text(self) -> str:
        """Return the extracted text, cleaned up."""
        text = "".join(self._pieces)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove excessive whitespace within lines
        lines = []
        for line in text.split("\n"):
            lines.append(re.sub(r"[ \t]+", " ", line).strip())
        return "\n".join(lines).strip()


def html_to_text(html: str) -> str:
    """Convert HTML content to plain text.

    Strips all tags, removes script/style content, and normalizes
    whitespace. No external dependencies required.
    """
    converter = _HTMLToText()
    converter.feed(html)
    return converter.get_text()


def truncate_docs(text: str, max_length: int = MAX_DOCS_TEXT_LENGTH) -> str:
    """Truncate documentation text to the maximum length.

    Adds a truncation notice if the text was cut short.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 100] + "\n\n... [documentation truncated]"
