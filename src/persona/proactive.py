"""Proactive scheduler — text notifications only. Aether NEVER speaks first on voice.

Morning briefing, evening check-in, agent task completions.
All proactive events appear as silent text notifications the user taps to read.
"""

import asyncio
from datetime import datetime, time

from loguru import logger

from src.core.events import event_bus
from src.shared.config import get_yaml_config
from src.shared.types import EventType, AetherEvent

# Default schedule
_DEFAULT_MORNING_TIME = "08:00"
_DEFAULT_EVENING_TIME = "21:00"
_DEFAULT_MAX_PER_DAY = 3


class ProactiveScheduler:
    """Schedules proactive text notifications. Never voice-first."""

    def __init__(self) -> None:
        config = get_yaml_config()
        notif_config = config.get("notifications", {})

        self._morning_time = self._parse_time(notif_config.get("daily_briefing_time", _DEFAULT_MORNING_TIME))
        self._evening_time = self._parse_time(notif_config.get("evening_time", _DEFAULT_EVENING_TIME))
        self._max_per_day = notif_config.get("max_proactive_per_day", _DEFAULT_MAX_PER_DAY)
        self._today_count = 0
        self._last_reset_date: str = ""
        self._running = False
        self._task: asyncio.Task | None = None

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse HH:MM string to time object."""
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return time(8, 0)

    def _reset_daily_count(self) -> None:
        """Reset notification count at start of new day."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._today_count = 0
            self._last_reset_date = today

    def can_send(self) -> bool:
        """Check if we can send another proactive notification today."""
        self._reset_daily_count()
        return self._today_count < self._max_per_day

    async def send_notification(self, text: str, category: str = "proactive") -> bool:
        """Send a text-only proactive notification via EventBus.

        Returns True if sent, False if rate-limited.
        """
        if not self.can_send():
            logger.info(f"Proactive: rate limited ({self._today_count}/{self._max_per_day} today)")
            return False

        self._today_count += 1
        logger.info(f"Proactive: sending notification ({self._today_count}/{self._max_per_day}): {text[:60]}")

        await event_bus.publish(
            AetherEvent(
                type=EventType.NOTIFICATION_REQUEST,
                data={
                    "title": "Aether",
                    "message": text,
                    "category": category,
                    "is_proactive": True,
                    "timestamp": datetime.now().isoformat(),
                },
                source_module="proactive",
            )
        )
        return True

    def start(self) -> None:
        """Start the proactive scheduler background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("Proactive: scheduler started")

    def stop(self) -> None:
        """Stop the proactive scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Proactive: scheduler stopped")

    @staticmethod
    def _in_time_window(current: time, start: time, end: time) -> bool:
        """Check if current time is in [start, end) window, handling midnight wrap."""
        if start <= end:
            return start <= current < end
        # Wraps midnight: e.g., 23:00-00:00
        return current >= start or current < end

    async def _schedule_loop(self) -> None:
        """Background loop that checks for scheduled notifications."""
        morning_sent_date: str = ""
        evening_sent_date: str = ""

        while self._running:
            try:
                now = datetime.now()
                current_time = now.time()
                today = now.strftime("%Y-%m-%d")

                # Morning briefing (date-based tracking, no midnight window needed)
                morning_end = time((self._morning_time.hour + 1) % 24, 0)
                if morning_sent_date != today and self._in_time_window(current_time, self._morning_time, morning_end):
                    morning_sent_date = today
                    await self.send_notification(
                        f"Good morning. {today}.",
                        category="morning_briefing",
                    )

                # Evening check-in
                evening_end = time((self._evening_time.hour + 1) % 24, 0)
                if evening_sent_date != today and self._in_time_window(current_time, self._evening_time, evening_end):
                    evening_sent_date = today
                    await self.send_notification(
                        "Wrapping up for the day?",
                        category="evening_checkin",
                    )

                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Proactive: schedule loop error: {e}")
                await asyncio.sleep(60)


# Module singleton
_scheduler: ProactiveScheduler | None = None


def get_proactive_scheduler() -> ProactiveScheduler:
    """Get or create the ProactiveScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ProactiveScheduler()
    return _scheduler
