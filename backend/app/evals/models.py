"""Eval scenario and run models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, CreatedOnlyMixin, OwnedMixin, TimestampMixin


class EvalScenario(Base, OwnedMixin, TimestampMixin):
    """A scenario definition for agent evaluation."""

    __tablename__ = "eval_scenarios"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_eval_scenarios_user_name"),)

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)  # JSON — interactions + checks

    # Relationship to runs
    runs: Mapped[list["EvalRun"]] = relationship("EvalRun", back_populates="scenario", cascade="all, delete-orphan")


class EvalRun(Base, CreatedOnlyMixin):
    """A single execution of an eval scenario."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending → running → passed/failed/error
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON — full results
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to scenario
    scenario: Mapped["EvalScenario"] = relationship("EvalScenario", back_populates="runs")
