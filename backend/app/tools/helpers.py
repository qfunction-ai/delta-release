"""Shared helpers for tool registration, update, and storage.

Eliminates the repeated "sanitize name -> check unique -> ensure schema
title -> create/update in Letta -> store in DB" pattern across route modules.
"""

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TOOL_ACTIVE
from app.database import check_unique_for_user
from app.letta_client import call_letta, get_letta_client
from app.sanitize import sanitize_string
from app.tools.models import Tool
from app.utils import to_pascal_case

logger = logging.getLogger(__name__)


def _prepare_letta_schema(json_schema: dict, name: str) -> dict:
    """Copy and fix up a JSON schema for Letta's sandbox executor.

    Adds ``title`` (PascalCase of *name*) if missing and ensures
    ``properties`` and ``type`` defaults are present.
    """
    args_schema = json_schema.copy()
    if "title" not in args_schema:
        args_schema["title"] = to_pascal_case(name)
    args_schema.setdefault("properties", {})
    args_schema.setdefault("type", "object")
    return args_schema


def _build_full_tool_schema(name: str, description: str | None, args_schema: dict) -> dict:
    """Build the full tool JSON schema that Letta expects for tool creation.

    Letta's ToolCreate has two paths:
    1. ``json_schema`` — used directly, no source code parsing needed
    2. ``args_json_schema`` — Letta parses the source code to find the
       function name and docstring, then builds the full schema

    Path 2 has a bug: ``get_function_name_and_docstring`` uses ``ast.walk``
    which finds the *last* FunctionDef, not the first public one. When a tool
    has helper functions (e.g., ``_extract_compact``), the wrong function gets
    registered.

    Using path 1 (full ``json_schema``) bypasses the source code parsing
    entirely, so the tool name is always correct.
    """
    return {
        "name": name,
        "description": description or name,
        "parameters": args_schema,
    }


def parse_pip_requirements(reqs: list[str] | None) -> list[dict[str, Any]] | None:
    """Convert ['requests', 'paramiko==2.12.0'] to [{'name': 'requests'}, {'name': 'paramiko', 'version': '2.12.0'}]"""
    if not reqs:
        return None
    result = []
    for req in reqs:
        req = req.strip()
        if not req:
            continue
        if "==" in req:
            name, version = req.split("==", 1)
            result.append({"name": name.strip(), "version": version.strip()})
        else:
            result.append({"name": req})
    return result if result else None


async def register_tool_with_letta(
    *,
    name: str,
    description: str | None,
    source_code: str,
    json_schema: dict,
    tags: list[str] | None,
    pip_requirements: list[str] | None,
    raise_on_error: bool = True,
) -> Any:
    """Register a tool with the Letta service.

    Handles the common schema fix-ups needed by Letta's sandbox executor:
    - Adds ``title`` (PascalCase of *name*) if missing
    - Ensures ``properties`` and ``type`` defaults are present

    Returns the Letta tool object, or ``None`` when *raise_on_error* is
    ``False`` and the call fails.
    """
    args_schema = _prepare_letta_schema(json_schema, name)

    # Build the full tool schema (name + description + parameters) instead of
    # using args_json_schema. This bypasses Letta's get_function_name_and_docstring
    # which has a bug: it uses ast.walk and picks the last FunctionDef, not the
    # first public one. When a tool has helper functions, the wrong function gets
    # registered. Passing the full json_schema avoids source code parsing entirely.
    full_schema = _build_full_tool_schema(name, description, args_schema)

    client = get_letta_client()
    letta_tool = await call_letta(
        client.tools.create,
        source_code=source_code,
        source_type="python",
        json_schema=full_schema,
        tags=tags or [],
        pip_requirements=parse_pip_requirements(pip_requirements),
        raise_on_error=raise_on_error,
    )
    return letta_tool


async def update_tool_with_letta(
    *,
    letta_tool_id: str,
    name: str,
    source_code: str,
    json_schema: dict,
    tags: list[str] | None,
    pip_requirements: list[str] | None,
) -> Any:
    """Update an existing tool in the Letta service.

    Handles the same schema fix-ups as :func:`register_tool_with_letta`:
    - Adds ``title`` (PascalCase of *name*) if missing
    - Ensures ``properties`` and ``type`` defaults are present

    Returns the Letta tool object from the update response.
    """
    args_schema = _prepare_letta_schema(json_schema, name)
    full_schema = _build_full_tool_schema(name, None, args_schema)

    client = get_letta_client()
    letta_tool = await call_letta(
        client.tools.update,
        tool_id=letta_tool_id,
        source_code=source_code,
        source_type="python",
        json_schema=full_schema,
        tags=tags or [],
        pip_requirements=parse_pip_requirements(pip_requirements),
    )
    return letta_tool


async def register_and_store_tool(
    *,
    name: str,
    description: str | None,
    source_code: str,
    json_schema: dict,
    tags: list[str] | None,
    pip_requirements: list[str] | None,
    user_id: str,
    db: AsyncSession,
    source: str = "manual",
    status: str = TOOL_ACTIVE,
    letta_tool_id: str = "",  # empty for pending proposals
    raise_on_error: bool = True,
) -> Tool | None:
    """Sanitize name, check unique, register with Letta, store in DB.

    This is the full "create a tool" pipeline used by the manual create,
    GitHub import, and skill co-creation routes.

    Returns the persisted :class:`Tool` on success, or ``None`` when
    *raise_on_error* is ``False`` and the Letta registration fails.
    """
    safe_name = sanitize_string(name)
    safe_description = sanitize_string(description) if description else None

    await check_unique_for_user(db, Tool, user_id, "name", safe_name, error_label="Tool")

    letta_tool = await register_tool_with_letta(
        name=safe_name,
        description=safe_description,
        source_code=source_code,
        json_schema=json_schema,
        tags=tags,
        pip_requirements=pip_requirements,
        raise_on_error=raise_on_error,
    )

    if letta_tool is None:
        return None

    tool = Tool(
        user_id=user_id,
        name=safe_name,
        description=safe_description,
        letta_tool_id=letta_tool.id,
        source_code=source_code,
        json_schema=json.dumps(json_schema),
        tags=",".join(tags) if tags else None,
        pip_requirements=",".join(pip_requirements) if pip_requirements else None,
        source=source,
        status=status,
    )
    db.add(tool)
    await db.flush()

    return tool
