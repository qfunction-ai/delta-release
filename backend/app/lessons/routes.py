"""CRUD routes for execution lessons."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_db, get_owned_or_404, list_owned
from app.lessons.models import Lesson
from app.lessons.schemas import LessonListResponse
from app.workflows.models import Workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


@router.get("/", response_model=LessonListResponse)
async def list_lessons(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all lessons for the current user."""
    lessons = await list_owned(db, Lesson, current_user.id, order_by=Lesson.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(Lesson).where(Lesson.user_id == current_user.id))
    total = count_result.scalar() or 0

    return LessonListResponse(lessons=lessons, total=total)


@router.get("/{workflow_id}", response_model=LessonListResponse)
async def list_workflow_lessons(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List lessons for a specific workflow."""
    workflow = await get_owned_or_404(db, Workflow, workflow_id, current_user.id)

    result = await db.execute(
        select(Lesson)
        .where(Lesson.workflow_id == workflow.id)
        .order_by(Lesson.utility_score.desc(), Lesson.created_at.desc())
    )
    lessons = list(result.scalars().all())

    return LessonListResponse(lessons=lessons, total=len(lessons))


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lesson_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a lesson."""
    lesson = await get_owned_or_404(db, Lesson, lesson_id, current_user.id)
    await db.delete(lesson)
