"""Schemas for export/import functionality."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ToolExport(BaseModel):
    """Tool data for export (excludes instance-specific fields)."""

    name: str
    description: str | None = None
    source_code: str
    json_schema: dict[str, Any]
    tags: list[str] | None = None
    pip_requirements: list[str] | None = None


class SkillFileExport(BaseModel):
    """Skill file data for export."""

    path: str
    content_text: str | None = None
    content_b64: str | None = None  # base64-encoded binary content
    mime_type: str = "text/plain"


class SkillExport(BaseModel):
    """Skill data for export."""

    name: str
    description: str | None = None
    content: str
    files: list[SkillFileExport] = Field(default_factory=list)


class WorkflowExport(BaseModel):
    """Workflow data for export (references tools/skills by name, excludes agent_id)."""

    name: str
    description: str | None = None
    prompt_template: str
    tool_names: list[str] = Field(default_factory=list)  # Reference by name, not UUID
    skill_names: list[str] = Field(default_factory=list)  # Reference by name, not UUID
    schedule_cron: str | None = None
    default_variables: dict[str, str] | None = None
    include_reasoning: bool = False


class ExportData(BaseModel):
    """Complete export data structure."""

    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now())
    tools: list[ToolExport] = Field(default_factory=list)
    skills: list[SkillExport] = Field(default_factory=list)
    workflows: list[WorkflowExport] = Field(default_factory=list)


class ImportResult(BaseModel):
    """Result of an import operation."""

    tools_imported: int = 0
    tools_skipped: int = 0
    skills_imported: int = 0
    skills_skipped: int = 0
    workflows_imported: int = 0
    workflows_skipped: int = 0
    workflows_needing_agent: int = 0
    errors: list[str] = Field(default_factory=list)


class ImportPreview(BaseModel):
    """Preview of what would be imported (before committing)."""

    tools: int = 0
    skills: int = 0
    workflows: int = 0
    tool_names: list[str] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    workflow_names: list[str] = Field(default_factory=list)


class ExportDataValidator(BaseModel):
    """Validator for import file structure."""

    version: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    workflows: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not v.startswith("1."):
            raise ValueError(f"Unsupported export version: {v}. Expected 1.x")
        return v

    @field_validator("tools", "skills", "workflows", mode="before")
    @classmethod
    def validate_lists(cls, v: Any) -> list:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("Must be a list")
        return v
