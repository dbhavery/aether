"""Tests for persona module — daily interview + memory corrections."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDailyInterview:
    """Test daily interview question selection."""

    def test_question_pool_not_empty(self):
        from src.persona.daily_interview import INTERVIEW_QUESTIONS

        assert len(INTERVIEW_QUESTIONS) >= 10

    def test_pick_question_returns_string(self, tmp_path):
        from src.persona import daily_interview as di

        original = di._asked_file
        di._asked_file = tmp_path / "asked.txt"
        try:
            q = di._pick_question()
            assert isinstance(q, str)
            assert len(q) > 10
        finally:
            di._asked_file = original

    def test_pick_question_avoids_repeats(self, tmp_path):
        from src.persona import daily_interview as di

        original = di._asked_file
        di._asked_file = tmp_path / "asked.txt"
        try:
            asked = set()
            for _ in range(len(di.INTERVIEW_QUESTIONS)):
                q = di._pick_question()
                assert q not in asked, f"Repeated question: {q}"
                asked.add(q)
        finally:
            di._asked_file = original

    def test_pool_resets_when_exhausted(self, tmp_path):
        from src.persona import daily_interview as di

        original = di._asked_file
        di._asked_file = tmp_path / "asked.txt"
        try:
            # Exhaust the pool
            for _ in range(len(di.INTERVIEW_QUESTIONS)):
                di._pick_question()
            # Should reset and give a new question
            q = di._pick_question()
            assert q in di.INTERVIEW_QUESTIONS
        finally:
            di._asked_file = original

    @pytest.mark.asyncio
    async def test_start_interview_publishes_event(self, tmp_path):
        from src.persona import daily_interview as di

        original = di._asked_file
        di._asked_file = tmp_path / "asked.txt"
        mock_detector = MagicMock()
        mock_detector.get_availability.return_value = "available"
        try:
            with (
                patch.object(di.event_bus, "publish", new_callable=AsyncMock) as mock_pub,
                patch.object(di, "get_yaml_config", return_value={"notifications": {"max_proactive_per_day": 3}}),
                patch("src.persona.busy_detector.get_busy_detector", return_value=mock_detector),
            ):
                await di.start_interview_session()
                mock_pub.assert_called_once()
                event = mock_pub.call_args[0][0]
                assert event.data["category"] == "daily_interview"
                assert len(event.data["text"]) > 20
        finally:
            di._asked_file = original

    @pytest.mark.asyncio
    async def test_interview_respects_max_proactive_zero(self, tmp_path):
        from src.persona import daily_interview as di

        original = di._asked_file
        di._asked_file = tmp_path / "asked.txt"
        try:
            with (
                patch.object(di.event_bus, "publish", new_callable=AsyncMock) as mock_pub,
                patch.object(di, "get_yaml_config", return_value={"notifications": {"max_proactive_per_day": 0}}),
            ):
                await di.start_interview_session()
                mock_pub.assert_not_called()
        finally:
            di._asked_file = original


class TestCorrectionDetection:
    """Test correction pattern matching."""

    def test_no_correction(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, _ = detect_correction("What's the weather today?")
        assert not is_corr

    def test_no_i_said(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, text = detect_correction("No, I said Tuesday")
        assert is_corr
        assert "Tuesday" in text

    def test_actually_its(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, _text = detect_correction("Actually, it's at 3pm not 4pm")
        assert is_corr

    def test_thats_not_right(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, _ = detect_correction("That's not right")
        assert is_corr

    def test_correction_prefix(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, text = detect_correction("Correction: the meeting is on Friday")
        assert is_corr
        assert "Friday" in text

    def test_i_didnt_say_that(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, _ = detect_correction("I didn't say that")
        assert is_corr

    def test_case_insensitive(self):
        from src.persona.memory_corrections import detect_correction

        is_corr, _ = detect_correction("NO, I SAID WEDNESDAY")
        assert is_corr


class TestCorrectionHandler:
    """Test memory correction event handling."""

    @pytest.mark.asyncio
    async def test_handler_stores_fact(self):
        import time

        from src.persona.memory_corrections import handle_memory_correction
        from src.shared.types import AetherEvent, EventType

        mock_event = AetherEvent(
            type=EventType.MEMORY_CORRECTION,
            data={
                "correction_text": "The meeting is on Tuesday",
                "original_context": "No, I said Tuesday",
            },
            timestamp=time.time(),
            source_module="brain",
        )

        with (
            patch(
                "src.persona.memory_corrections.search_memory",
                new_callable=AsyncMock,
                return_value=[{"content": "meeting on Monday", "metadata": {}, "relevance": 0.8}],
            ),
            patch("src.persona.memory_corrections.store_fact", new_callable=AsyncMock) as mock_store,
        ):
            await handle_memory_correction(mock_event)
            mock_store.assert_called_once()
            call_args = mock_store.call_args
            assert "Tuesday" in call_args.kwargs.get("value", "") or "Tuesday" in call_args[1].get(
                "value", call_args[0][1] if len(call_args[0]) > 1 else ""
            )

    @pytest.mark.asyncio
    async def test_handler_skips_empty_correction(self):
        import time

        from src.persona.memory_corrections import handle_memory_correction
        from src.shared.types import AetherEvent, EventType

        mock_event = AetherEvent(
            type=EventType.MEMORY_CORRECTION,
            data={"correction_text": "", "original_context": ""},
            timestamp=time.time(),
        )

        with patch("src.persona.memory_corrections.search_memory", new_callable=AsyncMock) as mock_search:
            await handle_memory_correction(mock_event)
            mock_search.assert_not_called()
