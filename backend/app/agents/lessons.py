"""Lesson lookup helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.models import Lesson


async def get_lessons_for_workflow(
    workflow_id: str,
    db: AsyncSession,
) -> list[Lesson]:
    """Load lessons for a workflow, ordered by utility score."""
    result = await db.execute(
        select(Lesson)
        .where(Lesson.workflow_id == workflow_id)
        .order_by(Lesson.utility_score.desc(), Lesson.created_at.desc())
        .limit(3)
    )
    return list(result.scalars().all())
