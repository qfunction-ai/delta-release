"""Admin log viewer endpoint.

Reads log files from the shared /data/logs volume, the audit_logs table,
and the Letta security_events table (via the fork's API), parses them,
and returns structured entries with filtering.
"""

import csv
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.auth.dependencies import get_admin_user
from app.auth.models import User
from app.config import get_settings
from app.database import get_db
from app.letta_client import LETTA_PROXY_TIMEOUT, letta_base_url
from app.logs.parser import PARSERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])

LOG_DIR = "/data/logs"
LOG_FILES = {
    "backend": "backend.log",
    "letta": "letta.log",
    "postgres": "postgres.log",
    "pip-sidecar": "pip-sidecar.log",
}

VALID_SERVICES = list(LOG_FILES.keys()) + ["audit", "security"]
VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Security event types that map to ERROR level
_SECURITY_ERROR_TYPES = {"tool_denied", "policy_violation", "canary_detected"}
# Security event types that map to WARNING level
_SECURITY_WARNING_TYPES = {
    "tool_approval_requested",
    "tool_approval_denied",
    "memory_block_modified",
    "archival_memory_modified",
}
# Tool categories (in event_data.tool_category) that override the base level
_SECURITY_CATEGORY_WARNING = {"memory_write", "archival_write"}


def _read_log_file(service: str) -> list[str]:
    """Read lines from a log file, most recent first."""
    filename = LOG_FILES.get(service)
    if not filename:
        return []

    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        return []

    lines = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            # Read from the end for efficiency on large files
            # For simplicity, read all and reverse (files are <50MB with rotation)
            all_lines = f.readlines()
            lines = all_lines[-get_settings().max_lines_per_log_file :]
    except OSError:
        return []

    return lines


def _parse_file_entries(service: str, lines: list[str]) -> list[dict]:
    """Parse log lines into structured entries."""
    parser = PARSERS.get(service)
    if not parser:
        return []

    entries = []
    for line in lines:
        entry = parser(line)
        if entry:
            entry["service"] = service
            entries.append(entry)

    return entries


def _map_security_level(event_type: str, event_data: dict | None = None) -> str:
    """Map a security event_type to a log level.

    Tool categories in event_data.tool_category can override the base level:
    memory_write and archival_write tools are WARNING even if the base
    event_type (tool_executed) would be INFO.
    """
    if event_type in _SECURITY_ERROR_TYPES:
        return "ERROR"
    if event_type in _SECURITY_WARNING_TYPES:
        return "WARNING"
    # Category-based override for tool_executed events
    if event_data and isinstance(event_data, dict):
        category = event_data.get("tool_category")
        if category in _SECURITY_CATEGORY_WARNING:
            return "WARNING"
    return "INFO"


def _build_security_message(event: dict) -> str:
    """Build a human-readable message from a security event."""
    event_type = event.get("event_type", "unknown")
    event_data = event.get("event_data") or {}
    agent_id = event.get("agent_id", "")

    # Friendly event type labels
    labels = {
        "tool_executed": "Tool executed",
        "tool_denied": "Tool denied",
        "tool_approval_requested": "Approval requested",
        "tool_approval_granted": "Approval granted",
        "tool_approval_denied": "Approval denied",
        "policy_violation": "Policy violation",
        "canary_detected": "Canary detected",
        "memory_block_modified": "Memory block modified",
        "archival_memory_modified": "Archival memory modified",
        "memory_read": "Memory read",
        "archival_memory_read": "Archival memory read",
        "conversation_read": "Conversation read",
        "web_search": "Web search",
        "web_fetch": "Web fetch",
        "message_sent": "Message sent",
    }
    label = labels.get(event_type, event_type)

    parts = [label]

    # Add tool name if present in event_data
    tool_name = event_data.get("tool_name") or event_data.get("tool")
    if tool_name:
        parts.append(f"tool: {tool_name}")

    # Add tool category if present
    tool_category = event_data.get("tool_category")
    if tool_category:
        parts.append(f"category: {tool_category}")

    # Add tool_call_id reference if present
    tool_call_id = event_data.get("tool_call_id")
    if tool_call_id:
        parts.append(f"call: {tool_call_id[:12]}")

    # Add agent short ID
    if agent_id:
        parts.append(f"agent: {agent_id[:16]}")

    # Add block label for memory events
    block_label = event_data.get("block_label")
    if block_label:
        parts.append(f"block: {block_label}")

    return " — ".join(parts)


