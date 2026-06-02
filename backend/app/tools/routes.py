import ast
import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
from letta_client import APIError as LettaAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.async_utils import run_sync
from app.auth.dependencies import get_admin_user, get_current_user, resolve_agent_user, verify_service_token
from app.auth.models import User
from app.constants import TOOL_ACTIVE, TOOL_PENDING
from app.database import check_unique_for_user, get_db, get_owned_or_404
from app.errors import sanitize_error_detail
from app.github import build_github_headers, parse_github_url
from app.letta_client import get_letta_client
from app.rate_limit import limiter
from app.sanitize import sanitize_python_code, sanitize_string, validate_tool_source_code

# Re-export from extracted modules for backward compatibility
from app.tools.github import fetch_github_tool
from app.tools.helpers import (
    register_and_store_tool,
    register_tool_with_letta,
    update_tool_with_letta,
)
from app.tools.models import Tool
from app.tools.packages import sidecar_request as _sidecar_request
from app.tools.schemas import (
    AgentToolProposeRequest,
    PackageInstallRequest,
    PackageResponse,
    SchemaGenerateRequest,
    ToolCreate,
    ToolDetailResponse,
    ToolGithubCreate,
    ToolProposalResponse,
    ToolProposeRequest,
    ToolResponse,
    ToolUpdate,
)

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Python type annotations -> JSON Schema type mapping
TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
    "List": "array",
    "Dict": "object",
}


def generate_schema_from_source(source_code: str) -> dict:
    """Parse Python source code and generate a JSON schema from the first function definition."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        raise ValueError(f"Invalid Python syntax: {e}")

    # Find the first function definition at the top level only.
    # ast.walk would recurse into nested classes/functions, which is wrong
    # — we want the first top-level def, or a method inside a top-level class.
    func_def = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            func_def = node
            break
        if isinstance(node, ast.ClassDef):
            # Look for the first method inside the class
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_def = child
                    break
            if func_def:
                break

    if not func_def:
        raise ValueError("No function definition found in source code")

    description = ""
    if (
        func_def.body
        and isinstance(func_def.body[0], ast.Expr)
        and isinstance(func_def.body[0].value, ast.Constant)
        and isinstance(func_def.body[0].value.value, str)
    ):
        docstring = func_def.body[0].value.value
        # Use first line of docstring as description
        description = docstring.strip().split("\n")[0].strip()

    properties = {}
    required = []

    # Get defaults (they align to the end of args)
    args = func_def.args
    defaults = args.defaults
    num_defaults = len(defaults)

    # Skip 'self' if present
    arg_list = [a for a in args.args if a.arg != "self"]

    for i, arg in enumerate(arg_list):
        arg_name = arg.arg
        arg_description = ""

        # Try to extract arg description from docstring Args section
        if description:
            docstring = func_def.body[0].value.value
            for line in docstring.split("\n"):
                stripped = line.strip()
                if stripped.startswith(f"{arg_name}:") or stripped.startswith(f"{arg_name} :"):
                    arg_description = stripped.split(":", 1)[1].strip() if ":" in stripped[4:] else ""
                    break

        # Determine type from annotation
        arg_type = "string"  # default
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                arg_type = TYPE_MAP.get(arg.annotation.id, "string")
            elif isinstance(arg.annotation, ast.Constant):
                # Literal type hint
                arg_type = "string"
            elif isinstance(arg.annotation, ast.Subscript):
                # e.g. List[str], Dict[str, Any]
                if isinstance(arg.annotation.value, ast.Name):
                    arg_type = TYPE_MAP.get(arg.annotation.value.id, "string")

        # Determine if required or has default
        # Defaults align to the end of the positional args.
        # For args = [a, b, c] with defaults = [5], that means c=5, a and b are required.
        default_offset = len(arg_list) - num_defaults
        has_default = i >= default_offset

        prop = {"type": arg_type, "description": arg_description or f"{arg_name} parameter"}

        # Add default value if present
        if has_default:
            default_idx = i - default_offset
            default_node = defaults[default_idx]
            if isinstance(default_node, ast.Constant):
                prop["default"] = default_node.value
            elif isinstance(default_node, ast.Name) and default_node.id == "None":
                prop["default"] = None
        else:
            required.append(arg_name)

        properties[arg_name] = prop

    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return schema


@router.post("/generate-schema")
async def generate_schema(
    req: SchemaGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate a JSON schema from Python source code."""
    try:
        schema = generate_schema_from_source(req.source_code)
        return schema
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=sanitize_error_detail(str(e)))


