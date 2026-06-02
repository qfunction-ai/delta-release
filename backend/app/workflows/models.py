import json
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import RUN_CANCELLED, RUN_COMPLETED, RUN_FAILED, RUN_PENDING, RUN_RUNNING
from app.database import Base, CreatedOnlyMixin, OwnedMixin, TimestampMixin

# Workflow run status enum — values must match app.constants
RunStatus = ENUM(RUN_PENDING, RUN_RUNNING, RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED, name="run_status")


class Workflow(Base, OwnedMixin, TimestampMixin):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_workflows_user_name"),)

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Letta agent ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)  # Template with {{variables}}
    tool_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of tool IDs (UUIDs)
    skill_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of skill IDs (UUIDs)
    # Scheduling (APScheduler-based for self-hosted)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Cron expression (5-field)
    default_variables: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object with default values
    include_reasoning: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship to runs
    runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun", back_populates="workflow", cascade="all, delete-orphan"
    )

    # Relationship to lessons
    lessons: Mapped[list["Lesson"]] = relationship("Lesson", back_populates="workflow", cascade="all, delete-orphan")

    @property
    def tool_ids_list(self) -> list | None:
        """Parse JSON tool_ids into a list."""
        return json.loads(self.tool_ids) if self.tool_ids else None

    @property
    def skill_ids_list(self) -> list | None:
        """Parse JSON skill_ids into a list."""
        return json.loads(self.skill_ids) if self.skill_ids else None

    @property
    def default_variables_dict(self) -> dict | None:
        """Parse JSON default_variables into a dict."""
        return json.loads(self.default_variables) if self.default_variables else None


class WorkflowRun(Base, CreatedOnlyMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(RunStatus, default=RUN_PENDING, nullable=False)
    input_variables: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    letta_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steps_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to workflow
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="runs")

    @property
    def input_variables_dict(self) -> dict | None:
        """Parse JSON input_variables into a dict."""
        return json.loads(self.input_variables) if self.input_variables else None
