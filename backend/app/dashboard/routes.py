"""Dashboard API — aggregated data for the main dashboard view.

Returns agents with metadata, resource counts, recent workflow runs,
and service health status in a single call.
"""

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_settings
from app.constants import DEFAULT_PIPSIDECAR_URL, HEALTH_CHECK_TIMEOUT, OLLAMA_DISCOVERY_URLS
from app.credentials.models import Credential
from app.database import get_db
from app.skills.models import Skill
from app.tools.models import Tool
from app.workflows.models import Workflow, WorkflowRun

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class HealthStatus(BaseModel):
    backend: str
    letta: str
    postgres: str
    pip_sidecar: str
    ollama: str


class AgentMetadata(BaseModel):
    id: str
    name: str
    model: str
    embedding: str
    created_at: str
    workflows_count: int
    has_schedule: bool
    last_activity: str


class RecentRun(BaseModel):
    id: str
    workflow_name: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None


class DashboardResponse(BaseModel):
    agents: list[AgentMetadata]
    stats: dict[str, int]
    recent_runs: list[RecentRun]
    health: HealthStatus


async def _check_health(url: str, timeout: float = HEALTH_CHECK_TIMEOUT) -> str:
    """Ping a health endpoint and return 'healthy' or 'unreachable'."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            return "healthy" if resp.status_code == 200 else "degraded"
    except (httpx.ConnectError, httpx.TimeoutException):
        return "unreachable"


def _dt_to_str(value) -> str:
    """Convert a datetime to ISO string, or return as-is if already a string."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else ""


@router.get("/", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all dashboard data in a single call."""
    user_id = current_user.id

    async def _count(model) -> int:
        result = await db.execute(select(func.count()).select_from(model).where(model.user_id == user_id))
        return result.scalar() or 0

    stats = {
        "agents": await _count(Agent),
        "tools": await _count(Tool),
        "skills": await _count(Skill),
        "workflows": await _count(Workflow),
        "credentials": await _count(Credential),
    }

    agents_result = await db.execute(select(Agent).where(Agent.user_id == user_id).order_by(Agent.created_at.desc()))
    agents = agents_result.scalars().all()

    # Pre-aggregate workflow metadata for all agents in a single query
    agent_ids = [a.letta_agent_id for a in agents]
    agent_meta = {}
    if agent_ids:
        agg_result = await db.execute(
            select(
                Workflow.agent_id,
                func.count(Workflow.id).label("workflows_count"),
                func.count(Workflow.schedule_cron).label("scheduled_count"),
            )
            .where(
                Workflow.user_id == user_id,
                Workflow.agent_id.in_(agent_ids),
            )
            .group_by(Workflow.agent_id)
        )
        for row in agg_result.all():
            agent_meta[row.agent_id] = {
                "workflows_count": row.workflows_count,
                "has_schedule": row.scheduled_count > 0,
            }

    # Pre-aggregate last activity per agent
    last_activity_map = {}
    if agent_ids:
        # Subquery: latest run per workflow
        latest_run_subq = (
            select(
                WorkflowRun.workflow_id,
                func.max(WorkflowRun.created_at).label("last_run_at"),
            )
            .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
            .where(Workflow.user_id == user_id, Workflow.agent_id.in_(agent_ids))
            .group_by(WorkflowRun.workflow_id)
            .subquery()
        )
        # Join back to get agent_id
        activity_result = await db.execute(
            select(
                Workflow.agent_id,
                func.max(latest_run_subq.c.last_run_at).label("last_activity"),
            )
            .join(latest_run_subq, Workflow.id == latest_run_subq.c.workflow_id)
            .where(Workflow.user_id == user_id, Workflow.agent_id.in_(agent_ids))
            .group_by(Workflow.agent_id)
        )
        for row in activity_result.all():
            last_activity_map[row.agent_id] = row.last_activity

    agent_list = []
    for agent in agents:
        meta = agent_meta.get(agent.letta_agent_id, {"workflows_count": 0, "has_schedule": False})
        last_activity = last_activity_map.get(agent.letta_agent_id)
        if not last_activity:
            last_activity = agent.created_at

        agent_list.append(
            AgentMetadata(
                id=str(agent.id),
                name=agent.name,
                model=agent.model,
                embedding=agent.embedding,
                created_at=_dt_to_str(agent.created_at),
                workflows_count=meta["workflows_count"],
                has_schedule=meta["has_schedule"],
                last_activity=_dt_to_str(last_activity),
            )
        )

    recent_runs_result = await db.execute(
        select(WorkflowRun, Workflow.name.label("workflow_name"))
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .where(Workflow.user_id == user_id)
        .order_by(desc(WorkflowRun.created_at))
        .limit(10)
    )
    recent_rows = recent_runs_result.all()

    recent_runs = []
    for run, workflow_name in recent_rows:
        duration_ms = None
        if run.started_at and run.completed_at:
            delta = run.completed_at - run.started_at
            duration_ms = int(delta.total_seconds() * 1000)

        recent_runs.append(
            RecentRun(
                id=str(run.id),
                workflow_name=workflow_name,
                status=run.status,
                started_at=run.started_at.isoformat()
                if run.started_at and isinstance(run.started_at, datetime)
                else None,
                completed_at=run.completed_at.isoformat()
                if run.completed_at and isinstance(run.completed_at, datetime)
                else None,
                duration_ms=duration_ms,
            )
        )

    settings = get_settings()
    letta_base = settings.letta_base_url
    health = HealthStatus(
        backend="healthy",
        letta=await _check_health(f"{letta_base}/v1/health/"),
        postgres="healthy",  # if we got here, postgres is working
        pip_sidecar=await _check_health(f"{DEFAULT_PIPSIDECAR_URL}/health"),
        ollama=await _check_health(OLLAMA_DISCOVERY_URLS[0]),
    )

    return DashboardResponse(
        agents=agent_list,
        stats=stats,
        recent_runs=recent_runs,
        health=health,
    )
