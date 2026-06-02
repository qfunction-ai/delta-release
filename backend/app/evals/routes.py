"""Eval routes — agent evaluation via giskard-checks."""

import errno
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_settings
from app.constants import EVAL_CONTAINER_TIMEOUT
from app.database import check_unique_for_user, get_db, get_owned_or_404, list_owned
from app.errors import safe_error
from app.evals.models import EvalRun, EvalScenario
from app.evals.schemas import (
    EvalRunFromFile,
    EvalRunListResponse,
    EvalRunResponse,
    EvalScenarioCreate,
    EvalScenarioListResponse,
    EvalScenarioResponse,
    EvalScenarioUpdate,
    ScenarioDefinition,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evals", tags=["evals"])


async def _call_eval_container(
    scenario_name: str,
    agent_id: str,
    definition: ScenarioDefinition,
) -> dict:
    """Call the eval container to execute a scenario.

    Returns the parsed JSON response from the eval container.
    Raises HTTPException on communication failure.
    """
    settings = get_settings()
    eval_url = settings.eval_url

    payload = {
        "scenario_name": scenario_name,
        "agent_id": agent_id,
        "letta_url": settings.letta_base_url,
        "interactions": [i.model_dump() for i in definition.interactions],
        "checks": [c.model_dump() for c in definition.checks],
        "route_through_backend": definition.route_through_backend,
        "settings": definition.settings,
    }

    # When the scenario requires backend routing, pass the backend URL
    # so the eval container can call the service-to-service chat endpoint
    # instead of going directly to Letta. The service token is already
    # available to the eval container via DELTA_SERVICE_TOKEN env var
    # or the shared volume file — no need to send it in the body.
    if definition.route_through_backend:
        # The eval container needs to reach the backend from inside Docker.
        # Use the Docker service name, not localhost.
        payload["backend_url"] = settings.backend_url

    headers = {"X-Service-Token": settings.service_token}

    try:
        async with httpx.AsyncClient(timeout=EVAL_CONTAINER_TIMEOUT) as client:
            resp = await client.post(
                f"{eval_url}/run",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Eval runner timed out. Scenarios with LLM agents can take several minutes.",
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Eval runner is not available. Ensure the eval service is running.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=safe_error(str(e.response.text), "eval"),
        )
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error(str(e), "eval"),
        )


