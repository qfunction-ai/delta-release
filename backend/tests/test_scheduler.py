"""Tests for APScheduler-based workflow scheduling."""

from unittest.mock import MagicMock, patch

import pytest
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.base import ConflictingIdError

from app.scheduler import (
    get_scheduled_workflows,
    get_scheduler,
    schedule_workflow,
    unschedule_workflow,
)


class TestScheduleWorkflow:
    """Tests for schedule_workflow function."""

    @pytest.mark.asyncio
    async def test_schedule_workflow_valid_cron(self):
        """Valid cron expression creates a scheduled job."""
        mock_scheduler = MagicMock()
        mock_scheduler.add_job = MagicMock()

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            await schedule_workflow(
                workflow_id="abc-123",
                cron_expression="0 9 * * *",
                agent_id="agent-1",
                prompt="Run this workflow",
            )

        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "workflow_abc-123"
        assert call_kwargs[1]["replace_existing"] is True
        assert call_kwargs[1]["misfire_grace_time"] == 3600

    @pytest.mark.asyncio
    async def test_schedule_workflow_invalid_cron_too_few_fields(self):
        """Invalid cron expression (too few fields) raises ValueError."""
        mock_scheduler = MagicMock()

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            with pytest.raises(ValueError, match="Invalid cron expression"):
                await schedule_workflow(
                    workflow_id="abc-123",
                    cron_expression="0 9 *",  # Only 3 fields
                    agent_id="agent-1",
                    prompt="Run this workflow",
                )

    @pytest.mark.asyncio
    async def test_schedule_workflow_invalid_cron_too_many_fields(self):
        """Invalid cron expression (too many fields) raises ValueError."""
        mock_scheduler = MagicMock()

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            with pytest.raises(ValueError, match="Invalid cron expression"):
                await schedule_workflow(
                    workflow_id="abc-123",
                    cron_expression="0 9 * * * *",  # 6 fields
                    agent_id="agent-1",
                    prompt="Run this workflow",
                )


class TestUnscheduleWorkflow:
    """Tests for unschedule_workflow function."""

    def test_unschedule_workflow_existing(self):
        """Removing an existing job succeeds."""
        mock_scheduler = MagicMock()
        mock_scheduler.remove_job = MagicMock()

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            unschedule_workflow("abc-123")

        mock_scheduler.remove_job.assert_called_once_with("workflow_abc-123")

    def test_unschedule_workflow_missing(self):
        """JobLookupError is caught and ignored."""
        mock_scheduler = MagicMock()
        mock_scheduler.remove_job = MagicMock(side_effect=JobLookupError("not found"))

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            # Should not raise
            unschedule_workflow("abc-123")

    def test_unschedule_workflow_conflicting_id_raises(self):
        """ConflictingIdError is re-raised."""
        mock_scheduler = MagicMock()
        mock_scheduler.remove_job = MagicMock(side_effect=ConflictingIdError("workflow_abc-123"))

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            with pytest.raises(ConflictingIdError):
                unschedule_workflow("abc-123")


class TestGetScheduledWorkflows:
    """Tests for get_scheduled_workflows function."""

    def test_get_scheduled_workflows(self):
        """Returns list of workflow jobs."""
        mock_scheduler = MagicMock()
        mock_job1 = MagicMock()
        mock_job1.id = "workflow_abc-123"
        mock_job1.next_run_time = MagicMock()
        mock_job1.next_run_time.isoformat.return_value = "2026-05-16T09:00:00"
        mock_job1.trigger = "cron[day='*']"

        mock_job2 = MagicMock()
        mock_job2.id = "workflow_def-456"
        mock_job2.next_run_time = MagicMock()
        mock_job2.next_run_time.isoformat.return_value = "2026-05-16T10:00:00"
        mock_job2.trigger = "cron[day='*']"

        mock_scheduler.get_jobs.return_value = [mock_job1, mock_job2]

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            result = get_scheduled_workflows()

        assert len(result) == 2
        assert result[0]["workflow_id"] == "abc-123"
        assert result[0]["next_run"] == "2026-05-16T09:00:00"
        assert result[1]["workflow_id"] == "def-456"

    def test_get_scheduled_workflows_ignores_non_workflow_jobs(self):
        """Jobs not starting with 'workflow_' are ignored."""
        mock_scheduler = MagicMock()
        mock_job1 = MagicMock()
        mock_job1.id = "workflow_abc-123"
        mock_job1.next_run_time = MagicMock()
        mock_job1.next_run_time.isoformat.return_value = "2026-05-16T09:00:00"
        mock_job1.trigger = "cron"

        mock_job2 = MagicMock()
        mock_job2.id = "other_job"  # Not a workflow job
        mock_job2.next_run_time = MagicMock()
        mock_job2.trigger = "interval"

        mock_scheduler.get_jobs.return_value = [mock_job1, mock_job2]

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            result = get_scheduled_workflows()

        assert len(result) == 1
        assert result[0]["workflow_id"] == "abc-123"

    def test_get_scheduled_workflows_none_next_run(self):
        """Jobs with None next_run_time are handled."""
        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "workflow_abc-123"
        mock_job.next_run_time = None
        mock_job.trigger = "cron"

        mock_scheduler.get_jobs.return_value = [mock_job]

        with patch("app.scheduler.get_scheduler", return_value=mock_scheduler):
            result = get_scheduled_workflows()

        assert len(result) == 1
        assert result[0]["next_run"] is None


class TestGetScheduler:
    """Tests for get_scheduler singleton."""

    def test_get_scheduler_creates_instance(self):
        """get_scheduler creates a scheduler if none exists."""
        import app.scheduler as scheduler_module

        # Reset the global scheduler
        scheduler_module.scheduler = None

        with patch("app.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_instance = MagicMock()
            mock_scheduler_class.return_value = mock_instance

            result = get_scheduler()

            mock_scheduler_class.assert_called_once()
            assert result == mock_instance

    def test_get_scheduler_returns_existing(self):
        """get_scheduler returns existing scheduler if one exists."""
        import app.scheduler as scheduler_module

        # Set a mock scheduler
        mock_scheduler = MagicMock()
        scheduler_module.scheduler = mock_scheduler

        result = get_scheduler()

        assert result == mock_scheduler