@router.get("/", response_model=list[ToolResponse])
async def list_tools(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's active tools (excludes pending proposals)."""
    result = await db.execute(select(Tool).where(Tool.user_id == current_user.id, Tool.status == TOOL_ACTIVE))
    tools = result.scalars().all()
    return [ToolResponse.from_orm_with_tags(t) for t in tools]


@router.post("/", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def create_tool(
    tool_data: ToolCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tool. Source code is stored in Letta."""
    # Sanitize and validate source code
    sanitized_code = validate_tool_source_code(tool_data.source_code)

    tool = await register_and_store_tool(
        name=tool_data.name,
        description=tool_data.description,
        source_code=sanitized_code,
        json_schema=tool_data.json_schema,
        tags=tool_data.tags,
        pip_requirements=tool_data.pip_requirements,
        user_id=str(current_user.id),
        db=db,
    )

    return ToolResponse.from_orm_with_tags(tool)


@router.post("/github", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_tool_from_github(
    request: Request,
    tool_data: ToolGithubCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a tool from a GitHub URL pointing to a directory with tool.yaml."""
    owner, repo, branch, sub_path = parse_github_url(tool_data.github_url)

    gh_headers = build_github_headers()

    name, description, source_code, json_schema, tags, pip_requirements, _has_skill = await fetch_github_tool(
        owner, repo, branch, sub_path, gh_headers
    )

    tool = await register_and_store_tool(
        name=name,
        description=description,
        source_code=source_code,
        json_schema=json_schema,
        tags=tags,
        pip_requirements=pip_requirements,
        user_id=str(current_user.id),
        db=db,
        source="github",
    )

    return ToolResponse.from_orm_with_tags(tool)


from app.tools.proposals import execute_dry_run


async def _create_proposal(
    user_id: str,
    proposal: ToolProposeRequest,  # Also accepts AgentToolProposeRequest (same shape)
    db: AsyncSession,
) -> ToolProposalResponse:
    """Shared logic for creating a tool proposal.

    Used by both the user-facing propose endpoint and the
    service-to-service agent propose endpoint.
    """
    from app.settings.service import get_or_create_settings

    settings = await get_or_create_settings(str(user_id), db)
    if not settings.agent_tool_creation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent tool creation is disabled. Enable it in Settings to allow agents to propose tools.",
        )

    # Sanitize source code
    validate_tool_source_code(proposal.source_code)

    safe_name = sanitize_string(proposal.name)
    safe_description = sanitize_string(proposal.description)

    await check_unique_for_user(db, Tool, user_id, "name", safe_name, error_label="Tool")

    dry_run_output, dry_run_error = await execute_dry_run(
        proposal.source_code,
        proposal.name,
        proposal.json_schema,
        proposal.pip_requirements,
    )

    # Store as pending tool — NOT registered with Letta
    tool = Tool(
        user_id=user_id,
        name=safe_name,
        description=safe_description,
        letta_tool_id="",  # Empty until approved
        source_code=proposal.source_code,
        json_schema=json.dumps(proposal.json_schema),
        tags=None,
        pip_requirements=",".join(proposal.pip_requirements)
        if proposal.pip_requirements and proposal.pip_requirements != ["None"]
        else None,
        source="agent",
        status=TOOL_PENDING,
        proposed_by="agent",
        dry_run_output=dry_run_output,
        dry_run_error=dry_run_error,
    )
    db.add(tool)
    await db.flush()

    return ToolProposalResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        source_code=tool.source_code,
        json_schema=json.loads(tool.json_schema),
        tags=None,
        pip_requirements=proposal.pip_requirements,
        proposed_by="agent",
        dry_run_output=dry_run_output,
        dry_run_error=dry_run_error,
        created_at=tool.created_at,
    )


@router.post("/propose", response_model=ToolProposalResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def propose_tool(
    request: Request,
    proposal: ToolProposeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propose a new tool from an agent. Requires agent_tool_creation setting enabled."""
    return await _create_proposal(current_user.id, proposal, db)


@router.post("/propose/agent", response_model=ToolProposalResponse, status_code=status.HTTP_201_CREATED)
async def propose_tool_from_agent(
    request: Request,
    proposal: AgentToolProposeRequest,
    _auth=Depends(verify_service_token),
    db: AsyncSession = Depends(get_db),
):
    """Service-to-service propose endpoint called by the propose_tool from the Letta sandbox.

    Authenticates via X-Service-Token (not user JWT) and resolves the user
    from the agent_id.
    """
    agent = await resolve_agent_user(request, proposal.agent_id, db)
    return await _create_proposal(agent.user_id, proposal, db)


@router.get("/proposals", response_model=list[ToolProposalResponse])
async def list_proposals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending tool proposals."""
    result = await db.execute(
        select(Tool).where(
            Tool.user_id == current_user.id,
            Tool.status == TOOL_PENDING,
        )
    )
    proposals = result.scalars().all()
    return [
        ToolProposalResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            source_code=p.source_code,
            json_schema=json.loads(p.json_schema),
            tags=p.tag_list,
            pip_requirements=p.pip_requirements_list,
            proposed_by=p.proposed_by or "agent",
            dry_run_output=p.dry_run_output,
            dry_run_error=p.dry_run_error,
            created_at=p.created_at,
        )
        for p in proposals
    ]


@router.post("/proposals/{proposal_id}/approve", response_model=ToolResponse)
async def approve_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending tool proposal. Registers it with Letta and activates it."""
    tool = await get_owned_or_404(db, Tool, proposal_id, current_user.id)

    if tool.status != TOOL_PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tool is not in pending state (current: {tool.status})"
        )

    # Re-sanitize (defense-in-depth)
    _, warnings = sanitize_python_code(tool.source_code)
    if warnings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool source code contains dangerous patterns: {'; '.join(warnings)}. Reject this proposal.",
        )

    # Register with Letta
    json_schema = json.loads(tool.json_schema)
    letta_tool = await register_tool_with_letta(
        name=tool.name,
        description=tool.description,
        source_code=tool.source_code,
        json_schema=json_schema,
        tags=tool.tag_list,
        pip_requirements=tool.pip_requirements_list,
    )

    # Activate the tool
    tool.letta_tool_id = letta_tool.id
    tool.status = TOOL_ACTIVE
    await db.flush()

    return ToolResponse.from_orm_with_tags(tool)


@router.post("/proposals/{proposal_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_proposal(
    proposal_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending tool proposal. Deletes it from the database."""
    tool = await get_owned_or_404(db, Tool, proposal_id, current_user.id)

    if tool.status != TOOL_PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Tool is not in pending state (current: {tool.status})"
        )

    await db.delete(tool)


def _sidecar_error_detail(response) -> str:
    """Extract user-actionable error detail from sidecar response.

    For 400 errors, the sidecar returns validation/install errors the user
    can act on (e.g., "package not found"). For other errors, return a
    generic message.
    """
    if response.status_code == 400:
        try:
            data = response.json()
            if isinstance(data, dict) and "detail" in data:
                return sanitize_error_detail(data["detail"], max_length=300)
        except Exception as e:
            logger.debug("Failed to parse sidecar error response: %s", e)
    return "Package management service error. Please try again later."


@router.get("/packages", response_model=list[PackageResponse])
async def list_packages(
    current_user: User = Depends(get_current_user),
):
    """List Python packages installed in the shared package directory."""
    response = await _sidecar_request("GET", "/packages")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=_sidecar_error_detail(response))
    packages = response.json()
    return [PackageResponse(name=p["name"], version=p["version"]) for p in packages]


