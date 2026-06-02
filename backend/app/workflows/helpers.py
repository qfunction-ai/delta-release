"""Shared workflow execution helpers."""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.constants import LETTA_ERRORS, RUN_FAILED
from app.errors import letta_error_detail, safe_error
from app.lessons.extractor import extract_and_store_lesson, update_lesson_utility

logger = logging.getLogger(__name__)


async def mark_run_failed(run, error) -> None:
    """Mark a workflow run as failed with a safe error message.

    Uses letta_error_detail for Letta errors (passes through
    user-actionable errors like parse/syntax/400), and safe_error
    for everything else.
    """
    run.status = RUN_FAILED
    if isinstance(error, LETTA_ERRORS):
        run.error_message = letta_error_detail(error)
    else:
        run.error_message = safe_error(str(error), "internal")
    run.completed_at = datetime.now(timezone.utc)


async def post_run_lesson_extraction(run, workflow, db) -> None:
    """Extract lessons from a completed run and update utility scores.

    Non-fatal — failures are logged but don't affect the run.
    """
    try:
        await extract_and_store_lesson(run, workflow, db)
        await update_lesson_utility(workflow, run, db)
    except (SQLAlchemyError, ValueError) as e:
        logger.debug("Lesson extraction failed (non-fatal): %s", e)
