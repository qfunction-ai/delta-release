"""Unified code safety constants.

Used by both the backend (sanitize.py) and the eval container (app.py)
to enforce consistent security policies across tool source code validation
and FnCheck expression validation.

Also provides secret detection (entropy + regex) for Layer 1 (tool source
code scanning) and Layer 2 (chat input scanning). The entropy + regex logic
is duplicated in the Letta fork at letta/security/secret_scanner.py for
Layer 3 (agent memory scanning). Changes here MUST be mirrored there.
"""

import math
import re
from collections import Counter

# Modules that are completely banned — no legitimate use in tools
DANGEROUS_MODULES = {
    "subprocess",
    "ctypes",
    "pickle",
    "marshal",
    "shutil",
    "commands",
    "signal",
    "socket",
    "ftplib",
    "telnetlib",
    "smtplib",
    "xmlrpc",
    "ssl",
    "pty",        # pseudo-terminal — enables terminal escape injection
    "runpy",      # run_module / run_path — arbitrary code execution
    "zipfile",    # archive extraction — path traversal risk
    "tarfile",    # archive extraction — path traversal risk
    "tempfile",   # temp file creation — not needed in sandbox tools
    "webbrowser", # opens URLs on host — SSRF/info leak
}

# Modules with restricted access — import allowed, but only safe operations
RESTRICTED_MODULES = {
    "os",
    "http",
    "urllib",
    "importlib",
}

# Safe operations on restricted modules (keyed by module)
# makedirs is allowed because tools need to create staging subdirectories
# before writing files (e.g., LETTA_STAGING_DIR). The sandbox already
# constrains where writes can go.
SAFE_OS_OPS = {"getenv", "environ", "path", "name", "sep", "linesep", "curdir", "pardir", "makedirs"}

# Dangerous built-in functions
DANGEROUS_BUILTINS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "import_module",
    "globals",
    "locals",
    "vars",
    "dir",
    "breakpoint",
    "input",
}

# Dangerous attributes (checked on any object access)
DANGEROUS_ATTRS = {
    "system",
    "popen",
    "exec",
    "spawn",
    "kill",
    "remove",
    "unlink",
    "rmtree",
}

# Dangerous dunder attributes used in Python sandbox escapes
DANGEROUS_DUNDER_ATTRS = {
    "__builtins__",
    "__globals__",
    "__class__",
    "__bases__",
    "__subclasses__",
    "__dict__",
    "__mro__",
    "__code__",
    "__closure__",
}

# Safe builtins that FnCheck expressions can use
# NOTE: getattr, hasattr, and type are intentionally EXCLUDED — they enable
# Python sandbox escape via dunder attribute access (e.g., __class__.__bases__).
SAFE_BUILTINS = {
    "len", "str", "int", "float", "bool", "list", "dict", "set",
    "tuple", "any", "all", "isinstance", "abs", "min", "max",
    "sorted", "reversed", "enumerate", "zip", "range",
    "round", "sum",
}

# String methods that FnCheck expressions can call on string objects.
# These are NOT builtins — they're methods on str instances. Listed
# separately to avoid confusion with actual built-in functions.
SAFE_STRING_METHODS = {
    "lower", "upper", "strip", "split", "join",
    "replace", "startswith", "endswith", "contains", "in",
    "find", "rfind", "count", "title", "capitalize",
}

# ---------------------------------------------------------------------------
# Secret detection — entropy (primary) + regex (confirmatory)
# ---------------------------------------------------------------------------
# MIRROR: letta/security/secret_scanner.py in the Letta fork duplicates
# this logic for Layer 3. Changes here MUST be mirrored there.

# Variable names that suggest a secret value
_KEY_LIKE_NAMES = re.compile(
    r'(?i)(?:api[_-]?key|apikey|access[_-]?key|secret|token|'
    r'password|credential|private[_-]?key|auth[_-]?token|bearer)',
)

_ENTROPY_THRESHOLD = 4.5   # bits per character
_ENTROPY_MIN_LENGTH = 20   # minimum string length to check


def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string in bits per character."""
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def is_high_entropy(s: str) -> bool:
    """Check if a string has high enough entropy to be a likely secret."""
    return len(s) >= _ENTROPY_MIN_LENGTH and shannon_entropy(s) >= _ENTROPY_THRESHOLD


# Regex patterns for well-known secret formats.
# Each entry: (regex_pattern, label_for_warnings)
# Keep this list SHORT — entropy detection catches the long tail.
SECRET_PATTERNS: list[tuple[str, str]] = [
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID"),
    (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----', "Private key (PEM)"),
    (r'gh[psou]_[A-Za-z0-9_]{36,}', "GitHub token"),
    (r'xox[bpa]-[A-Za-z0-9\-]{10,}', "Slack token"),
    (r'(?:sk|rk)_live_[A-Za-z0-9]{24,}', "Stripe key"),
]

# Pre-compile patterns for performance
_COMPILED_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p), label) for p, label in SECRET_PATTERNS
]


def scan_for_secrets(text: str) -> list[str]:
    """Scan text for secret patterns. Returns list of labels (e.g. ["AWS Access Key ID"]).

    Two signals:
    1. Regex: known-format matches (AWS keys, GitHub tokens, etc.)
    2. Entropy: high-entropy substrings of 20+ chars (catches unknown formats)

    Does NOT return matched values — only labels to display in warnings.
    """
    labels = []
    for pattern, label in _COMPILED_SECRET_PATTERNS:
        if pattern.search(text):
            labels.append(label)
    # Entropy check: scan for high-entropy substrings
    # Extract "word-like" tokens (sequences of non-whitespace 20+ chars)
    for token in re.findall(r'\S{20,}', text):
        if is_high_entropy(token):
            labels.append("High-entropy secret")
            break  # One hit is enough; don't spam
    return labels


def scan_for_secrets_regex(text: str) -> list[str]:
    """Scan text for known secret formats only (regex, no entropy check).

    Use this when entropy is already checked separately (e.g., in the AST
    visitor where key-like variable names provide the entropy signal).
    """
    labels = []
    for pattern, label in _COMPILED_SECRET_PATTERNS:
        if pattern.search(text):
            labels.append(label)
    return labels
