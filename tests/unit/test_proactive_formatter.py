"""Tests for Batch 13 — proactive scheduler, auto-sleep, response formatter."""

import pytest

from src.brain.response_formatter import format_for_mode
from src.persona.proactive import ProactiveScheduler, get_proactive_scheduler
from src.shared.types import InteractionMode


class TestResponseFormatter:
    def test_text_mode_unchanged(self):
        text = "## Header\n- bullet point\n**bold text**"
        result = format_for_mode(text, InteractionMode.TEXT)
        assert result == text

    def test_voice_strips_bold(self):
        text = "This is **important** text"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "**" not in result
        assert "important" in result

    def test_voice_strips_headers(self):
        text = "## My Header\nSome content"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "#" not in result
        assert "My Header" in result

    def test_voice_strips_code_blocks(self):
        text = "Here's the code:\n```python\nprint('hello')\n```\nDone."
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "```" not in result

    def test_voice_strips_inline_code(self):
        text = "Use `pip install` to install it"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "`" not in result
        assert "pip install" in result

    def test_voice_strips_bullets(self):
        text = "Things to do:\n- Item one\n- Item two\n- Item three"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "- " not in result

    def test_voice_strips_links(self):
        text = "Check out [this site](https://example.com) for more"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "[" not in result
        assert "(" not in result
        assert "this site" in result

    def test_voice_strips_stage_directions(self):
        text = "*smiles* That's a good point. *thinks for a moment*"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "*smiles*" not in result
        assert "*thinks for a moment*" not in result
        assert "good point" in result

    def test_voice_strips_italic(self):
        text = "This is *really* important"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "*" not in result

    def test_voice_strips_numbered_lists(self):
        text = "Steps:\n1. First thing\n2. Second thing"
        result = format_for_mode(text, InteractionMode.VOICE)
        assert "1." not in result

    def test_video_mode_same_as_voice(self):
        text = "## Header\n**bold**"
        voice_result = format_for_mode(text, InteractionMode.VOICE)
        video_result = format_for_mode(text, InteractionMode.VIDEO)
        assert voice_result == video_result


class TestProactiveScheduler:
    def test_scheduler_creation(self):
        sched = ProactiveScheduler()
        assert sched._max_per_day == 3

    def test_can_send_initially(self):
        sched = ProactiveScheduler()
        assert sched.can_send() is True

    def test_rate_limiting(self):
        sched = ProactiveScheduler()
        sched._today_count = 3
        sched._last_reset_date = "2026-03-05"
        # Force same date to prevent reset
        import datetime as dt

        sched._last_reset_date = dt.datetime.now().strftime("%Y-%m-%d")
        assert sched.can_send() is False

    @pytest.mark.asyncio
    async def test_send_notification_increments_count(self):
        from unittest.mock import AsyncMock, patch

        sched = ProactiveScheduler()
        with patch.object(sched, "can_send", return_value=True), patch("src.persona.proactive.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await sched.send_notification("Test notification")
            assert result is True
            assert sched._today_count == 1

    @pytest.mark.asyncio
    async def test_send_notification_rate_limited(self):
        sched = ProactiveScheduler()
        # Exhaust the limit
        import datetime as dt

        sched._today_count = 3
        sched._last_reset_date = dt.datetime.now().strftime("%Y-%m-%d")
        result = await sched.send_notification("Should not send")
        assert result is False

    def test_parse_time(self):
        t = ProactiveScheduler._parse_time("14:30")
        assert t.hour == 14
        assert t.minute == 30

    def test_parse_time_invalid(self):
        t = ProactiveScheduler._parse_time("invalid")
        assert t.hour == 8  # Fallback

    def test_singleton(self):
        s1 = get_proactive_scheduler()
        s2 = get_proactive_scheduler()
        assert s1 is s2

    def test_daily_reset(self):
        sched = ProactiveScheduler()
        sched._today_count = 5
        sched._last_reset_date = "2020-01-01"  # Old date
        assert sched.can_send() is True  # Should reset
        assert sched._today_count == 0


class TestAutoSleepConfig:
    def test_auto_sleep_in_config(self):
        from src.shared.config import get_yaml_config

        config = get_yaml_config()
        voice_config = config.get("voice", {})
        assert "auto_sleep_minutes" in voice_config
        assert voice_config["auto_sleep_minutes"] == 10
