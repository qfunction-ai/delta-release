"""Tests for database helper functions."""

import uuid

import pytest
from fastapi import HTTPException

from app.database import check_unique_for_user, list_owned, normalize_db_url


class TestNormalizeDbUrl:
    """Tests for normalize_db_url."""

    def test_adds_asyncpg_driver(self):
        """Adds +asyncpg to postgresql:// URL."""
        assert normalize_db_url("postgresql://user:pass@host/db") == "postgresql+asyncpg://user:pass@host/db"

    def test_preserves_asyncpg_driver(self):
        """Doesn't double-add +asyncpg if already present."""
        url = "postgresql+asyncpg://user:pass@host/db"
        assert normalize_db_url(url) == url

    def test_non_postgresql_url_unchanged(self):
        """Leaves non-postgresql URLs unchanged."""
        assert normalize_db_url("sqlite:///test.db") == "sqlite:///test.db"


@pytest.mark.asyncio
class TestCheckUniqueForUser:
    """Tests for check_unique_for_user."""

    async def test_no_duplicate_passes(self, app_client, engine):
        """check_unique_for_user passes when no duplicate exists."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.workflows.models import Workflow

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            fake_user_id = uuid.uuid4()
            # No duplicate — should not raise
            await check_unique_for_user(session, Workflow, fake_user_id, "name", "nonexistent-name")

    async def test_duplicate_raises_409(self, app_client, engine):
        """check_unique_for_user raises 409 when duplicate exists."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.workflows.models import Workflow

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            user_id = uuid.uuid4()
            # Create a workflow
            wf = Workflow(user_id=user_id, name="dup-test-wf", agent_id="test-agent", prompt_template="test")
            session.add(wf)
            await session.flush()

            # Duplicate — should raise 409
            with pytest.raises(HTTPException) as exc_info:
                await check_unique_for_user(session, Workflow, user_id, "name", "dup-test-wf")
            assert exc_info.value.status_code == 409


@pytest.mark.asyncio
class TestListOwned:
    """Tests for list_owned."""

    async def test_list_owned_empty(self, app_client, engine):
        """list_owned returns empty list when no objects exist."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.workflows.models import Workflow

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            fake_user_id = uuid.uuid4()
            result = await list_owned(session, Workflow, fake_user_id)
            assert result == []

    async def test_list_owned_returns_owned(self, app_client, engine):
        """list_owned returns only objects owned by the user."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.workflows.models import Workflow

        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            user_id = uuid.uuid4()
            wf = Workflow(user_id=user_id, name="owned-wf", agent_id="test-agent", prompt_template="test")
            session.add(wf)
            await session.flush()

            result = await list_owned(session, Workflow, user_id)
            assert len(result) == 1
            assert result[0].name == "owned-wf"
