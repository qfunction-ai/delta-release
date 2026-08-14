import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.base import ConflictingIdError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import Agent
from app.agents.prompts import extract_message_parts
from app.agents.run_prep import inject_skill_context, prepare_workflow_run
from app.agents.skills import get_skills_by_ids
from app.async_utils import event_to_sse, retry_letta_call, sse_response, stream_letta_response
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config import get_settings
from app.constants import LETTA_DB_ERRORS, RUN_COMPLETED, RUN_RUNNING
from app.database import check_unique_for_user, get_db, get_owned_or_404, list_owned
from app.errors import safe_error
from app.rate_limit import limiter
from app.scheduler import schedule_workflow, unschedule_workflow
from app.skills.models import Skill
from app.tools.models import Tool
from app.workflows.helpers import mark_run_failed, post_run_lesson_extraction
from app.workflows.models import Workflow, WorkflowRun
from app.workflows.schemas import (
    WorkflowCreate,
    WorkflowDetailResponse,
    WorkflowResponse,
    WorkflowRunVariables,
    WorkflowRunWithOutput,
    WorkflowUpdate,
)
from app.workflows.template import render_template

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


async def _validate_tool_skill_ids(
    tool_ids: list[str] | None,
    skill_ids: list[str] | None,
    user_id: str,
    db: AsyncSession,
) -> None:
    """Validate that all tool and skill IDs exist and belong to the given user."""
    if tool_ids:
        result = await db.execute(
            select(Tool.id).where(
                Tool.id.in_(tool_ids),
                Tool.user_id == user_id,
            )
        )
        valid_tool_ids = [str(r[0]) for r in result.fetchall()]
        if len(valid_tool_ids) != len(tool_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more tool IDs are invalid or not owned by current user",
            )

    if skill_ids:
        result = await db.execute(
            select(Skill.id).where(
                Skill.id.in_(skill_ids),
                Skill.user_id == user_id,
            )
        )
        valid_skill_ids = [str(r[0]) for r in result.fetchall()]
        if len(valid_skill_ids) != len(skill_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more skill IDs are invalid or not owned by current user",
            )


@router.get("/", response_model=list[WorkflowResponse])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's workflows."""
    workflows = await list_owned(db, Workflow, current_user.id)
    return [WorkflowResponse.from_orm_with_json(w) for w in workflows]


