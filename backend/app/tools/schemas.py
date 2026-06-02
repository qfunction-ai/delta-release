import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas import BaseORMSchema, GithubUrlValidatorMixin


class ToolNameValidatorMixin:
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                "Tool name must be lowercase, start with a letter, and contain only letters, numbers, and underscores"
            )
        return v


class ToolSourceCodeValidatorMixin:
    @field_validator("source_code")
    @classmethod
    def validate_source_code(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Source code cannot be empty")
        if "def " not in v:
            raise ValueError("Source code must contain a function definition")
        return v


class ToolCreate(ToolNameValidatorMixin, ToolSourceCodeValidatorMixin, BaseModel):
    name: str
    description: str | None = None
    source_code: str  # Python source code
    json_schema: dict  # JSON schema for the tool
    tags: list[str] | None = None
    pip_requirements: list[str] | None = None  # e.g. ["requests", "paramiko==2.12.0"]


class ToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_code: str | None = None
    json_schema: dict | None = None
    tags: list[str] | None = None
    pip_requirements: list[str] | None = None


class ToolResponse(BaseORMSchema):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    source: str = "manual"
    status: str = "active"
    proposed_by: str | None = None
    tags: list[str] | None
    pip_requirements: list[str] | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_tags(cls, tool: "Tool") -> "ToolResponse":
        return cls(
            id=tool.id,
            user_id=tool.user_id,
            name=tool.name,
            description=tool.description,
            source=tool.source,
            status=tool.status,
            proposed_by=tool.proposed_by,
            tags=tool.tag_list,
            pip_requirements=tool.pip_requirements_list,
            created_at=tool.created_at,
            updated_at=tool.updated_at,
        )


class ToolDetailResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    source: str = "manual"
    source_code: str
    json_schema: dict
    tags: list[str] | None
    pip_requirements: list[str] | None


class SchemaGenerateRequest(BaseModel):
    source_code: str


class PackageInstallRequest(BaseModel):
    packages: list[str]

    @field_validator("packages")
    @classmethod
    def validate_packages(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one package is required")
        pattern = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*(==[a-zA-Z0-9_.]+)?$")
        for pkg in v:
            if not pattern.match(pkg):
                raise ValueError(f"Invalid package specifier: {pkg}")
        return v


class PackageResponse(BaseModel):
    name: str
    version: str


class ToolGithubCreate(GithubUrlValidatorMixin, BaseModel):
    github_url: str


class ToolProposeRequest(ToolNameValidatorMixin, ToolSourceCodeValidatorMixin, BaseModel):
    name: str
    description: str
    source_code: str
    json_schema: dict
    pip_requirements: list[str] | None = None


class ToolProposalResponse(BaseModel):
    """Response for a pending tool proposal with dry-run results."""

    id: UUID
    name: str
    description: str | None
    source_code: str
    json_schema: dict
    tags: list[str] | None
    pip_requirements: list[str] | None
    proposed_by: str
    dry_run_output: str | None = None
    dry_run_error: str | None = None
    created_at: datetime


class AgentToolProposeRequest(ToolNameValidatorMixin, ToolSourceCodeValidatorMixin, BaseModel):
    """Service-to-service propose request from an agent (via Letta sandbox)."""

    agent_id: str
    name: str
    description: str = ""
    source_code: str
    json_schema: dict
    pip_requirements: list[str] | None = None
