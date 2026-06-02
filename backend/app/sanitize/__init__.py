"""
Input sanitization utilities.

Prevents XSS, SQL injection, and other malicious input.
"""

import ast
import os
import re

from app.sanitize.code_visitors import DangerousCodeVisitor, SecretPatternVisitor  # noqa: F401

__all__ = [
    "sanitize_string",
    "validate_cron_expression",
    "validate_prompt_template",
    "sanitize_python_code",
    "validate_tool_source_code",
    "sanitize_filename",
    "sanitize_file_path",
    "validate_mime_type",
    "DangerousCodeVisitor",
    "SecretPatternVisitor",
]


def sanitize_string(value: str, max_length: int = 10000) -> str:
    """
    Sanitize a string input.

    - Remove control characters
    - Limit length

    Note: HTML escaping is NOT applied here because this function is used
    for data passed to APIs (e.g., tool descriptions sent to Letta).
    Use HTML escaping at render time instead.
    """
    if not isinstance(value, str):
        return value

    # Limit length
    if len(value) > max_length:
        value = value[:max_length]

    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

    return value


def validate_cron_expression(value: str) -> bool:
    """
    Validate cron expression format.

    Only allows standard 5-field cron:
    minute hour day month weekday

    Rejects expressions that run more frequently than every 5 minutes
    to prevent resource exhaustion from overly aggressive schedules.
    """
    if not value:
        return True  # Empty is allowed

    parts = value.strip().split()
    if len(parts) != 5:
        return False

    # Range bounds for each cron field
    _CRON_RANGES = {
        0: (0, 59),  # minute
        1: (0, 23),  # hour
        2: (1, 31),  # day
        3: (1, 12),  # month
        4: (0, 6),  # weekday
    }

    # Each part should contain only valid cron characters
    valid_pattern = re.compile(r"^[\d*,/\-]+$")

    minute_part = parts[0]

    for i, part in enumerate(parts):
        # Allow * and alphanumeric with , / -
        if part == "*":
            continue
        if not valid_pattern.match(part):
            return False

        lo, hi = _CRON_RANGES[i]
        step_match = re.match(r"^\*/(\d+)$", part)
        if step_match:
            step = int(step_match.group(1))
            if step < 1 or step > hi:
                return False
            continue
        for item in part.split(","):
            if "/" in item:
                # e.g., 1-10/2
                range_part, step_part = item.split("/", 1)
                try:
                    step = int(step_part)
                    if step < 1:
                        return False
                except ValueError:
                    return False
                item = range_part
            if "-" in item:
                # e.g., 1-5
                range_parts = item.split("-", 1)
                try:
                    start, end = int(range_parts[0]), int(range_parts[1])
                except ValueError:
                    return False
                if start < lo or end > hi or start > end:
                    return False
            else:
                # Single value
                try:
                    val = int(item)
                except ValueError:
                    return False
                if val < lo or val > hi:
                    return False

    # Reject schedules that run more frequently than every 5 minutes.
    # A minute field of "*" (every minute) or "*/N" where N < 5 is too
    # aggressive for automated agent workflows.
    if minute_part == "*":
        return False
    step_match = re.match(r"^\*/(\d+)$", minute_part)
    if step_match and int(step_match.group(1)) < 5:
        return False

    return True


def validate_prompt_template(template: str) -> tuple[bool, str]:
    """
    Validate a prompt template.

    Returns (is_valid, error_message).
    """
    if not template or not template.strip():
        return False, "Template cannot be empty"

    dangerous_patterns = [
        (r"<script", "Script tags not allowed"),
        (r"javascript:", "JavaScript protocol not allowed"),
        (r"on\w+\s*=", "Event handlers not allowed"),
        (r"data:", "Data URLs not allowed"),
        (r"vbscript:", "VBScript not allowed"),
    ]

    lower_template = template.lower()
    for pattern, message in dangerous_patterns:
        if re.search(pattern, lower_template, re.IGNORECASE):
            return False, message

    # Validate variable format: {{variable_name}}
    # Only allow alphanumeric and underscore in variable names
    var_pattern = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
    var_pattern.findall(template)  # validate regex matches

    malformed = re.findall(r"\{[^{].*?\}", template)
    if malformed:
        # Only flag if it looks like a partial variable that isn't
        # part of a valid {{variable}} pattern
        for m in malformed:
            if "{" in m and "}" in m and not m.startswith("{{"):
                # Skip if this match is a substring of a valid {{var}}
                # (e.g., "{var}" inside "{{var}}")
                inner = m[1:]  # e.g., "var}" from "{var}"
                if ("{{" + inner) in template:
                    continue
                return False, f"Malformed variable syntax: {m}"

    return True, ""


