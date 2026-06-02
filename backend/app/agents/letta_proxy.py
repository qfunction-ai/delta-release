"""Proxy routes for Letta Local fork endpoints.

The Letta Local fork adds three API route groups that the letta-client
SDK doesn't cover yet. These routes proxy requests from Delta's frontend
to the Letta container, keeping the Letta container internal.

- Security audit log: GET /v1/security/events
- Agent files:        GET /v1/agents/{id}/files, GET /v1/agents/{id}/files/{path}
- Tool call policies: GET/PUT/PATCH/DELETE /v1/agents/{id}/policy, POST /v1/agents/{id}/policy/evaluate

Delta uses its own agent IDs (plain UUIDs) while the Letta server uses
prefixed IDs (agent-<uuid>). The proxy resolves Delta IDs to Letta IDs
before forwarding requests.
"""

import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.agents.models import Agent
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db, get_owned_or_404
from app.letta_client import LETTA_PROXY_TIMEOUT, letta_base_url

router = APIRouter(prefix="/api/agents", tags=["letta-proxy"])

logger = logging.getLogger(__name__)

# Allowed characters in proxied file paths: alphanumeric, dots, hyphens,
# underscores, and forward slashes. Rejects path traversal (..), null bytes,
# and any non-printable characters.
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")


def _validate_proxy_path(path: str) -> str:
    """Validate a file path before proxying to the Letta container.

    The Letta container runs as root, so we must prevent path traversal
    that could read arbitrary files (e.g., ../../etc/passwd).
    """
    if not path:
        raise HTTPException(status_code=400, detail="File path must not be empty")
    if ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if "\x00" in path:
        raise HTTPException(status_code=400, detail="Null bytes not allowed in path")
    if not _SAFE_PATH_RE.match(path):
        raise HTTPException(status_code=400, detail="File path contains invalid characters")
    return path


async def _resolve_agent(
    db,
    agent_id: str,
    current_user: User,
) -> Agent:
    """Look up a Delta agent and return it, verifying ownership.

    Returns the Agent ORM object so callers can access letta_agent_id.
    """
    return await get_owned_or_404(db, Agent, agent_id, current_user.id)


async def _proxy_request(
    method: str,
    path: str,
    agent: Agent,
    request: Request = None,
) -> Response:
    """Proxy a request to the Letta container.

    Ownership has already been verified by the caller. The path should
    use the Letta agent ID (agent.letta_agent_id), not the Delta ID.
    Returns the Letta response as-is (status code, headers, body).
    """
    base_url = letta_base_url()
    url = f"{base_url}{path}"

    headers = {}
    if request:
        ct = request.headers.get("content-type")
        if ct:
            headers["content-type"] = ct

    body = await request.body() if request else None

    async with httpx.AsyncClient(timeout=LETTA_PROXY_TIMEOUT) as client:
        try:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )
        except httpx.HTTPError as e:
            logger.error("Proxy request to Letta failed: %s %s -> %s", method, url, e)
            raise HTTPException(status_code=502, detail="Letta service unavailable")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


@router.get("/{agent_id}/files")
async def list_agent_files(
    agent_id: str,
    prefix: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """List files in an agent's workspace."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "GET",
        f"/v1/agents/{letta_id}/files" + (f"?prefix={prefix}" if prefix else ""),
        agent,
    )


@router.get("/{agent_id}/files/{path:path}")
async def get_agent_file(
    agent_id: str,
    path: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Download a file from an agent's workspace."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    safe_path = _validate_proxy_path(path)
    return await _proxy_request(
        "GET",
        f"/v1/agents/{letta_id}/files/{safe_path}",
        agent,
    )


@router.get("/{agent_id}/policy")
async def get_tool_call_policy(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get the tool call policy for an agent."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "GET",
        f"/v1/agents/{letta_id}/policy",
        agent,
    )


@router.put("/{agent_id}/policy")
async def update_tool_call_policy(
    agent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Update the tool call policy for an agent."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "PUT",
        f"/v1/agents/{letta_id}/policy",
        agent,
        request,
    )


@router.patch("/{agent_id}/policy")
async def patch_tool_call_policy(
    agent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Partially update the tool call policy for an agent."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "PATCH",
        f"/v1/agents/{letta_id}/policy",
        agent,
        request,
    )


@router.post("/{agent_id}/policy/evaluate")
async def evaluate_tool_call_policy(
    agent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Dry-run: evaluate a hypothetical tool call against the current policy."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "POST",
        f"/v1/agents/{letta_id}/policy/evaluate",
        agent,
        request,
    )


@router.delete("/{agent_id}/policy")
async def delete_tool_call_policy(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Delete the tool call policy for an agent (resets to allow all)."""
    agent = await _resolve_agent(db, agent_id, current_user)
    letta_id = agent.letta_agent_id
    return await _proxy_request(
        "DELETE",
        f"/v1/agents/{letta_id}/policy",
        agent,
    )
