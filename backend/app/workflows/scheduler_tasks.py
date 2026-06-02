"""
Scheduled workflow execution tasks.

These tasks are called by APScheduler at scheduled times.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.agents.prompts import extract_message_parts
from app.agents.run_prep import prepare_prompt_context
from app.async_utils import retry_letta_call
from app.config import get_settings
from app.constants import LETTA_DB_ERRORS, RUN_COMPLETED, RUN_PENDING, RUN_RUNNING
from app.database import normalize_db_url
from app.letta_client import get_letta_client
from app.workflows.helpers import mark_run_failed, post_run_lesson_extraction
from app.workflows.models import Workflow, WorkflowRun

logger = logging.getLogger(__name__)


async def _run_scheduled_workflow(
    workflow: Workflow,
    run: WorkflowRun,
    agent_id: str,
    prompt: str,
    session: AsyncSession,
) -> None:
    """Execute the workflow via Letta and update the run record.

    Handles the actual agent call, output extraction, and lesson extraction.
    On LETTA_DB_ERRORS, marks the run as failed.
    """
    client = get_letta_client()

    # Insert skills/lessons into archival memory and prepend prompt prefixes
    prompt = await prepare_prompt_context(workflow, agent_id, prompt, client, session)

    run.status = RUN_RUNNING
    run.started_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("Created run record for workflow %s", workflow.id)

    try:
        response = await retry_letta_call(
            client.agents.messages.create,
            agent_id=agent_id,
            messages=[{"role": "user", "content": prompt}],
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
            run.steps_count = response.usage.step_count if hasattr(response.usage, "step_count") else 0

        await session.commit()
        logger.info("Scheduled workflow %s completed successfully", workflow.id)

        await post_run_lesson_extraction(run, workflow, session)
        await session.commit()

    except LETTA_DB_ERRORS as e:
        await mark_run_failed(run, e)
        await session.commit()
        logger.error("Scheduled workflow %s failed: %s", workflow.id, e)

        await post_run_lesson_extraction(run, workflow, session)
        await session.commit()


async def _handle_scheduled_failure(run: WorkflowRun | None, session: AsyncSession) -> None:
    """Mark a stuck run as failed, or rollback if no run record exists."""
    if run is not None and run.status in (RUN_PENDING, RUN_RUNNING):
        try:
            await mark_run_failed(run, Exception("Workflow execution failed"))
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
    else:
        await session.rollback()


async def execute_scheduled_workflow(workflow_id: str, agent_id: str, prompt: str):
    """Execute a scheduled workflow.

    This is called by APScheduler at the scheduled time.
    It creates a run record and executes the workflow.

    Args:
        workflow_id: UUID of the workflow
        agent_id: Letta agent ID
        prompt: Pre-rendered prompt (from default_variables)
    """
    logger.info("Executing scheduled workflow %s", workflow_id)

    # Create async engine for this task (APScheduler runs in separate context)
    settings = get_settings()
    db_url = normalize_db_url(settings.database_url)

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        run = None
        try:
            result = await session.execute(select(Workflow).where(Workflow.id == workflow_id))
            workflow = result.scalar_one_or_none()

            if not workflow:
                logger.error("Workflow %s not found", workflow_id)
                return

            # Create run record — don't commit yet, keep in same transaction
            # so failures during skill attachment don't leave a stuck 'pending' row
            run = WorkflowRun(
                workflow_id=workflow.id,
                status=RUN_PENDING,
                input_variables=workflow.default_variables,
                rendered_prompt=prompt,
            )
            session.add(run)
            await session.flush()  # Assign ID without committing

            await _run_scheduled_workflow(workflow, run, agent_id, prompt, session)

        except LETTA_DB_ERRORS as e:
            logger.error("Error executing scheduled workflow %s: %s", workflow_id, e)
            if run is not None and run.status == RUN_PENDING:
                try:
                    await mark_run_failed(run, e)
                    await session.commit()
                except SQLAlchemyError:
                    await session.rollback()
            else:
                await session.rollback()
        except Exception as e:
            logger.error("Unexpected error executing scheduled workflow %s: %s", workflow_id, e, exc_info=True)
            await _handle_scheduled_failure(run, session)
        finally:
            await engine.dispose()