async def _get_security_entries(
    hours: int,
    level: str | None = None,
    search: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Fetch security events from the Letta fork's audit log.

    Calls the Letta container's /v1/security/events endpoint directly.
    Returns entries mapped to the standard log entry shape.
    If the Letta container is down, returns an empty list (never breaks
    the rest of the logs viewer).
    """
    base_url = letta_base_url()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    params = {"limit": min(limit, 1000), "since": since}

    async with httpx.AsyncClient(timeout=LETTA_PROXY_TIMEOUT) as client:
        try:
            resp = await client.get(
                f"{base_url}/v1/security/events",
                params=params,
            )
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch security events: %s", e)
            return []

    if resp.status_code != 200:
        logger.warning("Security events endpoint returned %d", resp.status_code)
        return []

    try:
        data = resp.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning("Security events response not valid JSON")
        return []

    events = data.get("events", [])
    entries = []

    for event in events:
        event_type = event.get("event_type", "")
        event_data = event.get("event_data") or {}
        entry_level = _map_security_level(event_type, event_data)

        # Apply level filter
        if level and entry_level != level:
            continue

        message = _build_security_message(event)

        # Apply search filter
        if search:
            search_lower = search.lower()
            if search_lower not in message.lower() and search_lower not in event_type.lower():
                continue

        entries.append(
            {
                "timestamp": event.get("created_at"),
                "service": "security",
                "level": entry_level,
                "module": event_type,
                "message": message,
            }
        )

    return entries


async def _get_audit_entries(
    db: AsyncSession,
    hours: int,
    level: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Query audit logs from the database."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    base = select(AuditLog).where(AuditLog.created_at >= cutoff)

    # Audit logs don't have a level field — map status codes
    # 2xx = INFO, 4xx = WARNING, 5xx = ERROR
    if level == "ERROR":
        base = base.where(AuditLog.status_code >= 500)
    elif level == "WARNING":
        base = base.where((AuditLog.status_code >= 400) & (AuditLog.status_code < 500))
    elif level in ("DEBUG", "INFO", "CRITICAL"):
        # INFO matches 2xx; DEBUG/CRITICAL have no audit equivalent, skip
        if level == "INFO":
            base = base.where((AuditLog.status_code >= 200) & (AuditLog.status_code < 300))
        else:
            return [], 0

    # Text search in details and action
    if search:
        search_term = f"%{search}%"
        base = base.where(
            AuditLog.details.ilike(search_term)
            | AuditLog.action.ilike(search_term)
            | AuditLog.resource_type.ilike(search_term)
        )

    # Count total
    count_query = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = base.order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()

    entries = []
    for log in logs:
        # Map status code to level
        code = log.status_code or 200
        if code >= 500:
            log_level = "ERROR"
        elif code >= 400:
            log_level = "WARNING"
        else:
            log_level = "INFO"

        message = f"{log.action}"
        if log.resource_type:
            message += f" {log.resource_type}"
        if log.resource_id:
            message += f"/{log.resource_id[:8]}"
        if log.details:
            try:
                details = json.loads(log.details)
                method = details.get("method", "")
                path = details.get("path", "")
                duration = details.get("duration_ms", "")
                if method and path:
                    message += f" — {method} {path}"
                if duration:
                    message += f" ({duration}ms)"
            except (json.JSONDecodeError, TypeError):
                message += f" — {log.details[:100]}"

        entries.append(
            {
                "timestamp": log.created_at.isoformat() if log.created_at else None,
                "service": "audit",
                "level": log_level,
                "module": "audit",
                "message": message,
            }
        )

    return entries, total


@router.get("/")
async def get_logs(
    service: str | None = Query(None, description="Filter by service"),
    level: str | None = Query(None, description="Filter by level"),
    search: str | None = Query(None, description="Text search in messages"),
    limit: int = Query(100, le=500, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    hours: int = Query(24, le=168, description="Lookback window in hours"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get log entries from all services. Admin-only."""
    if service and service not in VALID_SERVICES:
        raise HTTPException(status_code=400, detail=f"Invalid service. Valid: {', '.join(VALID_SERVICES)}")
    if level and level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid level. Valid: {', '.join(VALID_LEVELS)}")

    all_entries = []

    # Audit logs from DB
    if not service or service == "audit":
        audit_entries, _ = await _get_audit_entries(
            db, hours=hours, level=level, search=search, limit=limit, offset=offset
        )
        all_entries.extend(audit_entries)

    # Security events from Letta fork
    if not service or service == "security":
        security_entries = await _get_security_entries(
            hours=hours,
            level=level,
            search=search,
            limit=limit,
        )
        all_entries.extend(security_entries)

    # File-based logs (skip if only audit or security is requested)
    if service not in ("audit", "security"):
        services_to_read = [service] if service and service in LOG_FILES else list(LOG_FILES.keys())
        for svc in services_to_read:
            lines = _read_log_file(svc)
            entries = _parse_file_entries(svc, lines)

            # Apply level filter
            if level:
                entries = [e for e in entries if e["level"] == level]

            # Apply search filter
            if search:
                search_lower = search.lower()
                entries = [e for e in entries if search_lower in e.get("message", "").lower()]

            # Apply time filter
            if hours and entries:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                filtered = []
                for e in entries:
                    ts = e.get("timestamp")
                    if ts:
                        try:
                            entry_time = datetime.fromisoformat(ts)
                            if entry_time >= cutoff:
                                filtered.append(e)
                        except (ValueError, TypeError):
                            # Keep entries without parseable timestamps
                            filtered.append(e)
                    else:
                        # No timestamp — keep it (might be from current session)
                        filtered.append(e)
                entries = filtered

            all_entries.extend(entries)

    # Sort by timestamp descending (newest first)
    def sort_key(e):
        ts = e.get("timestamp") or ""
        return ts

    all_entries.sort(key=sort_key, reverse=True)

    # Apply pagination
    total = len(all_entries)
    paginated = all_entries[offset : offset + limit]

    return {
        "entries": paginated,
        "total": total,
        "services": VALID_SERVICES,
    }


@router.get("/export")
async def export_logs(
    service: str | None = Query(None, description="Filter by service"),
    level: str | None = Query(None, description="Filter by level"),
    search: str | None = Query(None, description="Text search in messages"),
    hours: int = Query(24, le=168, description="Lookback window in hours"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all matching log entries as CSV. Admin-only."""
    if service and service not in VALID_SERVICES:
        raise HTTPException(status_code=400, detail=f"Invalid service. Valid: {', '.join(VALID_SERVICES)}")
    if level and level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid level. Valid: {', '.join(VALID_LEVELS)}")

    all_entries = []

    # Audit logs from DB
    if not service or service == "audit":
        audit_entries, _ = await _get_audit_entries(
            db,
            hours=hours,
            level=level,
            search=search,
            limit=10000,
            offset=0,
        )
        all_entries.extend(audit_entries)

    # Security events from Letta fork
    if not service or service == "security":
        security_entries = await _get_security_entries(
            hours=hours,
            level=level,
            search=search,
            limit=10000,
        )
        all_entries.extend(security_entries)

    # File-based logs
    if service not in ("audit", "security"):
        services_to_read = [service] if service and service in LOG_FILES else list(LOG_FILES.keys())
        for svc in services_to_read:
            lines = _read_log_file(svc)
            entries = _parse_file_entries(svc, lines)

            if level:
                entries = [e for e in entries if e["level"] == level]

            if search:
                search_lower = search.lower()
                entries = [e for e in entries if search_lower in e.get("message", "").lower()]

            if hours and entries:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                filtered = []
                for e in entries:
                    ts = e.get("timestamp")
                    if ts:
                        try:
                            entry_time = datetime.fromisoformat(ts)
                            if entry_time >= cutoff:
                                filtered.append(e)
                        except (ValueError, TypeError):
                            filtered.append(e)
                    else:
                        filtered.append(e)
                entries = filtered

            all_entries.extend(entries)

    # Sort by timestamp descending
    all_entries.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "service", "level", "module", "message"])

    for entry in all_entries:
        writer.writerow(
            [
                entry.get("timestamp") or "",
                entry.get("service") or "",
                entry.get("level") or "",
                entry.get("module") or "",
                entry.get("message") or "",
            ]
        )

    output.seek(0)
    filename = f"delta_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
