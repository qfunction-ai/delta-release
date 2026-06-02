from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, OwnedMixin, TimestampMixin


class Credential(Base, OwnedMixin, TimestampMixin):
    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_credentials_user_key"),)

    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # SPLUNK_API_KEY
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False)  # splunk, crowdstrike, sentinelone, etc.
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    primary_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secondary_key_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
