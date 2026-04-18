"""Smoke tests for the voice pipeline — no real audio hardware needed.

Tests verify:
- VoicePipeline.stop() is safe to call when the pipeline was never started.
- TTS handler sends audio chunks to the avatar client for lip sync.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestEchoCanceller:
    """Tests for echo cancellation gate."""

    def test_not_gating_when_idle(self):
        from src.voice.echo_cancel import EchoCanceller

        ec = EchoCanceller(ring_down_ms=200.0)
        assert not ec.should_gate_input
        assert not ec.is_speaking

    def test_gates_during_tts(self):
        from src.voice.echo_cancel import EchoCanceller

        ec = EchoCanceller(ring_down_ms=200.0)
        ec.on_tts_start()
        assert ec.should_gate_input
        assert ec.is_speaking

    def test_gates_during_ring_down(self):
        from src.voice.echo_cancel import EchoCanceller

        ec = EchoCanceller(ring_down_ms=500.0)
        ec.on_tts_start()
        ec.on_tts_stop()
        assert not ec.is_speaking
        assert ec.should_gate_input  # Still in ring-down

    def test_ring_down_expires(self):
        import time

        from src.voice.echo_cancel import EchoCanceller

        ec = EchoCanceller(ring_down_ms=50.0)
        ec.on_tts_start()
        ec.on_tts_stop()
        time.sleep(0.06)  # Wait for ring-down to expire
        assert not ec.should_gate_input


class TestVoicePipelineStop:
    """Verify stop() is safe even when the pipeline was never started."""

    def test_pipeline_stop_is_safe_when_not_started(self):
        """Calling stop_voice_pipeline() when no pipeline exists should not raise."""
        with patch("src.voice.pipeline.get_yaml_config") as mock_yaml:
            mock_yaml.return_value = {
                "audio": {
                    "sample_rate": 16000,
                    "chunk_size": 512,
                    "input_device": None,
                    "vad_max_silence_ms": 800,
                },
                "voice": {
                    "barge_in_enabled": True,
                    "barge_in_delay_ms": 300,
                    "echo_cancel_ring_down_ms": 200,
                },
            }
            from src.voice.pipeline import stop_voice_pipeline

            # Should not raise even though start was never called
            stop_voice_pipeline()


class TestSilenceDetector:
    """Tests for the context-aware silence detector."""

    def test_base_threshold_when_no_transcript(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        assert det.get_effective_silence_ms(None) == 800.0
        assert det.get_effective_silence_ms("") == 800.0

    def test_continuation_word_extends_threshold(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        # "and" is a continuation word → 1.5x
        effective = det.get_effective_silence_ms("I was thinking and")
        assert effective == 1200.0

    def test_mid_sentence_extends_threshold(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        # No sentence-ending punctuation → 1.2x
        effective = det.get_effective_silence_ms("I was thinking about the")
        assert effective == 960.0

    def test_complete_sentence_uses_base(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        # Ends with period → base threshold
        effective = det.get_effective_silence_ms("That sounds good.")
        assert effective == 800.0

    def test_question_mark_uses_base(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        effective = det.get_effective_silence_ms("What do you think?")
        assert effective == 800.0

    def test_spanish_continuation_words(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        effective = det.get_effective_silence_ms("estaba pensando pero")
        assert effective == 1200.0  # "pero" = "but"

    def test_analyze_context_returns_details(self):
        from src.voice.silence_detector import ContextAwareSilenceDetector

        det = ContextAwareSilenceDetector(base_silence_ms=800.0)
        result = det.analyze_context("I was thinking but")
        assert result["reason"] == "continuation_word"
        assert result["last_word"] == "but"
        assert result["multiplier"] == 1.5


class TestHealthWatchdog:
    """Tests for the pipeline health watchdog."""

    def test_watchdog_task_created_on_start(self):
        """Verify that the watchdog constants and tracking fields exist on VoicePipeline."""
        with patch("src.voice.pipeline.get_yaml_config") as mock_yaml:
            mock_yaml.return_value = {
                "audio": {
                    "sample_rate": 16000,
                    "chunk_size": 512,
                    "input_device": None,
                    "vad_max_silence_ms": 800,
                },
                "voice": {
                    "barge_in_enabled": True,
                    "barge_in_delay_ms": 300,
                    "echo_cancel_ring_down_ms": 200,
                },
            }
            from src.voice.pipeline import VoicePipeline

            pipeline = VoicePipeline()
            assert pipeline._WATCHDOG_INTERVAL == 15.0
            assert pipeline._CB_TRIP_RESET_THRESHOLD == 3
            assert pipeline._AUDIO_STARVATION_TIMEOUT == 300.0
            assert pipeline._consecutive_cb_trips == 0
            assert pipeline._watchdog_task is None

    def test_stop_cancels_watchdog(self):
        """Verify stop() cancels the watchdog task."""
        with patch("src.voice.pipeline.get_yaml_config") as mock_yaml:
            mock_yaml.return_value = {
                "audio": {
                    "sample_rate": 16000,
                    "chunk_size": 512,
                    "input_device": None,
                    "vad_max_silence_ms": 800,
                },
                "voice": {
                    "barge_in_enabled": True,
                    "barge_in_delay_ms": 300,
                    "echo_cancel_ring_down_ms": 200,
                },
            }
            from src.voice.pipeline import VoicePipeline

            pipeline = VoicePipeline()
            # Simulate a running watchdog task
            mock_task = MagicMock()
            mock_task.done.return_value = False
            pipeline._watchdog_task = mock_task
            pipeline.stop()
            mock_task.cancel.assert_called_once()


class TestTTSHandlerAvatarSync:
    """Verify the TTS handler sends audio chunks to the avatar for lip sync."""

    @pytest.mark.asyncio
    async def test_tts_handler_sends_audio_to_avatar(self):
        """Mock synthesize to return audio, mock avatar client, verify send_audio_chunk is called."""
        sample_rate = 16000
        # 0.2 seconds of audio at 16kHz — enough for at least 1 lip-sync chunk (100ms)
        audio = np.zeros(int(sample_rate * 0.2), dtype=np.float32)

        mock_client = MagicMock()
        mock_client.available = True
        mock_client.send_audio_chunk = AsyncMock()
        mock_client.set_speaking = AsyncMock()

        with (
            patch(
                "src.voice.tts_handler.synthesize",
                new_callable=AsyncMock,
                return_value=(audio, sample_rate),
            ),
            patch(
                "src.voice.tts_handler.play_audio",
                new_callable=AsyncMock,
            ),
            patch("src.avatar.client.get_avatar_client", return_value=mock_client),
        ):
            from src.shared.types import AetherEvent, EventType
            from src.voice.tts_handler import on_response_text_ready

            event = AetherEvent(
                type=EventType.RESPONSE_TEXT_READY,
                data={"text": "Hello User", "is_interim": False, "mode": "voice"},
                source_module="test",
            )
            await on_response_text_ready(event)

            # send_audio_chunk should have been called at least once
            # (0.2s audio / 0.1s chunk = 2 chunks)
            assert mock_client.send_audio_chunk.call_count >= 1, (
                f"Expected send_audio_chunk to be called at least once, got {mock_client.send_audio_chunk.call_count}"
            )

    @pytest.mark.asyncio
    async def test_tts_handler_skips_avatar_when_unavailable(self):
        """When avatar client is not available, send_audio_chunk should not be called."""
        sample_rate = 16000
        audio = np.zeros(int(sample_rate * 0.2), dtype=np.float32)

        mock_client = MagicMock()
        mock_client.available = False
        mock_client.send_audio_chunk = AsyncMock()
        mock_client.set_speaking = AsyncMock()

        with (
            patch(
                "src.voice.tts_handler.synthesize",
                new_callable=AsyncMock,
                return_value=(audio, sample_rate),
            ),
            patch(
                "src.voice.tts_handler.play_audio",
                new_callable=AsyncMock,
            ),
            patch("src.avatar.client.get_avatar_client", return_value=mock_client),
        ):
            from src.shared.types import AetherEvent, EventType
            from src.voice.tts_handler import on_response_text_ready

            event = AetherEvent(
                type=EventType.RESPONSE_TEXT_READY,
                data={"text": "Hello User", "is_interim": False, "mode": "voice"},
                source_module="test",
            )
            await on_response_text_ready(event)

            # Avatar is unavailable so send_audio_chunk should NOT be called
            mock_client.send_audio_chunk.assert_not_called()
