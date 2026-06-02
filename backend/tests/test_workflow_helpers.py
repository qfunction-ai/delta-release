"""Tests for workflow execution helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.constants import RUN_FAILED
from app.workflows.helpers import mark_run_failed, post_run_lesson_extraction


class TestMarkRunFailed:
    """Tests for mark_run_failed."""

    @pytest.mark.asyncio
    async def test_sets_status_to_failed(self):
        """mark_run_failed sets run status to 'failed'."""
        run = MagicMock()
        run.status = "running"

        await mark_run_failed(run, Exception("something broke"))

        assert run.status == RUN_FAILED

    @pytest.mark.asyncio
    async def test_sets_error_message(self):
        """mark_run_failed sets a safe error message."""
        run = MagicMock()
        run.status = "running"

        await mark_run_failed(run, Exception("db connection lost"))

        assert run.error_message is not None
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_sets_completed_at(self):
        """mark_run_failed sets completed_at timestamp."""
        run = MagicMock()
        run.status = "running"
        run.completed_at = None

        await mark_run_failed(run, ValueError("bad"))

        assert run.completed_at is not None


class TestPostRunLessonExtraction:
    """Tests for post_run_lesson_extraction."""

    @pytest.mark.asyncio
    async def test_success_path(self):
        """Calls both extract_and_store_lesson and update_lesson_utility."""
        run = MagicMock()
        workflow = MagicMock()
        db = AsyncMock()

        with (
            patch("app.workflows.helpers.extract_and_store_lesson", new_callable=AsyncMock) as mock_extract,
            patch("app.workflows.helpers.update_lesson_utility", new_callable=AsyncMock) as mock_update,
        ):
            await post_run_lesson_extraction(run, workflow, db)

        mock_extract.assert_called_once_with(run, workflow, db)
        mock_update.assert_called_once_with(workflow, run, db)

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_is_non_fatal(self):
        """SQLAlchemyError during extraction is caught and logged, not raised."""
        run = MagicMock()
        workflow = MagicMock()
        db = AsyncMock()

        with (
            patch(
                "app.workflows.helpers.extract_and_store_lesson",
                new_callable=AsyncMock,
                side_effect=SQLAlchemyError("db error"),
            ),
            patch("app.workflows.helpers.update_lesson_utility", new_callable=AsyncMock),
        ):
            # Should not raise
            await post_run_lesson_extraction(run, workflow, db)

    @pytest.mark.asyncio
    async def test_value_error_is_non_fatal(self):
        """ValueError during extraction is caught and logged, not raised."""
        run = MagicMock()
        workflow = MagicMock()
        db = AsyncMock()

        with (
            patch("app.workflows.helpers.extract_and_store_lesson", new_callable=AsyncMock, return_value=MagicMock()),
            patch(
                "app.workflows.helpers.update_lesson_utility",
                new_callable=AsyncMock,
                side_effect=ValueError("bad data"),
            ),
        ):
            # Should not raise
            await post_run_lesson_extraction(run, workflow, db)
