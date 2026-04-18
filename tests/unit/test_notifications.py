"""Module 12 tests — verify notifications and scheduler."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestScheduler:
    def test_scheduler_initializes(self):
        from src.notifications.scheduler import get_scheduler

        scheduler = get_scheduler()
        assert scheduler is not None

    def test_default_jobs_registered(self):
        from src.notifications.scheduler import get_scheduler, setup_default_jobs

        scheduler = get_scheduler()
        setup_default_jobs()
        assert scheduler.get_job("daily_briefing") is not None
        assert scheduler.get_job("weekly_digest") is not None

    @pytest.mark.asyncio
    async def test_schedule_reminder_returns_job_id(self):
        from src.notifications.scheduler import schedule_reminder

        run_at = datetime.now() + timedelta(hours=1)
        with patch("src.notifications.scheduler.get_scheduler") as mock_sched:
            mock_sched.return_value.add_job = MagicMock()
            mock_sched.return_value.get_job = MagicMock(return_value=None)
            job_id = await schedule_reminder("call John", run_at)
            assert "reminder_" in job_id


class TestWindowsNotify:
    @pytest.mark.asyncio
    async def test_notification_does_not_raise_on_error(self):
        from src.notifications.windows_notify import show_notification

        with patch(
            "src.notifications.windows_notify.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=Exception("no winotify"),
        ):
            # Should not raise — errors are caught and logged
            await show_notification("Test", "test message")


class TestFCM:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_service_account(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch("src.notifications.fcm_notify._get_fcm_service_account_path", return_value=mock_path):
            # Reset initialization state
            import src.notifications.fcm_notify as fcm_mod

            fcm_mod._fcm_initialized = False
            result = await fcm_mod.send_push_notification("Test", "message")
            assert result is False


class TestHandler:
    @pytest.mark.asyncio
    async def test_handler_calls_windows_notify(self):
        from src.notifications.handler import on_notification_request
        from src.shared.types import AetherEvent, EventType

        mock_detector = MagicMock()
        mock_detector.should_notify.return_value = True
        with (
            patch("src.notifications.handler.show_notification", new_callable=AsyncMock) as mock_show,
            patch("src.notifications.handler.send_push_notification", new_callable=AsyncMock, return_value=False),
            patch("src.notifications.handler.get_busy_detector", return_value=mock_detector),
        ):
            event = AetherEvent(
                type=EventType.NOTIFICATION_REQUEST,
                data={"title": "Test", "message": "hello"},
                source_module="test",
            )
            await on_notification_request(event)
            mock_show.assert_called_once_with("Test", "hello")

    @pytest.mark.asyncio
    async def test_handler_skips_empty_message(self):
        from src.notifications.handler import on_notification_request
        from src.shared.types import AetherEvent, EventType

        with patch("src.notifications.handler.show_notification", new_callable=AsyncMock) as mock_show:
            event = AetherEvent(
                type=EventType.NOTIFICATION_REQUEST,
                data={"title": "Test", "message": ""},
                source_module="test",
            )
            await on_notification_request(event)
            mock_show.assert_not_called()