async def _execute_eval_run(
    scenario: EvalScenario,
    scenario_name: str,
    agent_id: str,
    definition: ScenarioDefinition,
    db: AsyncSession,
) -> EvalRun:
    """Create a run record, call the eval container, and record the result."""
    run = EvalRun(
        scenario_id=scenario.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        result = await _call_eval_container(
            scenario_name=scenario_name,
            agent_id=agent_id,
            definition=definition,
        )
        run.status = "passed" if result.get("passed") else "failed"
        run.result = json.dumps(result)
    except HTTPException as e:
        run.status = "error"
        run.result = json.dumps({"error": e.detail})
        logger.warning("Eval run %s failed: %s", run.id, e.detail)
    finally:
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()

    return run


@router.post("/scenarios", response_model=EvalScenarioResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_scenario(
    request: Request,
    body: EvalScenarioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new eval scenario."""
    # Verify agent belongs to user
    await get_owned_or_404(db, Agent, body.agent_id, current_user.id, id_field="letta_agent_id")

    await check_unique_for_user(db, EvalScenario, current_user.id, "name", body.name, error_label="Scenario")

    scenario = EvalScenario(
        user_id=current_user.id,
        agent_id=body.agent_id,
        name=body.name,
        description=body.description,
        definition=json.dumps(body.definition.model_dump()),
    )
    db.add(scenario)
    await db.flush()
    return EvalScenarioResponse.from_orm(scenario)


@router.get("/scenarios", response_model=EvalScenarioListResponse)
async def list_scenarios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all eval scenarios for the current user."""
    scenarios = await list_owned(db, EvalScenario, current_user.id, order_by=EvalScenario.created_at.desc())

    count_result = await db.execute(
        select(func.count()).select_from(EvalScenario).where(EvalScenario.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    return EvalScenarioListResponse(
        scenarios=[EvalScenarioResponse.from_orm(s) for s in scenarios],
        total=total,
    )


@router.get("/scenarios/{scenario_id}", response_model=EvalScenarioResponse)
async def get_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an eval scenario by ID."""
    scenario = await get_owned_or_404(db, EvalScenario, scenario_id, current_user.id)
    return EvalScenarioResponse.from_orm(scenario)


@router.put("/scenarios/{scenario_id}", response_model=EvalScenarioResponse)
async def update_scenario(
    scenario_id: str,
    body: EvalScenarioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an eval scenario."""
    scenario = await get_owned_or_404(db, EvalScenario, scenario_id, current_user.id)

    if body.name is not None:
        scenario.name = body.name
    if body.description is not None:
        scenario.description = body.description
    if body.agent_id is not None:
        await get_owned_or_404(db, Agent, body.agent_id, current_user.id, id_field="letta_agent_id")
        scenario.agent_id = body.agent_id
    if body.definition is not None:
        scenario.definition = json.dumps(body.definition.model_dump())

    await db.flush()
    return EvalScenarioResponse.from_orm(scenario)


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an eval scenario and all its runs."""
    scenario = await get_owned_or_404(db, EvalScenario, scenario_id, current_user.id)
    await db.delete(scenario)


@router.post("/scenarios/{scenario_id}/run", response_model=EvalRunResponse)
@limiter.limit("2/minute")
async def run_scenario(
    request: Request,
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an eval scenario against its agent."""
    scenario = await get_owned_or_404(db, EvalScenario, scenario_id, current_user.id)

    # Verify agent still belongs to user
    await get_owned_or_404(db, Agent, scenario.agent_id, current_user.id, id_field="letta_agent_id")

    try:
        definition_data = json.loads(scenario.definition)
        definition = ScenarioDefinition(**definition_data)
    except (json.JSONDecodeError, ValueError) as e:
        run = EvalRun(
            scenario_id=scenario.id,
            status="error",
            started_at=datetime.now(timezone.utc),
        )
        run.result = json.dumps({"error": f"Invalid scenario definition: {e}"})
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)
        await db.flush()
        return EvalRunResponse.from_orm(run)

    run = await _execute_eval_run(scenario, scenario.name, scenario.agent_id, definition, db)
    return EvalRunResponse.from_orm(run)


@router.post("/run-from-file", response_model=EvalRunResponse)
@limiter.limit("2/minute")
async def run_from_file(
    request: Request,
    body: EvalRunFromFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Load a scenario from a YAML file and run it.

    Creates a scenario record if one doesn't exist with the same name.
    """
    # Load and validate YAML
    # Restrict file paths to the evals directory to prevent path traversal.
    # Use O_NOFOLLOW to prevent symlink attacks (TOCTOU race between
    # path validation and file open).
    from app.config import get_settings

    _EVALS_DIR = Path(get_settings().evals_dir).resolve()
    try:
        resolved_path = Path(body.file_path).resolve()
        if not resolved_path.is_relative_to(_EVALS_DIR):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File path must be within the evals directory",
            )
        # Open with O_NOFOLLOW to reject symlinks — prevents TOCTOU race
        # where an attacker replaces a valid file with a symlink between
        # the path check and the open call.
        fd = os.open(str(resolved_path), os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scenario file not found",
        )
    except OSError as e:
        # ELOOP = too many symlinks (O_NOFOLLOW hit a symlink)
        if e.errno == errno.ELOOP:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File path must not be a symlink",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot open scenario file: {e.strerror}",
        )

    try:
        with os.fdopen(fd, "r") as f:
            yaml_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid YAML: {e}",
        )

    scenario_name = yaml_data.get("name", "unnamed")
    description = yaml_data.get("description")
    agent_id = body.agent_id or yaml_data.get("agent_id")

    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="agent_id is required (in YAML or request body)",
        )

    # Verify agent belongs to user
    await get_owned_or_404(db, Agent, agent_id, current_user.id, id_field="letta_agent_id")

    interactions = yaml_data.get("interactions", [])
    checks = yaml_data.get("checks", [])

    definition = ScenarioDefinition(
        interactions=[{"input": i["input"]} for i in interactions],
        checks=checks,
    )

    # Create scenario if it doesn't exist
    existing = await db.execute(
        select(EvalScenario).where(
            EvalScenario.user_id == current_user.id,
            EvalScenario.name == scenario_name,
        )
    )
    scenario = existing.scalar_one_or_none()

    if scenario:
        scenario.definition = json.dumps(definition.model_dump())
        scenario.agent_id = agent_id
        if description:
            scenario.description = description
    else:
        scenario = EvalScenario(
            user_id=current_user.id,
            agent_id=agent_id,
            name=scenario_name,
            description=description,
            definition=json.dumps(definition.model_dump()),
        )
        db.add(scenario)

    await db.flush()

    run = await _execute_eval_run(scenario, scenario_name, agent_id, definition, db)
    return EvalRunResponse.from_orm(run)


@router.get("/runs", response_model=EvalRunListResponse)
async def list_runs(
    scenario_id: str | None = None,
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List eval runs, optionally filtered by scenario."""
    query = (
        select(EvalRun)
        .join(EvalScenario)
        .where(EvalScenario.user_id == current_user.id)
        .order_by(EvalRun.created_at.desc())
    )

    if scenario_id:
        query = query.where(EvalRun.scenario_id == scenario_id)

    # Count
    count_query = (
        select(func.count()).select_from(EvalRun).join(EvalScenario).where(EvalScenario.user_id == current_user.id)
    )
    if scenario_id:
        count_query = count_query.where(EvalRun.scenario_id == scenario_id)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    result = await db.execute(query.offset(offset).limit(limit))
    runs = list(result.scalars().all())

    return EvalRunListResponse(
        runs=[EvalRunResponse.from_orm(r) for r in runs],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an eval run by ID."""
    # Join through scenario to check ownership
    result = await db.execute(
        select(EvalRun).join(EvalScenario).where(EvalRun.id == run_id, EvalScenario.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="EvalRun not found",
        )
    return EvalRunResponse.from_orm(run)