def sanitize_python_code(code: str) -> tuple[str, list[str]]:
    """
    Sanitize Python code for tool uploads using AST-based analysis.

    Returns (sanitized_code, warnings).
    Warnings are treated as blocking errors — callers should reject the upload
    if any warnings are present.

    NOTE: This is a best-effort defense-in-depth check, NOT a security boundary.
    The primary security boundary is Letta's sandbox execution environment.
    This sanitizer catches common dangerous patterns but cannot guarantee complete
    coverage — a determined attacker can find bypasses through obfuscation,
    metaclass tricks, or indirect code execution. If you need to run truly
    untrusted code, you need a proper sandbox, not an AST checker.
    """
    warnings = []

    code = code.replace("\x00", "")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        # If the code can't be parsed, reject it with the actual error
        return code, [f"Syntax error: {e.msg} (line {e.lineno})" if e.msg else "Code contains syntax errors"]

    visitor = DangerousCodeVisitor()
    visitor.visit(tree)
    warnings = visitor.warnings

    secret_visitor = SecretPatternVisitor()
    secret_visitor.visit(tree)
    warnings.extend(secret_visitor.warnings)

    return code, warnings


def validate_tool_source_code(source_code: str) -> str:
    """Sanitize tool source code and raise HTTPException if dangerous patterns found.

    Returns the sanitized code on success. Raises HTTPException(400) on warnings.
    This is the single entry point for tool source code validation — used by
    create, update, github import, and propose paths.
    """
    from fastapi import HTTPException, status

    sanitized_code, warnings = sanitize_python_code(source_code)
    if warnings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool source code contains potentially dangerous patterns: {'; '.join(warnings)}. "
            f"Letta's sandbox is the primary security boundary, but these patterns are blocked as defense-in-depth.",
        )
    return sanitized_code


# MIME type prefixes that are safe to serve inline.
# text/html is intentionally excluded to prevent stored XSS.
_SAFE_MIME_PREFIXES = (
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/yaml",
    "text/x-python",
    "application/json",
    "application/yaml",
    "application/xml",
    "application/pdf",
    "application/octet-stream",
    "image/",
    "video/",
    "audio/",
)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for use in Content-Disposition headers.

    Strips directory components, quotes, newlines, and control characters
    that could break the header format or enable header injection.
    """
    # Strip directory components
    filename = os.path.basename(filename)
    # Remove characters that break Content-Disposition quoted-string:
    # double quotes (breaks the quoted-string boundary), CR/LF (header
    # injection), and other control characters.
    filename = re.sub(r'["\r\n\x00-\x1f]', "", filename)
    # Collapse whitespace
    filename = re.sub(r"\s+", " ", filename).strip()
    # Fallback if empty after sanitization
    return filename or "download"


def sanitize_file_path(path: str) -> str:
    """Sanitize a file path for safe storage.

    Preserves directory structure but strips characters that could enable
    header injection when the path is later used in Content-Disposition
    (quotes, newlines, control characters). Also rejects path traversal.
    """
    # Reject path traversal
    if ".." in path or path.startswith("/"):
        path = os.path.basename(path)
    # Strip quotes, newlines, and control characters
    path = re.sub(r'["\r\n\x00-\x1f]', "", path)
    # Collapse whitespace
    path = re.sub(r"\s+", " ", path).strip()
    # Fallback if empty after sanitization
    return path or "unknown"


def validate_mime_type(mime_type: str) -> str:
    """Validate a MIME type is safe for inline serving.

    Returns the original type if it matches a safe prefix, otherwise
    falls back to application/octet-stream. text/html is rejected to
    prevent stored XSS via crafted skill file imports.
    """
    if any(mime_type.startswith(p) for p in _SAFE_MIME_PREFIXES):
        return mime_type
    return "application/octet-stream"
