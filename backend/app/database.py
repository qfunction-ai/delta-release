import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from alembic.config import Config
from fastapi import HTTPException, status
from sqlalchemy import DateTime, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import DatabaseError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from alembic import command
from app.config import get_settings

logger = logging.getLogger(__name__)


def normalize_db_url(url: str) -> str:
    """Ensure a PostgreSQL URL uses the asyncpg driver.

    Alembic and external tools often set DATABASE_URL with
    postgresql:// — asyncpg needs postgresql+asyncpg://.
    """
    if "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


# Lazy engine — avoids import-time side effects (opening a connection pool
# when the module is imported). The engine is created on first access.
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker | None = None


def _get_engine() -> AsyncEngine:
    """Lazily create the async engine on first access."""
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = normalize_db_url(settings.database_url)
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return _engine


def _get_session_maker() -> async_sessionmaker:
    """Lazily create the session maker on first access."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


class Base(DeclarativeBase):
    pass


class OwnedMixin:
    """Mixin for models that belong to a user. Provides id + user_id columns."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


class TimestampMixin:
    """Mixin for models with created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CreatedOnlyMixin:
    """Mixin for models that only have created_at (no updated_at)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


async def get_owned_or_404(
    session: AsyncSession,
    model: type,
    object_id,
    user_id,
    id_field: str = "id",
    user_field: str = "user_id",
):
    """Get an owned object or raise 404. Reduces boilerplate across all route modules."""
    result = await session.execute(
        select(model).where(
            getattr(model, id_field) == object_id,
            getattr(model, user_field) == user_id,
        )
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return obj


async def list_owned(
    session: AsyncSession,
    model: type,
    user_id,
    user_field: str = "user_id",
    order_by=None,
) -> list:
    """List all objects owned by a user. Reduces boilerplate across all route modules."""
    stmt = select(model).where(getattr(model, user_field) == user_id)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_agent_by_letta_id_or_404(
    session: AsyncSession,
    letta_agent_id: str,
) -> "Agent":
    """Get an Agent by its letta_agent_id or raise 404."""
    from app.agents.models import Agent

    result = await session.execute(select(Agent).where(Agent.letta_agent_id == letta_agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


async def check_unique_for_user(
    session: AsyncSession,
    model: type,
    user_id,
    field: str,
    value: str,
    exclude_id=None,
    error_label: str | None = None,
):
    """Raise HTTPException 409 if a resource with this field value already exists for the user."""
    query = select(model).where(
        getattr(model, field) == value,
        getattr(model, "user_id") == user_id,
    )
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    result = await session.execute(query)
    if result.scalar_one_or_none():
        label = error_label or model.__name__
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} with this {field} already exists",
        )


async def get_db():
    async with _get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        finally:
            await session.close()


async def init_db():
    """Initialize the database schema.

    For existing databases with an alembic_version table, runs any pending
    Alembic migrations. For databases created by the old create_all approach
    (has tables but no alembic_version), stamps the head revision. For fresh
    databases, uses create_all to create all tables and then stamps the head
    revision.

    The migration chain was originally generated against a create_all database,
    so some early migrations are empty or reference tables that wouldn't exist
    on a fresh database. Using create_all for the fresh case avoids those
    issues while still maintaining the alembic_version for future migrations.
    """
    alembic_ini = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    alembic_cfg = Config(alembic_ini)

    # Build a sync database URL for Alembic (psycopg2, not asyncpg)
    sync_url = get_settings().database_url
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)

    async with _get_engine().begin() as conn:
        result = await conn.execute(
            text("SELECT EXISTS (  SELECT 1 FROM information_schema.tables   WHERE table_name = 'alembic_version')")
        )
        has_version_table = result.scalar()

        if has_version_table:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
        else:
            current_version = None

        if current_version is None:
            # Check if any app tables exist (legacy create_all database).
            result = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name NOT IN ('alembic_version', 'pg_stat_statements')"
                )
            )
            table_count = result.scalar()

    if current_version is not None:
        # Existing alembic_version — run upgrade for any pending migrations.
        logger.info("Running Alembic upgrade from revision %s.", current_version)
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
            logger.info("Alembic migrations applied.")
        except (OperationalError, DatabaseError) as e:
            logger.error("Alembic migration failed: %s", e)
            raise
    elif table_count > 0:
        # Database was created by create_all — stamp head revision.
        logger.warning(
            "Database has %d tables but no alembic_version. Stamping head revision (legacy create_all database).",
            table_count,
        )
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, command.stamp, alembic_cfg, "head")
            logger.info("Stamped alembic_version to head.")
        except (OperationalError, DatabaseError) as e:
            logger.error("Alembic stamp failed: %s", e)
            raise
    else:
        # Fresh database — create all tables and stamp head revision.
        logger.info("Fresh database — creating tables with create_all.")
        async with _get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created. Stamping alembic_version to head.")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, command.stamp, alembic_cfg, "head")
            logger.info("Stamped alembic_version to head.")
        except (OperationalError, DatabaseError) as e:
            logger.error("Alembic stamp failed: %s", e)
            raise
