from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, OwnedMixin, TimestampMixin


class Tool(Base, OwnedMixin, TimestampMixin):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tools_user_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    letta_tool_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    json_schema: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Comma-separated
    pip_requirements: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Comma-separated
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    proposed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dry_run_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def tag_list(self) -> list[str] | None:
        """Parse comma-separated tags into a list."""
        return self.tags.split(",") if self.tags else None

    @property
    def pip_requirements_list(self) -> list[str] | None:
        """Parse comma-separated pip_requirements into a list."""
        return self.pip_requirements.split(",") if self.pip_requirements else None
