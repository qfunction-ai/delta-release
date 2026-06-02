from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.sanitize import sanitize_string, validate_cron_expression, validate_prompt_template
from app.schemas import BaseORMSchema


class WorkflowValidatorMixin:
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("Workflow name cannot be empty")
        return sanitize_string(v.strip())

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return sanitize_string(v)

    @field_validator("prompt_template")
    @classmethod
    def validate_template(cls, v: str | None) -> str | None:
        if v is None:
            return None
        is_valid, error = validate_prompt_template(v)
        if not is_valid:
            raise ValueError(f"Invalid prompt template: {error}")
        return v


class WorkflowCreate(WorkflowValidatorMixin, BaseModel):
    name: str
    agent_id: str
    description: str | None = None
    prompt_template: str  # Template with {{variable}} placeholders
    tool_ids: list[UUID] | None = None  # Tools to attach during execution
    skill_ids: list[UUID] | None = None  # Skills to make available
    schedule_cron: str | None = None  # Cron expression (5-field, e.g., "0 9 * * *")
    default_variables: dict[str, str] | None = None  # Default values for {{variables}}
    include_reasoning: bool = False  # Include reasoning in output

    @field_validator("schedule_cron")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not validate_cron_expression(v):
            raise ValueError("Invalid cron expression format")
        return v.strip()


class WorkflowUpdate(WorkflowValidatorMixin, BaseModel):
    name: str | None = None
    agent_id: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    tool_ids: list[UUID] | None = None
    skill_ids: list[UUID] | None = None
    schedule_cron: str | None = None
    default_variables: dict[str, str] | None = None
    include_reasoning: bool | None = None


class WorkflowResponse(BaseORMSchema):
    id: UUID
    user_id: UUID
    agent_id: str
    name: str
    description: str | None
    prompt_template: str
    tool_ids: list[UUID] | None
    skill_ids: list[UUID] | None
    schedule_cron: str | None
    default_variables: dict[str, str] | None
    include_reasoning: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_with_json(cls, workflow: "Workflow") -> "WorkflowResponse":
        return cls(
            id=workflow.id,
            user_id=workflow.user_id,
            agent_id=workflow.agent_id,
            name=workflow.name,
            description=workflow.description,
            prompt_template=workflow.prompt_template,
            tool_ids=workflow.tool_ids_list,
            skill_ids=workflow.skill_ids_list,
            schedule_cron=workflow.schedule_cron,
            default_variables=workflow.default_variables_dict,
            include_reasoning=workflow.include_reasoning,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


class WorkflowRunWithOutput(BaseORMSchema):
    id: UUID
    workflow_id: UUID
    status: str
    input_variables: dict | None
    rendered_prompt: str | None
    output: str | None
    reasoning_output: str | None
    error_message: str | None
    steps_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    @classmethod
    def from_orm_with_json(cls, run: "WorkflowRun") -> "WorkflowRunWithOutput":
        return cls(
            id=run.id,
            workflow_id=run.workflow_id,
            status=run.status,
            input_variables=run.input_variables_dict,
            rendered_prompt=run.rendered_prompt,
            output=run.output,
            reasoning_output=run.reasoning_output,
            error_message=run.error_message,
            steps_count=run.steps_count,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )


class WorkflowRunVariables(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)  # Variables to substitute in template


class WorkflowDetailResponse(WorkflowResponse):
    runs: list[WorkflowRunWithOutput]

    @classmethod
    def from_orm_full(cls, workflow: "Workflow", runs: list["WorkflowRunWithOutput"]) -> "WorkflowDetailResponse":
        base = WorkflowResponse.from_orm_with_json(workflow)
        return cls(**base.model_dump(), runs=runs)
