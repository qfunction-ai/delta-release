from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas import BaseORMSchema


class LessonResponse(BaseORMSchema):
    id: UUID
    workflow_id: UUID
    run_id: UUID | None
    category: str
    content: str
    utility_score: float
    times_used: int
    created_at: datetime


class LessonListResponse(BaseModel):
    lessons: list[LessonResponse]
    total: int
