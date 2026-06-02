"""Error handling utilities — prevent leaking internal details to clients."""

import logging
import re

logger = logging.getLogger(__name__)

# Generic messages for different error categories
GENERIC_MESSAGES = {
    "letta": "Failed to communicate with the AI service. Please try again later.",
    "docker": "Container management is currently unavailable.",
    "sidecar": "Package management service error. Please try again later.",
    "eval": "Eval runner service error. Please try again later.",
    "internal": "An internal error occurred. Please try again later.",
}

# Patterns that may leak internal paths or system details
_INTERNAL_PATTERNS = [
    re.compile(r"/[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+"),  # Unix paths
    re.compile(r"[A-Z]:\\[a-zA-Z0-9_.-]+(?:\\[a-zA-Z0-9_.-]+)+"),  # Windows paths
    re.compile(r"Traceback \(most recent call last\)"),  # Python tracebacks
    re.compile(r'File "[^"]+", line \d+'),  # File references in tracebacks
]


def safe_error(detail: str, category: str = "internal") -> str:
    """Return a safe error message for the client, logging the real detail."""
    logger.error("[%s] %s", category, detail)
    return GENERIC_MESSAGES.get(category, GENERIC_MESSAGES["internal"])


def letta_error_detail(error: Exception) -> str:
    """Return a safe error detail for Letta API failures.

    Passes through user-actionable errors verbatim (parse/syntax errors,
    400 Bad Request validation errors), sanitizes everything else.
    """
    error_detail = str(error)
    if "parse" in error_detail.lower() or "syntax" in error_detail.lower():
        return sanitize_error_detail(error_detail)
    # 400 Bad Request errors are validation errors the user can fix
    from letta_client import BadRequestError

    if isinstance(error, BadRequestError):
        return sanitize_error_detail(error_detail)
    return safe_error(error_detail, "letta")


def sanitize_error_detail(detail: str, max_length: int = 200) -> str:
    """Sanitize an error detail string for safe client display.

    Strips internal paths, tracebacks, and truncates length.
    Use for user-actionable errors (validation, parse errors) where
    the message needs to be informative but not leak internals.
    """
    result = detail
    for pattern in _INTERNAL_PATTERNS:
        result = pattern.sub("[path]", result)
    # Truncate to prevent large error responses
    if len(result) > max_length:
        result = result[: max_length - 3] + "..."
    return result
