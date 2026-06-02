from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, CreatedOnlyMixin, OwnedMixin


class Agent(Base, OwnedMixin, CreatedOnlyMixin):
    __tablename__ = "agents"

    letta_agent_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding: Mapped[str] = mapped_column(String(255), nullable=False)
