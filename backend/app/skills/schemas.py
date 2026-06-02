import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas import BaseORMSchema, GithubUrlValidatorMixin


class SkillCreate(BaseModel):
    name: str
    content: str = Field(max_length=1_000_000)  # 1MB max
    tool_ids: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        # Skill names should be valid directory names
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Skill name must contain only letters, numbers, underscores, and hyphens")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        # Basic validation - must have YAML frontmatter
        if not v.strip().startswith("---"):
            raise ValueError("Skill content must start with YAML frontmatter (---)")
        parts = v.strip().split("---")
        if len(parts) < 3:
            raise ValueError("Skill content must have YAML frontmatter enclosed by ---")
        return v


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = Field(default=None, max_length=1_000_000)
    tool_ids: list[str] | None = None


class SkillGithubCreate(GithubUrlValidatorMixin, BaseModel):
    github_url: str


class SkillResponse(BaseORMSchema):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    source: str
    content: str | None = None
    tool_ids: list[str] = []
    created_at: datetime
    updated_at: datetime


class SkillFileResponse(BaseModel):
    """Metadata for a skill's extra file (no content — use the file download endpoint)."""

    id: UUID
    skill_id: UUID
    path: str
    mime_type: str
    size: int


class SkillContentResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    content: str
    files: list[SkillFileResponse] = []
    tool_ids: list[str] = []
