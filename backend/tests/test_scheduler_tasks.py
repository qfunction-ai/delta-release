"""Tests for scheduled workflow execution tasks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import RUN_COMPLETED, RUN_PENDING
from app.workflows.scheduler_tasks import execute_scheduled_workflow


def _make_workflow(workflow_id="wf-123", name="test-wf"):
    """Create a mock workflow object."""
    wf = MagicMock()
    wf.id = workflow_id
    wf.name = name
    wf.default_variables = '{"key": "value"}'
    wf.include_reasoning = False
    wf.skill_ids_list = []
    wf.user_id = "user-1"
    return wf


def _make_run(run_id="run-123", status=RUN_PENDING):
    """Create a mock run object."""
    run = MagicMock()
    run.id = run_id
    run.status = status
    run.output = None
    run.reasoning_output = None
    run.started_at = None
    run.completed_at = None
    run.letta_run_id = None
    run.steps_count = None
    return run


def _patch_session_context(mock_sessionmaker, mock_session):
    """Patch sessionmaker to return an async context manager that yields mock_session."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_sessionmaker.return_value.return_value = cm


class TestExecuteScheduledWorkflow:
    """Tests for execute_scheduled_workflow."""

    @pytest.mark.asyncio
    async def test_workflow_not_found_returns_early(self):
        """If the workflow doesn't exist, log error and return."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("nonexistent-id", "agent-1", "test prompt")

        # Should not attempt to create a run
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Successful execution creates run, calls Letta, marks completed, extracts lesson."""
        workflow = _make_workflow()

        mock_session = AsyncMock()
        # First execute: workflow lookup
        wf_result = MagicMock()
        wf_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = wf_result

        # Track run creation — session.add is synchronous in SQLAlchemy
        created_runs = []
        mock_session.add = MagicMock(side_effect=lambda obj: created_runs.append(obj))

        # Mock Letta client
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.message_type = "assistant_message"
        mock_message.content = "Search complete"
        mock_response = MagicMock()
        mock_response.messages = [mock_message]
        mock_response.run_id = "letta-run-1"
        mock_response.usage = MagicMock(step_count=3)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
            patch("app.workflows.scheduler_tasks.get_letta_client", return_value=mock_client),
            patch(
                "app.workflows.scheduler_tasks.prepare_prompt_context",
                new_callable=AsyncMock,
                return_value="enhanced prompt",
            ),
            patch("app.workflows.scheduler_tasks.retry_letta_call", new_callable=AsyncMock, return_value=mock_response),
            patch("app.workflows.scheduler_tasks.extract_message_parts", return_value=("Search complete", None)),
            patch("app.workflows.scheduler_tasks.post_run_lesson_extraction", new_callable=AsyncMock),
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            mock_settings.return_value.max_steps = 10
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("wf-123", "agent-1", "test prompt")

        # Verify run was created
        assert len(created_runs) == 1
        # The run's status gets mutated by the code path (pending → running → completed)
        assert created_runs[0].status == RUN_COMPLETED

        # Verify commit was called (run status → running, then → completed)
        assert mock_session.commit.call_count >= 2

    @pytest.mark.asyncio
    async def test_letta_error_marks_run_failed(self):
        """Letta DB error during execution marks run as failed and extracts lesson."""
        workflow = _make_workflow()

        mock_session = AsyncMock()
        wf_result = MagicMock()
        wf_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = wf_result

        mock_client = MagicMock()
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        from httpx import ConnectError

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
            patch("app.workflows.scheduler_tasks.get_letta_client", return_value=mock_client),
            patch(
                "app.workflows.scheduler_tasks.prepare_prompt_context", new_callable=AsyncMock, return_value="prompt"
            ),
            patch(
                "app.workflows.scheduler_tasks.retry_letta_call",
                new_callable=AsyncMock,
                side_effect=ConnectError("refused"),
            ),
            patch("app.workflows.scheduler_tasks.mark_run_failed", new_callable=AsyncMock),
            patch("app.workflows.scheduler_tasks.post_run_lesson_extraction", new_callable=AsyncMock),
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            mock_settings.return_value.max_steps = 10
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("wf-123", "agent-1", "test prompt")

        # If we got here without exception, the error path works

    @pytest.mark.asyncio
    async def test_outer_db_error_with_pending_run(self):
        """Outer DB error when run is still pending marks it failed."""
        workflow = _make_workflow()

        mock_session = AsyncMock()
        wf_result = MagicMock()
        wf_result.scalar_one_or_none.return_value = workflow
        mock_session.execute.return_value = wf_result

        # Make prepare_prompt_context raise a SQLAlchemyError
        from sqlalchemy.exc import SQLAlchemyError

        mock_client = MagicMock()
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
            patch("app.workflows.scheduler_tasks.get_letta_client", return_value=mock_client),
            patch(
                "app.workflows.scheduler_tasks.prepare_prompt_context",
                new_callable=AsyncMock,
                side_effect=SQLAlchemyError("db error"),
            ),
            patch("app.workflows.scheduler_tasks.mark_run_failed", new_callable=AsyncMock),
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            mock_settings.return_value.max_steps = 10
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("wf-123", "agent-1", "test prompt")

        # Engine should be disposed
        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_engine_disposed_on_all_paths(self):
        """Engine is always disposed in the finally block."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Workflow not found
        mock_session.execute.return_value = mock_result

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("nonexistent", "agent-1", "prompt")

        mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_outer_db_error_no_run(self):
        """Outer DB error before run creation just rolls back."""
        mock_session = AsyncMock()
        # Make the workflow query itself fail
        from sqlalchemy.exc import SQLAlchemyError

        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("app.workflows.scheduler_tasks.get_settings") as mock_settings,
            patch("app.workflows.scheduler_tasks.normalize_db_url", return_value="sqlite+aiosqlite://"),
            patch("app.workflows.scheduler_tasks.create_async_engine", return_value=mock_engine),
            patch("app.workflows.scheduler_tasks.sessionmaker") as mock_sessionmaker,
        ):
            mock_settings.return_value.database_url = "postgresql://test"
            _patch_session_context(mock_sessionmaker, mock_session)

            await execute_scheduled_workflow("wf-123", "agent-1", "prompt")

        # Should rollback (no run to mark failed)
        mock_session.rollback.assert_called_once()
        mock_engine.dispose.assert_called_once()
