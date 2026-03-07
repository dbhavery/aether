"""Speech-to-text — ElevenLabs Scribe v2 Realtime (primary) + faster-whisper (fallback).

Includes CircuitBreaker to prevent STT buffer overflow zombies (v13 lesson).
"""

import asyncio
import io
import threading
import time

import numpy as np
import soundfile as sf
from loguru import logger

from src.shared.config import get_settings


class CircuitBreaker:
    """Trips after N failures within a time window. Auto-resets after cooldown.

    Prevents the STT system from becoming a zombie when the audio pipeline
    floods with unprocessable frames (v13 incident: 14,490 warnings, process
    alive but unresponsive for 5 days).
    """

    def __init__(
        self,
        failure_threshold: int = 10,
        window_seconds: float = 30.0,
        cooldown_seconds: float = 10.0,
    ):
        self._failure_threshold = failure_threshold
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._failure_times: list[float] = []
        self._tripped = False
        self._tripped_at: float = 0.0
        self._trip_count: int = 0
        self._lock = threading.Lock()

    @property
    def is_tripped(self) -> bool:
        """Check if circuit breaker is currently tripped (with auto-reset)."""
        with self._lock:
            if self._tripped:
                elapsed = time.monotonic() - self._tripped_at
                if elapsed >= self._cooldown_seconds:
                    self._tripped = False
                    self._failure_times.clear()
                    logger.info(f"CircuitBreaker: auto-reset after {self._cooldown_seconds}s cooldown")
            return self._tripped

    @property
    def trip_count(self) -> int:
        """Total number of times the circuit breaker has tripped."""
        return self._trip_count

    def record_failure(self) -> bool:
        """Record a failure. Returns True if the circuit breaker just tripped."""
        with self._lock:
            now = time.monotonic()
            # Prune old failures outside the window
            cutoff = now - self._window_seconds
            self._failure_times = [t for t in self._failure_times if t > cutoff]
            self._failure_times.append(now)

            if len(self._failure_times) >= self._failure_threshold:
                self._tripped = True
                self._tripped_at = now
                self._trip_count += 1
                self._failure_times.clear()
                logger.warning(
                    f"CircuitBreaker: TRIPPED (trip #{self._trip_count}) — "
                    f"{self._failure_threshold} failures in {self._window_seconds}s. "
                    f"Pausing for {self._cooldown_seconds}s."
                )
                return True
            return False

    def record_success(self) -> None:
        """Record a success. Clears accumulated failures."""
        with self._lock:
            self._failure_times.clear()

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._tripped = False
            self._failure_times.clear()
            logger.info("CircuitBreaker: manually reset")


# Module-level circuit breaker — shared across all STT calls
_circuit_breaker = CircuitBreaker(
    failure_threshold=10,
    window_seconds=30.0,
    cooldown_seconds=10.0,
)


def get_circuit_breaker() -> CircuitBreaker:
    """Get the module-level STT circuit breaker (for monitoring)."""
    return _circuit_breaker


_elevenlabs_stt_client = None
_elevenlabs_stt_lock = threading.Lock()


def _get_elevenlabs_stt_client():
    """Return the module-level ElevenLabs client singleton for STT."""
    global _elevenlabs_stt_client
    if _elevenlabs_stt_client is None:
        with _elevenlabs_stt_lock:
            if _elevenlabs_stt_client is None:
                from elevenlabs.client import ElevenLabs

                settings = get_settings()
                if not settings.elevenlabs_api_key:
                    raise RuntimeError("ELEVENLABS_API_KEY not set")
                _elevenlabs_stt_client = ElevenLabs(api_key=settings.elevenlabs_api_key)
                logger.debug("STT: ElevenLabs client singleton created")
    return _elevenlabs_stt_client


async def transcribe_elevenlabs(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe audio using ElevenLabs Scribe v2 Realtime. Returns text or None on failure."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        logger.warning("STT: ELEVENLABS_API_KEY not set — skipping ElevenLabs STT")
        return None
    try:
        client = _get_elevenlabs_stt_client()

        # Convert numpy array to WAV bytes
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        buf.seek(0)

        response = await asyncio.to_thread(
            client.speech_to_text.convert,
            file=buf,
            model_id="scribe_v2",
            language_code="en",
        )
        text = response.text.strip()
        logger.info(f"STT (ElevenLabs): '{text[:80]}'")
        return text if text else None
    except Exception as e:
        logger.warning(f"STT: ElevenLabs failed ({e}), will fall back to Whisper")
        return None


_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                logger.info("STT: Loading faster-whisper distil-large-v3 (CUDA)...")
                try:
                    _whisper_model = WhisperModel(
                        "distil-large-v3",
                        device="cuda",
                        compute_type="float16",
                    )
                except Exception as e:
                    logger.warning(f"STT: distil-large-v3 unavailable ({e}), trying base.en")
                    _whisper_model = WhisperModel(
                        "base.en",
                        device="cuda",
                        compute_type="float16",
                    )
                logger.info("STT: faster-whisper ready")
    return _whisper_model


async def transcribe_whisper(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe audio using faster-whisper. Local fallback — no API required."""
    try:
        # Load model in thread to avoid blocking event loop on first call (~5-10s)
        model = await asyncio.to_thread(_get_whisper_model)

        def _transcribe_and_collect():
            """Run transcription AND consume the generator in the worker thread.

            faster-whisper returns a lazy generator — iterating it on the event
            loop would block. Consume it here so all computation stays off-loop.
            """
            segments, info = model.transcribe(
                audio.astype(np.float32),
                language="en",
                beam_size=5,
            )
            text = " ".join(seg.text for seg in segments).strip()
            return text, info

        text, info = await asyncio.to_thread(_transcribe_and_collect)
        logger.info(f"STT (Whisper): '{text[:80]}' (lang={info.language}, conf={info.language_probability:.2f})")
        return text if text else None
    except Exception as e:
        logger.error(f"STT: Whisper failed: {e}")
        return None


async def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe with ElevenLabs primary, Whisper fallback. Guarded by circuit breaker."""
    if _circuit_breaker.is_tripped:
        logger.debug("STT: circuit breaker tripped — dropping audio frame")
        return None

    # Graduated buffer duration warnings
    duration = len(audio) / sample_rate
    if duration > 45:
        logger.warning(f"STT: audio buffer extremely long ({duration:.1f}s) — possible overflow")
    elif duration > 30:
        logger.warning(f"STT: audio buffer long ({duration:.1f}s) — check audio pipeline")

    text = await transcribe_elevenlabs(audio, sample_rate)
    if text:
        _circuit_breaker.record_success()
        return text

    logger.info("STT: Falling back to faster-whisper")
    text = await transcribe_whisper(audio, sample_rate)
    if text:
        _circuit_breaker.record_success()
        return text

    # Both engines failed
    _circuit_breaker.record_failure()
    return None
