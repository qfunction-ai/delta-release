import uuid

from sqlalchemy import ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, OwnedMixin, TimestampMixin


class Skill(Base, OwnedMixin, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_skills_user_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    content: Mapped[str] = mapped_column(Text, nullable=False)


class SkillFile(Base, TimestampMixin):
    """Extra file attached to a skill (scripts, references, assets, etc.)."""

    __tablename__ = "skill_files"
    __table_args__ = (UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/plain")


class SkillTool(Base):
    """Join table linking skills to their required tools."""

    __tablename__ = "skill_tools"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True
    )
