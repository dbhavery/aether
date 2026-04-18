"""Smoke tests for the voice pipeline — no real audio hardware needed.

Tests verify:
- VoicePipeline.stop() is safe to call when the pipeline was never started.
- TTS handler sends audio chunks to the avatar client for lip sync.
"""

from unittest.mock import patch


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


# TestHealthWatchdog and TestTTSHandlerAvatarSync were pre-v1.0 — the
# watchdog, avatar lip-sync bridge, and VoicePipeline class itself were
# rewritten for push-to-talk in Agent 2's voice pipeline overhaul. The
# replacement module is src.voice.pipeline (module-level start/stop
# functions, no VoicePipeline class), and avatar lip-sync now flows via
# AVATAR_AUDIO_CHUNK events not a direct client call. No test coverage of
# the new shape has been written yet.
