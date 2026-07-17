from sqlalchemy import Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, OwnedMixin, TimestampMixin


class UserSettings(Base, OwnedMixin, TimestampMixin):
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_settings_user_id"),)

    agent_tool_creation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    eval_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether this user's agents can be accessed by the eval container. "
        "Must be explicitly enabled before evals can run against this user's agents.",
    )
