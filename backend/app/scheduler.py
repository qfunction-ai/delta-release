"""
APScheduler-based workflow scheduling for self-hosted deployments.

Letta's schedule API is cloud-only, so we use APScheduler to trigger
workflow executions by calling our internal API.
"""

import logging

from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import ConflictingIdError
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global scheduler
    if scheduler is None:
        settings = get_settings()
        # Use PostgreSQL for job persistence
        jobstores = {"default": SQLAlchemyJobStore(url=settings.database_url.replace("+asyncpg", ""))}
        scheduler = AsyncIOScheduler(jobstores=jobstores)
    return scheduler


def start_scheduler():
    """Start the scheduler if not already running."""
    global scheduler
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        scheduler = sched  # Ensure global is set
        logger.info("APScheduler started, jobs loaded: %s", len(sched.get_jobs()))
        for job in sched.get_jobs():
            logger.info("  Job: %s, next run: %s", job.id, job.next_run_time)
    else:
        logger.info("APScheduler already running")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped")


async def schedule_workflow(workflow_id: str, cron_expression: str, agent_id: str, prompt: str):
    """Create a scheduled job for a workflow.

    Args:
        workflow_id: UUID of the workflow
        cron_expression: 5-field cron expression (e.g., "0 9 * * *")
        agent_id: Letta agent ID
        prompt: Rendered prompt to send to agent
    """
    from app.workflows.scheduler_tasks import execute_scheduled_workflow

    sched = get_scheduler()

    parts = cron_expression.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expression}")

    minute, hour, day, month, day_of_week = parts

    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week, timezone="UTC")

    # Add job
    job_id = f"workflow_{workflow_id}"
    sched.add_job(
        execute_scheduled_workflow,
        trigger=trigger,
        id=job_id,
        args=[workflow_id, agent_id, prompt],
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 hour late
    )

    logger.info("Scheduled workflow %s with cron '%s'", workflow_id, cron_expression)


def unschedule_workflow(workflow_id: str):
    """Remove a scheduled job for a workflow."""
    sched = get_scheduler()
    job_id = f"workflow_{workflow_id}"

    try:
        sched.remove_job(job_id)
        logger.info("Unscheduled workflow %s", workflow_id)
    except JobLookupError:
        logger.debug("Workflow %s has no scheduled job to remove", workflow_id)
    except ConflictingIdError as e:
        logger.error("Failed to unschedule workflow %s: %s", workflow_id, e)
        raise


def get_scheduled_workflows() -> list[dict]:
    """Get all scheduled workflow jobs."""
    sched = get_scheduler()
    jobs = []

    for job in sched.get_jobs():
        if job.id.startswith("workflow_"):
            workflow_id = job.id.replace("workflow_", "")
            jobs.append(
                {
                    "workflow_id": workflow_id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )

    return jobs