@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow_data: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow."""
    # Verify agent belongs to the current user
    await get_owned_or_404(
        db,
        Agent,
        workflow_data.agent_id,
        current_user.id,
        id_field="letta_agent_id",
    )

    await check_unique_for_user(db, Workflow, current_user.id, "name", workflow_data.name)

    await _validate_tool_skill_ids(workflow_data.tool_ids, workflow_data.skill_ids, current_user.id, db)

    workflow = Workflow(
        user_id=current_user.id,
        name=workflow_data.name,
        agent_id=workflow_data.agent_id,
        description=workflow_data.description,
        prompt_template=workflow_data.prompt_template,
        tool_ids=json.dumps([str(tid) for tid in workflow_data.tool_ids]) if workflow_data.tool_ids else None,
        skill_ids=json.dumps([str(sid) for sid in workflow_data.skill_ids]) if workflow_data.skill_ids else None,
        schedule_cron=workflow_data.schedule_cron,
        default_variables=json.dumps(workflow_data.default_variables) if workflow_data.default_variables else None,
        include_reasoning=workflow_data.include_reasoning,
    )
    db.add(workflow)
    await db.flush()

    # Create schedule if cron is provided
    if workflow_data.schedule_cron:
        default_vars = workflow_data.default_variables or {}
        scheduled_prompt = render_template(workflow_data.prompt_template, default_vars)

        if workflow_data.skill_ids:
            skills = await get_skills_by_ids([str(sid) for sid in workflow_data.skill_ids], str(current_user.id), db)
            if skills:
                scheduled_prompt = await inject_skill_context(scheduled_prompt, skills, db)

        try:
            await schedule_workflow(
                workflow_id=str(workflow.id),
                cron_expression=workflow_data.schedule_cron,
                agent_id=workflow_data.agent_id,
                prompt=scheduled_prompt,
            )
        except (SQLAlchemyError, ConflictingIdError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error(str(e), "internal"))

    return WorkflowResponse.from_orm_with_json(workflow)


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workflow details with recent runs."""
    workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    runs_result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(20)
    )
    runs = runs_result.scalars().all()

    return WorkflowDetailResponse.from_orm_full(workflow, [WorkflowRunWithOutput.from_orm_with_json(r) for r in runs])


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    workflow_data: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow."""
    workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    # Handle schedule changes — reschedule if cron, prompt, or variables change.
    # model_fields_set distinguishes "field absent from request" (leave schedule
    # alone) from "field explicitly null" (remove the existing schedule).
    cron_provided = "schedule_cron" in workflow_data.model_fields_set
    needs_reschedule = (
        workflow_data.schedule_cron is not None
        or (cron_provided and workflow.schedule_cron)
        or (workflow_data.prompt_template is not None and workflow.schedule_cron)
        or (workflow_data.default_variables is not None and workflow.schedule_cron)
    )

    if needs_reschedule:
        # Remove old schedule if exists
        if workflow.schedule_cron:
            unschedule_workflow(str(workflow.id))

        # Determine the effective cron, prompt, and variables
        effective_cron = (
            workflow_data.schedule_cron if workflow_data.schedule_cron is not None else workflow.schedule_cron
        )
        effective_prompt = (
            workflow_data.prompt_template if workflow_data.prompt_template is not None else workflow.prompt_template
        )
        effective_vars = (
            workflow_data.default_variables
            if workflow_data.default_variables is not None
            else workflow.default_variables
        )

        # Create new schedule if cron is present
        if effective_cron:
            default_vars = json.loads(effective_vars) if effective_vars else {}

            scheduled_prompt = render_template(effective_prompt, default_vars)

            # Add skill context
            skill_ids = json.loads(workflow.skill_ids) if workflow.skill_ids else []
            if skill_ids:
                skills = await get_skills_by_ids(skill_ids, str(current_user.id), db)
                if skills:
                    scheduled_prompt = await inject_skill_context(scheduled_prompt, skills, db)

            try:
                await schedule_workflow(
                    workflow_id=str(workflow.id),
                    cron_expression=effective_cron,
                    agent_id=workflow.agent_id,
                    prompt=scheduled_prompt,
                )
            except (SQLAlchemyError, ConflictingIdError) as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=safe_error(str(e), "internal"))

        workflow.schedule_cron = workflow_data.schedule_cron

    if workflow_data.name is not None and workflow_data.name != workflow.name:
        await check_unique_for_user(
            db,
            Workflow,
            current_user.id,
            "name",
            workflow_data.name,
            exclude_id=workflow.id,
        )
        workflow.name = workflow_data.name
    if workflow_data.description is not None:
        workflow.description = workflow_data.description
    if workflow_data.prompt_template is not None:
        workflow.prompt_template = workflow_data.prompt_template
    if workflow_data.tool_ids is not None or workflow_data.skill_ids is not None:
        # Validate ownership before persisting (prevents IDOR)
        await _validate_tool_skill_ids(workflow_data.tool_ids, workflow_data.skill_ids, current_user.id, db)
    if workflow_data.tool_ids is not None:
        workflow.tool_ids = json.dumps([str(tid) for tid in workflow_data.tool_ids])
    if workflow_data.skill_ids is not None:
        workflow.skill_ids = json.dumps([str(sid) for sid in workflow_data.skill_ids])
    if workflow_data.default_variables is not None:
        workflow.default_variables = json.dumps(workflow_data.default_variables)
    if workflow_data.include_reasoning is not None:
        workflow.include_reasoning = workflow_data.include_reasoning
    if workflow_data.agent_id is not None:
        # Verify new agent belongs to the current user
        await get_owned_or_404(
            db,
            Agent,
            workflow_data.agent_id,
            current_user.id,
            id_field="letta_agent_id",
        )
        workflow.agent_id = workflow_data.agent_id

    await db.flush()
    return WorkflowResponse.from_orm_with_json(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow and all its runs."""
    workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    # Remove schedule if exists
    if workflow.schedule_cron:
        unschedule_workflow(str(workflow.id))

    await db.delete(workflow)


