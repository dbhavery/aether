"""Busy detection — infers the user's availability from context signals.

Sources: time of day (learned from daily interview), last activity time,
conversation cadence.
"""

from datetime import datetime, time

from loguru import logger


class BusyDetector:
    """Estimates the user's availability.

    Returns one of: 'available', 'likely_busy', 'sleeping', 'do_not_disturb'
    """

    def __init__(self) -> None:
        # Learned defaults — updated by daily interview sessions
        self._sleep_start: time = time(23, 0)  # 11 PM
        self._sleep_end: time = time(7, 30)  # 7:30 AM
        self._last_activity: datetime | None = None

    def record_activity(self) -> None:
        """Call whenever the user sends a message or speaks."""
        self._last_activity = datetime.now()

    def get_availability(self) -> str:
        now = datetime.now()
        current_time = now.time()

        # Sleeping? Handle both overnight wrap (23:00-07:30) and same-day (01:00-09:00)
        if self._sleep_start > self._sleep_end:
            # Overnight: e.g., 23:00 - 07:30
            if current_time >= self._sleep_start or current_time < self._sleep_end:
                return "sleeping"
        else:
            # Same-day: e.g., 01:00 - 09:00
            if self._sleep_start <= current_time < self._sleep_end:
                return "sleeping"

        # No activity in last 2 hours during the day -> likely busy
        if self._last_activity:
            minutes_since = (now - self._last_activity).total_seconds() / 60
            if minutes_since > 120:
                return "likely_busy"

        return "available"

    def should_notify(self, priority: str = "normal") -> bool:
        """Return True if it's OK to send a proactive notification.

        - 'urgent': always notify
        - 'normal': notify unless sleeping
        - 'low': only notify when available
        """
        availability = self.get_availability()
        if priority == "urgent":
            return True
        if availability == "sleeping":
            return False
        return not (priority == "low" and availability != "available")

    def update_sleep_schedule(self, sleep_hour: int, sleep_minute: int, wake_hour: int, wake_minute: int) -> None:
        """Called when daily interview learns the user's sleep schedule."""
        self._sleep_start = time(sleep_hour, sleep_minute)
        self._sleep_end = time(wake_hour, wake_minute)
        logger.info(
            f"BusyDetector: sleep schedule updated "
            f"{sleep_hour:02d}:{sleep_minute:02d} -> {wake_hour:02d}:{wake_minute:02d}"
        )


_detector = BusyDetector()


def get_busy_detector() -> BusyDetector:
    return _detector


async def _on_user_message(event) -> None:
    """Record activity when user sends a message — subscribed via EventBus."""
    _detector.record_activity()


def register_busy_detector_events() -> None:
    """Subscribe busy detector to USER_MESSAGE events. Called during startup."""
    from src.core.events import event_bus
    from src.shared.types import EventType

    event_bus.subscribe(EventType.USER_MESSAGE, _on_user_message)
