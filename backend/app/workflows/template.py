"""Workflow template rendering."""

import re


def render_template(template: str, variables: dict[str, str]) -> str:
    """Render a prompt template with variable substitution.

    Uses a lambda replacement to prevent re.sub from interpreting
    backreferences (e.g., \\1, \\g<1>) in user-supplied variable values.
    """
    result = template
    for key, value in variables.items():
        pattern = r"\{\{\s*" + re.escape(key) + r"\s*\}\}"
        result = re.sub(pattern, lambda m: str(value), result)
    return result
