import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


def _base_query(current_user: User):
    """Return a base query scoped to the current user's actions."""
    return select(AuditLog).where(AuditLog.user_id == current_user.id)


@router.get("/")
async def list_audit_logs(
    limit: int = Query(50, le=200),
    offset: int = 0,
    action: str | None = None,
    resource_type: str | None = None,
    days: int | None = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List audit logs for the current user with filtering."""
    query = _base_query(current_user).order_by(desc(AuditLog.created_at))

    # Apply filters
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(AuditLog.created_at >= cutoff)

    # Apply pagination
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "status_code": log.status_code,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/export")
async def export_audit_logs(
    days: int = Query(30, le=90),
    action: str | None = None,
    resource_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export current user's audit logs as CSV."""
    query = _base_query(current_user).order_by(desc(AuditLog.created_at))

    # Apply filters
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = query.where(AuditLog.created_at >= cutoff)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)

    result = await db.execute(query)
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "details",
            "ip_address",
            "status_code",
            "created_at",
        ]
    )

    for log in logs:
        writer.writerow(
            [
                str(log.id),
                str(log.user_id) if log.user_id else "",
                log.action,
                log.resource_type or "",
                log.resource_id or "",
                log.details or "",
                log.ip_address or "",
                log.status_code or "",
                log.created_at.isoformat(),
            ]
        )

    output.seek(0)
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/stats")
async def audit_stats(
    days: int = Query(7, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get audit statistics for the current user."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total actions
    total_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.user_id == current_user.id,
            AuditLog.created_at >= cutoff,
        )
    )
    total = total_result.scalar()

    # Actions by type
    actions_result = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("count"))
        .where(AuditLog.user_id == current_user.id, AuditLog.created_at >= cutoff)
        .group_by(AuditLog.action)
        .order_by(desc("count"))
    )
    by_action = [{"action": row[0], "count": row[1]} for row in actions_result.fetchall()]

    # Actions by resource
    resource_result = await db.execute(
        select(AuditLog.resource_type, func.count(AuditLog.id).label("count"))
        .where(AuditLog.user_id == current_user.id, AuditLog.created_at >= cutoff)
        .where(AuditLog.resource_type.isnot(None))
        .group_by(AuditLog.resource_type)
        .order_by(desc("count"))
    )
    by_resource = [{"resource": row[0], "count": row[1]} for row in resource_result.fetchall()]

    # Failed actions (4xx, 5xx)
    failed_result = await db.execute(
        select(func.count(AuditLog.id))
        .where(AuditLog.user_id == current_user.id, AuditLog.created_at >= cutoff)
        .where((AuditLog.status_code >= 400) & (AuditLog.status_code < 600))
    )
    failed = failed_result.scalar()

    return {
        "total_actions": total,
        "by_action": by_action,
        "by_resource": by_resource,
        "failed_actions": failed,
        "period_days": days,
    }