@router.post("/packages/install", response_model=list[PackageResponse])
async def install_packages(
    req: PackageInstallRequest,
    current_user: User = Depends(get_admin_user),
):
    """Install Python packages into the shared package directory. Admin only."""
    response = await _sidecar_request("POST", "/packages/install", json={"packages": req.packages})
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=_sidecar_error_detail(response))
    return [PackageResponse(name=p["name"], version=p["version"]) for p in response.json()]


_PKG_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.\-]*$")


@router.delete("/packages/{package_name}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_package(
    package_name: str,
    current_user: User = Depends(get_admin_user),
):
    """Uninstall a Python package from the shared package directory. Admin only."""
    if not _PKG_NAME_RE.match(package_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid package name format",
        )
    response = await _sidecar_request("DELETE", f"/packages/{package_name}")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Package {package_name} not found")
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=_sidecar_error_detail(response))


@router.get("/{tool_id}", response_model=ToolDetailResponse)
async def get_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tool details including source code."""
    tool = await get_owned_or_404(db, Tool, tool_id, current_user.id)

    return ToolDetailResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        source=tool.source,
        source_code=tool.source_code,
        json_schema=json.loads(tool.json_schema),
        tags=tool.tag_list,
        pip_requirements=tool.pip_requirements_list,
    )


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a tool. Changes are synced to Letta."""
    tool = await get_owned_or_404(db, Tool, tool_id, current_user.id)

    if tool_data.name is not None and tool_data.name != tool.name:
        safe_name = sanitize_string(tool_data.name)
        await check_unique_for_user(
            db, Tool, current_user.id, "name", safe_name, exclude_id=tool_id, error_label="Tool"
        )
        tool.name = safe_name

    if tool_data.description is not None:
        tool.description = sanitize_string(tool_data.description)

    # Update source code or schema (requires Letta update)
    if tool_data.source_code is not None or tool_data.json_schema is not None or tool_data.pip_requirements is not None:
        new_source = tool_data.source_code or tool.source_code

        # Sanitize source code on update too
        if tool_data.source_code is not None:
            validate_tool_source_code(tool_data.source_code)
        new_schema = tool_data.json_schema or json.loads(tool.json_schema)
        new_pip_reqs = (
            tool_data.pip_requirements if tool_data.pip_requirements is not None else tool.pip_requirements_list
        )

        await update_tool_with_letta(
            letta_tool_id=tool.letta_tool_id,
            name=tool.name,
            source_code=new_source,
            json_schema=new_schema,
            tags=tool.tag_list,
            pip_requirements=new_pip_reqs,
        )
        tool.source_code = new_source
        tool.json_schema = json.dumps(new_schema)
        tool.pip_requirements = ",".join(new_pip_reqs) if new_pip_reqs else None

    if tool_data.tags is not None:
        tool.tags = ",".join(tool_data.tags) if tool_data.tags else None

    await db.flush()
    return ToolResponse.from_orm_with_tags(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tool from Letta and database."""
    tool = await get_owned_or_404(db, Tool, tool_id, current_user.id)

    client = get_letta_client()
    try:
        await run_sync(client.tools.delete, tool.letta_tool_id)
    except (httpx.HTTPError, LettaAPIError) as e:
        logger.warning("Letta tool deletion failed (proceeding with local cleanup): %s", e)

    await db.delete(tool)
