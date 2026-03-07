"""Tests for busy detection."""

from datetime import datetime, time, timedelta
from unittest.mock import patch

from src.persona.busy_detector import BusyDetector


def _make_daytime(hour: int = 14, minute: int = 0) -> datetime:
    """Return a datetime at the given hour today, defaulting to 2 PM (daytime)."""
    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_available_during_day():
    d = BusyDetector()
    d._sleep_start = time(23, 0)
    d._sleep_end = time(7, 30)
    # Force daytime (14:00) so test doesn't depend on when it runs
    fixed_now = _make_daytime(14, 0)
    d._last_activity = fixed_now
    with patch("src.persona.busy_detector.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        avail = d.get_availability()
    assert avail == "available"


def test_sleeping_detection():
    d = BusyDetector()
    d._sleep_start = time(0, 0)  # Always sleeping (start=0:00)
    d._sleep_end = time(23, 59)  # End at 23:59
    assert d.get_availability() == "sleeping"


def test_likely_busy_after_long_inactivity():
    d = BusyDetector()
    d._sleep_start = time(23, 0)
    d._sleep_end = time(7, 30)
    # Force daytime (14:00) with last activity 3 hours ago
    fixed_now = _make_daytime(14, 0)
    d._last_activity = fixed_now - timedelta(hours=3)
    with patch("src.persona.busy_detector.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        avail = d.get_availability()
    assert avail == "likely_busy"


def test_record_activity_updates():
    d = BusyDetector()
    assert d._last_activity is None
    d.record_activity()
    assert d._last_activity is not None


def test_should_notify_urgent_always():
    d = BusyDetector()
    d._sleep_start = time(0, 0)
    d._sleep_end = time(23, 59)
    assert d.should_notify("urgent") is True


def test_should_notify_normal_not_sleeping():
    d = BusyDetector()
    d._sleep_start = time(0, 0)
    d._sleep_end = time(23, 59)
    assert d.should_notify("normal") is False


def test_update_sleep_schedule():
    d = BusyDetector()
    d.update_sleep_schedule(22, 0, 6, 0)
    assert d._sleep_start == time(22, 0)
    assert d._sleep_end == time(6, 0)
