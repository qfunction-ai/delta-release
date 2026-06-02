"""Observability proxy routes.

Proxies requests to the Letta fork's observability and run APIs.
All routes are admin-only. The Letta container stays internal —
the frontend never calls it directly.

The trace endpoint queries Jaeger directly (not the fork) because
the fork's trace retrieval requires ClickHouse, which isn't in the
dev stack. Jaeger already stores all OTel spans via the collector.
"""

import logging
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_admin_user
from app.auth.models import User
from app.letta_client import LETTA_PROXY_TIMEOUT, letta_base_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observability", tags=["observability"])

# Jaeger query API — accessible from the backend container as http://jaeger:16686
JAEGER_BASE_URL = os.getenv("JAEGER_BASE_URL", "http://jaeger:16686")

# OTel trace IDs are 16 or 32 hex chars (64-bit or 128-bit).
# Reject anything else to prevent path manipulation in the Jaeger URL.
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{16,32}$", re.IGNORECASE)

# Letta run/step IDs are prefixed UUIDs (e.g., "run-abc123..." or "step-def456...").
# Reject anything else to prevent path manipulation in proxied URLs.
_LETTA_ID_RE = re.compile(r"^[a-z]+-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


async def _proxy_get(path: str, params: dict | None = None) -> dict:
    """GET a JSON response from the Letta API. Returns parsed JSON or raises."""
    base_url = letta_base_url()
    url = f"{base_url}{path}"

    async with httpx.AsyncClient(timeout=LETTA_PROXY_TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as e:
            logger.error("Observability proxy failed: GET %s -> %s", url, e)
            raise HTTPException(status_code=502, detail="Letta service unavailable")

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Not found")
    if resp.status_code == 500:
        # The fork's duplicate /metrics endpoint can return 500 when
        # no metrics exist. Return empty data instead of propagating.
        logger.warning("Letta returned 500 for %s, returning empty", path)
        return {}
    if resp.status_code != 200:
        logger.error("Letta returned %d for GET %s: %s", resp.status_code, url, resp.text[:500])
        # Return a generic error instead of propagating the upstream status code
        # and body, which could leak internal details (stack traces, DB errors, etc.)
        raise HTTPException(status_code=502, detail="Upstream service error")

    return resp.json()


@router.get("/overview")
async def get_overview(
    since: Optional[str] = Query(None, description="ISO datetime"),
    until: Optional[str] = Query(None, description="ISO datetime"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    current_user: User = Depends(get_admin_user),
):
    """Aggregated observability stats from the fork."""
    params = {}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    if agent_id:
        params["agent_id"] = agent_id

    return await _proxy_get("/v1/observability/overview", params)


@router.get("/runs")
async def list_runs(
    agent_id: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None, description="Comma-separated statuses"),
    limit: int = Query(100, le=1000),
    before: Optional[str] = Query(None, description="Cursor: runs created before this"),
    after: Optional[str] = Query(None, description="Cursor: runs created after this"),
    order: str = Query("desc", description="asc or desc"),
    current_user: User = Depends(get_admin_user),
):
    """List runs from the Letta fork."""
    params = {"limit": limit, "order": order}
    if agent_id:
        params["agent_id"] = agent_id
    if statuses:
        params["statuses"] = statuses
    if before:
        params["before"] = before
    if after:
        params["after"] = after

    return await _proxy_get("/v1/runs/", params)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: User = Depends(get_admin_user),
):
    """Get a single run."""
    if not _LETTA_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    return await _proxy_get(f"/v1/runs/{run_id}")


@router.get("/runs/{run_id}/steps")
async def list_run_steps(
    run_id: str,
    limit: int = Query(100, le=1000),
    order: str = Query("desc"),
    current_user: User = Depends(get_admin_user),
):
    """List steps for a run."""
    if not _LETTA_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    return await _proxy_get(f"/v1/runs/{run_id}/steps", {"limit": limit, "order": order})


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(
    run_id: str,
    current_user: User = Depends(get_admin_user),
):
    """Get metrics for a run. Returns empty dict if no metrics exist."""
    if not _LETTA_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    return await _proxy_get(f"/v1/runs/{run_id}/metrics")


@router.get("/runs/{run_id}/usage")
async def get_run_usage(
    run_id: str,
    current_user: User = Depends(get_admin_user),
):
    """Get token usage for a run."""
    if not _LETTA_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    return await _proxy_get(f"/v1/runs/{run_id}/usage")


@router.get("/steps/{step_id}/metrics")
async def get_step_metrics(
    step_id: str,
    current_user: User = Depends(get_admin_user),
):
    """Get metrics for a step. Returns empty dict if no metrics exist."""
    if not _LETTA_ID_RE.match(step_id):
        raise HTTPException(status_code=400, detail="Invalid step ID format")
    return await _proxy_get(f"/v1/steps/{step_id}/metrics")


@router.get("/runs/{run_id}/trace")
async def get_run_trace(
    run_id: str,
    current_user: User = Depends(get_admin_user),
):
    """Get OTel trace spans for a run from Jaeger.

    The fork's trace endpoint requires ClickHouse, which isn't in the
    dev stack. This route queries Jaeger's API directly using the
    trace_id stored on the run's steps.
    """
    if not _LETTA_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run ID format")
    # 1. Get steps to find trace_id
    steps = await _proxy_get(f"/v1/runs/{run_id}/steps", {"limit": 25})
    if not isinstance(steps, list):
        steps = []

    trace_id = None
    for step in steps:
        tid = step.get("trace_id")
        if tid:
            trace_id = tid
            break

    if not trace_id or not _TRACE_ID_RE.match(trace_id):
        return {"trace_id": trace_id, "spans": []}

    # 2. Query Jaeger for the trace
    url = f"{JAEGER_BASE_URL}/api/traces/{trace_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            logger.error("Jaeger query failed: GET %s -> %s", url, e)
            raise HTTPException(status_code=502, detail="Jaeger service unavailable")

    if resp.status_code != 200:
        logger.error("Jaeger returned %d for trace %s", resp.status_code, trace_id)
        return {"trace_id": trace_id, "spans": []}

    jaeger_data = resp.json()
    traces = jaeger_data.get("data", [])
    if not traces:
        return {"trace_id": trace_id, "spans": []}

    # 3. Transform Jaeger spans to flat list for the frontend
    jaeger_trace = traces[0]
    jaeger_spans = jaeger_trace.get("spans", [])

    parent_ids = set()
    for s in jaeger_spans:
        for ref in s.get("references", []):
            if ref.get("refType") == "CHILD_OF":
                parent_ids.add(ref["spanID"])

    spans = []
    for s in jaeger_spans:
        tags = {}
        for t in s.get("tags", []):
            tags[t["key"]] = t["value"]

        # Find parent span ID
        parent_span_id = None
        for ref in s.get("references", []):
            if ref.get("refType") == "CHILD_OF":
                parent_span_id = ref["spanID"]
                break

        spans.append(
            {
                "span_id": s["spanID"],
                "parent_span_id": parent_span_id,
                "operation_name": s["operationName"],
                "start_time_us": s["startTime"],
                "duration_us": s["duration"],
                "tags": tags,
                "has_children": s["spanID"] in parent_ids,
            }
        )

    # Sort by start time
    spans.sort(key=lambda s: s["start_time_us"])

    return {"trace_id": trace_id, "spans": spans}


@router.get("/tool-calls")
async def list_tool_calls(
    agent_id: Optional[str] = Query(None),
    tool_name: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    since: Optional[str] = Query(None, description="ISO datetime"),
    until: Optional[str] = Query(None, description="ISO datetime"),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """List tool call records from the fork's observability store."""
    params = {"limit": limit}
    if agent_id:
        params["agent_id"] = agent_id
    if tool_name:
        params["tool_name"] = tool_name
    if success is not None:
        params["success"] = str(success).lower()
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    return await _proxy_get("/v1/observability/tool-calls", params)


@router.get("/security-events")
async def list_security_events(
    agent_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO datetime (defaults to 7 days ago if not provided)"),
    until: Optional[str] = Query(None, description="ISO datetime (upper bound)"),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """List security events from the audit log."""
    from datetime import datetime, timedelta, timezone

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    params = {"limit": limit, "since": since}
    if agent_id:
        params["agent_id"] = agent_id
    if event_type:
        params["event_type"] = event_type
    if until:
        params["until"] = until

    return await _proxy_get("/v1/security/events", params)
