"""Module 02 tests — verify Voice-In components."""

from importlib.util import find_spec
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

# VAD imports torch (Silero VAD). On environments without torch (base dev
# install without requirements-voice.txt) the VAD class is skipped.
_HAS_TORCH = find_spec("torch") is not None


@pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed; VAD uses Silero VAD")
class TestVAD:
    def test_vad_stream_initializes(self):
        from src.voice.vad import VADStream

        vad = VADStream()
        assert vad.threshold > 0
        assert vad.sample_rate == 16000

    def test_vad_callbacks_fire(self):
        from src.voice.vad import VADStream

        speech_started = []
        speech_ended = []

        vad = VADStream(
            on_speech_start=lambda: speech_started.append(True),
            on_speech_end=lambda audio: speech_ended.append(audio),
        )
        # Simulate speech above threshold (need enough chunks to exceed min_speech_ms=250ms)
        with patch("src.voice.vad.is_speech", return_value=0.9):
            speech_chunk = np.ones(512, dtype=np.float32) * 0.5
            for _ in range(10):  # 10 * 32ms = 320ms > 250ms min_speech_ms
                vad.process_chunk(speech_chunk, 32.0)
            assert len(speech_started) == 1

        # Simulate end of speech (silence)
        with patch("src.voice.vad.is_speech", return_value=0.1):
            silence_chunk = np.zeros(512, dtype=np.float32)
            for _ in range(30):  # enough silence chunks to trigger speech_end
                vad.process_chunk(silence_chunk, 32.0)
            assert len(speech_ended) == 1


class TestSTT:
    @pytest.mark.asyncio
    async def test_transcribe_falls_back_gracefully_when_elevenlabs_opted_in(self):
        """Whisper fails -> ElevenLabs is used, but only when user opted in."""
        with (
            patch("src.voice.stt.transcribe_whisper", new_callable=AsyncMock, return_value=None),
            patch("src.voice.stt.transcribe_elevenlabs", new_callable=AsyncMock, return_value="hello world"),
            patch("src.voice.stt._elevenlabs_enabled", return_value=True),
        ):
            from src.voice.stt import transcribe

            result = await transcribe(np.zeros(16000, dtype=np.float32))
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_transcribe_skips_elevenlabs_when_not_opted_in(self):
        """Local-mode users never hit the cloud, even if whisper returns empty."""
        with (
            patch("src.voice.stt.transcribe_whisper", new_callable=AsyncMock, return_value=None),
            patch("src.voice.stt.transcribe_elevenlabs", new_callable=AsyncMock, return_value="cloud hit"),
            patch("src.voice.stt._elevenlabs_enabled", return_value=False),
        ):
            from src.voice.stt import transcribe

            result = await transcribe(np.zeros(16000, dtype=np.float32))
            assert result is None  # Never tried the cloud path.

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_if_both_fail(self):
        with (
            patch("src.voice.stt.transcribe_whisper", new_callable=AsyncMock, return_value=None),
            patch("src.voice.stt.transcribe_elevenlabs", new_callable=AsyncMock, return_value=None),
            patch("src.voice.stt._elevenlabs_enabled", return_value=True),
        ):
            from src.voice.stt import transcribe

            result = await transcribe(np.zeros(16000, dtype=np.float32))
            assert result is None


class TestCircuitBreaker:
    def test_trips_after_threshold_failures(self):
        from src.voice.stt import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, window_seconds=60.0, cooldown_seconds=1.0)
        assert not cb.is_tripped
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_tripped
        tripped = cb.record_failure()  # 3rd failure — should trip
        assert tripped is True
        assert cb.is_tripped
        assert cb.trip_count == 1

    def test_auto_resets_after_cooldown(self):
        import time

        from src.voice.stt import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=2, window_seconds=60.0, cooldown_seconds=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_tripped
        time.sleep(0.15)  # Wait for cooldown
        assert not cb.is_tripped  # Should auto-reset

    def test_success_clears_failures(self):
        from src.voice.stt import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, window_seconds=60.0, cooldown_seconds=1.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Should clear accumulated failures
        cb.record_failure()
        assert not cb.is_tripped  # Only 1 failure after success clear

    def test_manual_reset(self):
        from src.voice.stt import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=2, window_seconds=60.0, cooldown_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_tripped
        cb.reset()
        assert not cb.is_tripped

    def test_window_based_pruning(self):
        import time

        from src.voice.stt import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, window_seconds=0.1, cooldown_seconds=1.0)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)  # Wait for failures to age out of window
        cb.record_failure()  # Only 1 failure in window now
        assert not cb.is_tripped

    @pytest.mark.asyncio
    async def test_transcribe_returns_none_when_tripped(self):
        """When circuit breaker is tripped, transcribe() returns None immediately."""
        from src.voice.stt import _circuit_breaker

        # Save original state and trip the CB
        original_tripped = _circuit_breaker._tripped
        original_at = _circuit_breaker._tripped_at
        original_cooldown = _circuit_breaker._cooldown_seconds
        try:
            import time

            _circuit_breaker._tripped = True
            _circuit_breaker._tripped_at = time.monotonic()
            _circuit_breaker._cooldown_seconds = 60.0  # Long cooldown so it stays tripped

            from src.voice.stt import transcribe

            result = await transcribe(np.zeros(16000, dtype=np.float32))
            assert result is None
        finally:
            _circuit_breaker._tripped = original_tripped
            _circuit_breaker._tripped_at = original_at
            _circuit_breaker._cooldown_seconds = original_cooldown