@router.post("/{workflow_id}/run", response_model=WorkflowRunWithOutput)
@limiter.limit("10/minute")
async def execute_workflow(
    request: Request,
    workflow_id: str,
    run_data: WorkflowRunVariables,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a workflow synchronously."""
    workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    # Shared preparation: render prompt, insert skills/lessons, create run, attach tools
    rendered_prompt, run, client = await prepare_workflow_run(workflow, run_data.variables, str(current_user.id), db)

    try:
        response = await retry_letta_call(
            client.agents.messages.create,
            agent_id=workflow.agent_id,
            messages=[{"role": "user", "content": rendered_prompt}],
            max_steps=get_settings().max_steps,
        )

        assistant_output, reasoning_output = extract_message_parts(
            response.messages, include_reasoning=workflow.include_reasoning
        )
        run.output = assistant_output
        run.reasoning_output = reasoning_output
        run.status = RUN_COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        run.letta_run_id = response.run_id if hasattr(response, "run_id") else None

        if hasattr(response, "usage") and response.usage:
            run.steps_count = (
                response.usage.step_count
                if (hasattr(response.usage, "step_count") and response.usage.step_count is not None)
                else 0
            )

    except LETTA_DB_ERRORS as e:
        await mark_run_failed(run, e)
    except Exception as e:
        logger.error("Unexpected error in workflow %s run: %s", workflow_id, e, exc_info=True)
        await mark_run_failed(run, e)

    await db.flush()

    await post_run_lesson_extraction(run, workflow, db)

    return WorkflowRunWithOutput.from_orm_with_json(run)


@router.post("/{workflow_id}/stream")
@limiter.limit("10/minute")
async def stream_workflow(
    request: Request,
    workflow_id: str,
    req: WorkflowRunVariables,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a workflow with streaming output via SSE."""

    async def event_generator():
        try:
            workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)
        except HTTPException:
            yield f"data: {json.dumps({'error': 'Workflow not found'})}\n\n"
            return

        # Shared preparation: render prompt, insert skills/lessons, create run, attach tools
        rendered_prompt, run, client = await prepare_workflow_run(workflow, req.variables, str(current_user.id), db)

        # Commit the DB transaction before streaming starts.
        # prepare_workflow_run may INSERT rows (e.g., workflow runs) or UPDATE
        # rows. If we don't commit before the stream, the transaction stays
        # open for the entire duration of the agent response (30+ seconds).
        # Concurrent requests that touch the same tables will block on the
        # uncommitted transaction's locks.
        await db.commit()

        yield f"data: {json.dumps({'type': 'status', 'status': RUN_RUNNING, 'run_id': str(run.id)})}\n\n"

        assistant_parts = []
        reasoning_parts = []

        try:
            async for event in stream_letta_response(
                client,
                workflow.agent_id,
                [{"role": "user", "content": rendered_prompt}],
                include_reasoning=workflow.include_reasoning,
                max_steps=get_settings().max_steps,
            ):
                # Collect content/reasoning for run output
                if event["type"] == "content":
                    assistant_parts.append(event["content"])
                elif event["type"] == "reasoning":
                    reasoning_parts.append(event["content"])
                elif event["type"] == "status" and event["status"] == "completed":
                    run.status = RUN_COMPLETED
                    run.completed_at = datetime.now(timezone.utc)
                    run.output = "".join(assistant_parts) if assistant_parts else None
                    run.reasoning_output = (
                        "".join(reasoning_parts) if (workflow.include_reasoning and reasoning_parts) else None
                    )
                elif event["type"] == "usage":
                    run.steps_count = event["steps"]

                sse_line = event_to_sse(event, include_reasoning=True)
                if sse_line:
                    yield sse_line

        except LETTA_DB_ERRORS as e:
            await mark_run_failed(run, e)
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error(str(e), 'letta')})}\n\n"
        except Exception as e:
            logger.error("Unexpected error streaming workflow %s: %s", workflow_id, e, exc_info=True)
            await mark_run_failed(run, e)
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error(str(e), 'internal')})}\n\n"

        await db.flush()

        await post_run_lesson_extraction(run, workflow, db)

    return sse_response(event_generator())


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunWithOutput])
async def list_workflow_runs(
    workflow_id: str,
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List runs for a workflow."""
    # Verify workflow belongs to user
    await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()

    return [WorkflowRunWithOutput.from_orm_with_json(r) for r in runs]


@router.get("/runs/{run_id}", response_model=WorkflowRunWithOutput)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific run."""
    result = await db.execute(
        select(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .where(WorkflowRun.id == run_id, Workflow.user_id == current_user.id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return WorkflowRunWithOutput.from_orm_with_json(run)
