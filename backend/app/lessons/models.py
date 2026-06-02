import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, CreatedOnlyMixin, OwnedMixin


class Lesson(Base, OwnedMixin, CreatedOnlyMixin):
    """A lesson extracted from a workflow run, stored for future execution guidance."""

    __tablename__ = "lessons"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,  # NULL if the run is deleted
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # "strategy" | "recovery" | "optimization"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    utility_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="lessons")
    run: Mapped["WorkflowRun"] = relationship("WorkflowRun")
