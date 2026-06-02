"""Tool proposal helpers — dry-run execution."""

import logging
import re

from app.async_utils import run_sync
from app.constants import LETTA_ERRORS

# Valid Python identifier pattern — used to prevent code injection
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

logger = logging.getLogger(__name__)


async def execute_dry_run(
    source_code: str,
    entry_point_name: str,
    json_schema: dict,
    pip_requirements: list[str] | None,
) -> tuple[str | None, str | None]:
    """Validate tool source code by creating a temporary tool in Letta.

    Returns (output, error) — one will be None.

    SECURITY: The previous implementation string-interpolated user-supplied
    source_code into a wrapper template, which was a code injection vector
    (triple-quoted strings could break out of the wrapper's indentation).
    The current approach creates the tool directly with the user's source
    code — no template, no interpolation, no injection risk. Letta's sandbox
    is the execution boundary; we just verify the tool can be created.
    """
    if not _IDENTIFIER_RE.match(entry_point_name):
        return None, f"Invalid entry point name: {entry_point_name}"

    for prop_name in (json_schema or {}).get("properties", {}):
        if not _IDENTIFIER_RE.match(prop_name):
            return None, f"Invalid schema property name: {prop_name}"

    from app.letta_client import call_letta, get_letta_client

    client = get_letta_client()

    # Build a minimal args schema for the dry-run tool.
    # We use the user's schema so Letta can validate the tool structure,
    # but we don't execute it — we just verify it can be created.
    args_schema = json_schema.copy() if json_schema else {}
    args_schema.setdefault("title", "DryRunInput")
    args_schema.setdefault("type", "object")
    args_schema.setdefault("properties", {})

    try:
        # Create a temporary tool with the user's source code directly.
        # No string interpolation, no wrapper template — the source code
        # is passed verbatim to Letta's tool creation API.
        temp_tool = await run_sync(
            client.tools.create,
            source_code=source_code,
            source_type="python",
            description=f"Dry run for {entry_point_name}",
            args_json_schema=args_schema,
            tags=["dry-run"],
        )

        await call_letta(client.tools.delete, temp_tool.id, raise_on_error=False)

        # The dry run succeeded — the tool code is syntactically valid and
        # can be registered with Letta. We verify:
        # 1. The code compiles (sanitizer already checked this)
        # 2. The entry point exists (tool_yaml.py checked this)
        # 3. The tool can be created in Letta (creation succeeded)
        return "Tool code compiles successfully. Entry point found. Dry run passed structural validation.", None

    except LETTA_ERRORS as e:
        error_msg = str(e)
        if "syntax" in error_msg.lower():
            return None, f"Syntax error in tool code: {error_msg}"
        if "import" in error_msg.lower():
            return None, f"Import error: {error_msg}"
        return None, f"Dry run failed: {error_msg}"
