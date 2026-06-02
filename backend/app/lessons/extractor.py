"""Extract structured lessons from workflow run results.

Template-based extraction — no LLM call needed. Keeps lessons concise
and actionable so they're useful when injected into future runs.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.constants import RUN_COMPLETED, RUN_FAILED
from app.lessons.models import Lesson
from app.workflows.models import Workflow, WorkflowRun

logger = logging.getLogger(__name__)

MIN_OUTPUT_LENGTH = 50  # Skip runs with very short output
MAX_SUMMARY_LENGTH = 200  # Truncate output summary


def _truncate_at_sentence(text: str, max_len: int = MAX_SUMMARY_LENGTH) -> str:
    """Truncate text at a sentence boundary, max max_len chars."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # Try to break at the last sentence-ending punctuation
    last_stop = max(
        truncated.rfind("."),
        truncated.rfind("!"),
        truncated.rfind("?"),
    )
    if last_stop > max_len // 2:
        return truncated[: last_stop + 1]
    return truncated + "..."


def _classify_error(error_message: str) -> str:
    """Classify an error message into a short category."""
    error_lower = error_message.lower()
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"
    if "connection" in error_lower or "refused" in error_lower:
        return "connection_error"
    if "auth" in error_lower or "401" in error_lower or "403" in error_lower:
        return "auth_error"
    if "not found" in error_lower or "404" in error_lower:
        return "not_found"
    if "rate limit" in error_lower or "429" in error_lower:
        return "rate_limited"
    if "syntax" in error_lower or "parse" in error_lower:
        return "syntax_error"
    return "execution_error"


def extract_lesson_text(
    run: WorkflowRun,
    workflow: Workflow,
) -> tuple[str, str] | None:
    """Extract a lesson from a completed or failed run.

    Returns (category, content) or None if no lesson should be extracted.
    """
    # Failed run → recovery lesson
    if run.status == RUN_FAILED and run.error_message:
        error_type = _classify_error(run.error_message)
        suggestion_map = {
            "timeout": "consider reducing the scope of the query or adding retry logic",
            "connection_error": "verify the target service is reachable and credentials are valid",
            "auth_error": "check that credentials are correctly configured and not expired",
            "not_found": "verify the target resource exists and the identifier is correct",
            "rate_limited": "add delays between requests or reduce batch size",
            "syntax_error": "validate the query syntax before execution",
        }
        suggestion = suggestion_map.get(error_type, "review the error details and adjust the approach")
        content = (
            f"When running '{workflow.name}', a {error_type} occurred: "
            f"{_truncate_at_sentence(run.error_message)}. "
            f"To avoid this, {suggestion}."
        )
        return ("recovery", content)

    # Completed run with output
    if run.status == RUN_COMPLETED and run.output and len(run.output) >= MIN_OUTPUT_LENGTH:
        # Build a factual summary from run metadata, not truncated output.
        # Dumping output fragments into lessons wastes context window and
        # teaches the agent nothing about *how* to succeed.
        duration = ""
        if run.started_at and run.completed_at:
            secs = int((run.completed_at - run.started_at).total_seconds())
            duration = f" in {secs}s"

        steps_desc = f"{run.steps_count} step{'s' if run.steps_count != 1 else ''}"

        # High step count → optimization lesson
        if run.steps_count >= 10:
            content = (
                f"When running '{workflow.name}', the agent completed in {steps_desc}{duration}. "
                f"Consider if this can be accomplished more efficiently."
            )
            return ("optimization", content)

        # Normal completion → strategy lesson
        content = f"When running '{workflow.name}', the agent completed successfully in {steps_desc}{duration}."
        return ("strategy", content)

    return None


async def extract_and_store_lesson(
    run: WorkflowRun,
    workflow: Workflow,
    db: AsyncSession,
) -> Lesson | None:
    """Extract a lesson from a run and store it in the DB.

    Enforces the max lessons per workflow limit by removing the
    lowest-utility lesson if the cap is reached.
    """
    result = extract_lesson_text(run, workflow)
    if result is None:
        return None

    category, content = result

    count_result = await db.execute(select(func.count()).select_from(Lesson).where(Lesson.workflow_id == workflow.id))
    lesson_count = count_result.scalar() or 0

    # If at cap, remove the lowest-utility lesson
    if lesson_count >= get_settings().max_lessons_per_workflow:
        lowest = await db.execute(
            select(Lesson)
            .where(Lesson.workflow_id == workflow.id)
            .order_by(Lesson.utility_score.asc(), Lesson.created_at.asc())
            .limit(1)
        )
        oldest_lesson = lowest.scalar_one_or_none()
        if oldest_lesson:
            await db.delete(oldest_lesson)

    lesson = Lesson(
        user_id=workflow.user_id,
        workflow_id=workflow.id,
        run_id=run.id,
        category=category,
        content=content,
        utility_score=0.0,
        times_used=0,
    )
    db.add(lesson)
    await db.flush()

    logger.info(
        "Extracted %s lesson from run %s (workflow '%s')",
        category,
        run.id,
        workflow.name,
    )
    return lesson


async def update_lesson_utility(
    workflow: Workflow,
    latest_run: WorkflowRun,
    db: AsyncSession,
) -> None:
    """Update lesson utility scores based on the latest run result.

    Compares the latest run's step count to the average of the last 5 runs.
    - If steps decreased by ≥20%, increment utility_score by 1
    - If steps increased by ≥20%, decrement utility_score by 0.5
    - If the run failed and recovery lessons exist, decrement by 1
    - Auto-delete lessons with utility_score < -3
    """
    recent_result = await db.execute(
        select(WorkflowRun)
        .where(
            WorkflowRun.workflow_id == workflow.id,
            WorkflowRun.status == RUN_COMPLETED,
            WorkflowRun.id != latest_run.id,
        )
        .order_by(WorkflowRun.created_at.desc())
        .limit(5)
    )
    recent_runs = list(recent_result.scalars().all())

    lessons_result = await db.execute(select(Lesson).where(Lesson.workflow_id == workflow.id))
    lessons = list(lessons_result.scalars().all())

    if not lessons:
        return

    # If the run failed, penalize recovery lessons (they didn't help)
    if latest_run.status == RUN_FAILED:
        for lesson in lessons:
            if lesson.category == "recovery":
                lesson.utility_score -= 1.0
        logger.debug("Penalized recovery lessons for failed run on workflow '%s'", workflow.name)

    # If the run completed, compare step counts
    elif recent_runs and latest_run.steps_count > 0:
        avg_steps = sum(r.steps_count for r in recent_runs) / len(recent_runs)
        if avg_steps > 0:
            change = (latest_run.steps_count - avg_steps) / avg_steps
            if change <= -0.2:
                # Steps decreased → lessons helped
                for lesson in lessons:
                    lesson.utility_score += 1.0
                logger.debug("Boosted lesson utility for workflow '%s' (steps decreased)", workflow.name)
            elif change >= 0.2:
                # Steps increased → lessons may not be helping
                for lesson in lessons:
                    lesson.utility_score -= 0.5
                logger.debug("Reduced lesson utility for workflow '%s' (steps increased)", workflow.name)

    # Auto-delete lessons with very low utility
    for lesson in lessons:
        if lesson.utility_score < -3:
            await db.delete(lesson)
            logger.info("Auto-deleted low-utility lesson %s (score=%.1f)", lesson.id, lesson.utility_score)

    await db.flush()
