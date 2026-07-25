"""Speech-to-text — faster-whisper local (primary) + optional ElevenLabs fallback.

v1.0 defaults to local STT via faster-whisper. The model comes from
``config.voice.stt_model``:

- ``"faster-whisper-base.en"`` (default): tiny English-only, CPU-friendly.
- ``"faster-whisper-distil-large-v3"``: GPU + 6 GB+ VRAM recommended.

Unknown names pass through unchanged so advanced users can pick any model
name recognized by the faster-whisper loader.

ElevenLabs Scribe is attempted only when BOTH:

  1. ``config.voice.mode == "elevenlabs"`` (user opted in during onboarding), and
  2. An ``elevenlabs`` API key resolves via the OS keyring (or env-var fallback).

A CircuitBreaker guards against STT zombies caused by an audio pipeline
flooding with unprocessable frames: ten failures in 30 s triggers a 10 s
cooldown during which ``transcribe`` short-circuits to ``None``.
"""

from __future__ import annotations

import asyncio
import io
import threading
import time
from typing import Any

import numpy as np
import soundfile as sf
from loguru import logger

# ---------------------------------------------------------------------------
# Circuit breaker — retained from upstream; prevents zombie STT spins.
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Trips after ``failure_threshold`` failures within ``window_seconds``.

    Auto-resets after ``cooldown_seconds``. Thread-safe: the audio callback
    thread and the asyncio event-loop both call ``is_tripped`` and the
    ``record_*`` methods.
    """

    def __init__(
        self,
        failure_threshold: int = 10,
        window_seconds: float = 30.0,
        cooldown_seconds: float = 10.0,
    ) -> None:
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
        with self._lock:
            if self._tripped:
                elapsed = time.monotonic() - self._tripped_at
                if elapsed >= self._cooldown_seconds:
                    self._tripped = False
                    self._failure_times.clear()
                    logger.info(
                        f"CircuitBreaker: auto-reset after {self._cooldown_seconds}s cooldown"
                    )
            return self._tripped

    @property
    def trip_count(self) -> int:
        return self._trip_count

    def record_failure(self) -> bool:
        """Record a failure. Returns True if this call crossed the trip threshold."""
        with self._lock:
            now = time.monotonic()
            cutoff = now - self._window_seconds
            self._failure_times = [t for t in self._failure_times if t > cutoff]
            self._failure_times.append(now)
            if len(self._failure_times) >= self._failure_threshold:
                self._tripped = True
                self._tripped_at = now
                self._trip_count += 1
                self._failure_times.clear()
                logger.warning(
                    f"CircuitBreaker: TRIPPED (#{self._trip_count}) — "
                    f"{self._failure_threshold} failures in {self._window_seconds}s. "
                    f"Pausing for {self._cooldown_seconds}s."
                )
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failure_times.clear()

    def reset(self) -> None:
        with self._lock:
            self._tripped = False
            self._failure_times.clear()
            logger.info("CircuitBreaker: manually reset")


_circuit_breaker = CircuitBreaker(
    failure_threshold=10, window_seconds=30.0, cooldown_seconds=10.0
)


def get_circuit_breaker() -> CircuitBreaker:
    return _circuit_breaker


# ---------------------------------------------------------------------------
# faster-whisper (primary, local).
# ---------------------------------------------------------------------------

_whisper_model: Any = None
_whisper_lock = threading.Lock()

_DEFAULT_MODEL_NAME = "base.en"


def _resolve_whisper_model_name() -> str:
    """Map ``config.voice.stt_model`` to a faster-whisper model name."""
    try:
        from src.shared.config import get_yaml_config

        raw = str(get_yaml_config().get("voice", {}).get("stt_model", "") or "")
    except Exception:
        raw = ""
    if not raw:
        return _DEFAULT_MODEL_NAME
    # Accept both "base.en" and "faster-whisper-base.en" forms.
    stripped = raw.removeprefix("faster-whisper-")
    return stripped or _DEFAULT_MODEL_NAME


def _get_whisper_model() -> Any:
    """Lazy-load the faster-whisper model. CUDA float16, falling back to CPU int8."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model

        from faster_whisper import WhisperModel

        model_name = _resolve_whisper_model_name()
        try:
            logger.info(f"STT: loading faster-whisper {model_name!r} on CUDA float16")
            _whisper_model = WhisperModel(model_name, device="cuda", compute_type="float16")
        except Exception as exc:
            logger.warning(f"STT: CUDA load failed ({exc!r}); falling back to CPU int8")
            _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        logger.info(f"STT: faster-whisper {model_name!r} ready")
        return _whisper_model


async def transcribe_whisper(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe ``audio`` via faster-whisper. Returns the text or ``None`` on failure."""
    try:
        model = await asyncio.to_thread(_get_whisper_model)

        def _run() -> tuple[str, Any]:
            segments, info = model.transcribe(
                audio.astype(np.float32),
                language="en",
                beam_size=5,
            )
            # Consume the generator inside the worker thread — iterating it
            # on the event loop would block.
            text = " ".join(seg.text for seg in segments).strip()
            return text, info

        text, info = await asyncio.to_thread(_run)
        logger.info(
            f"STT (whisper): {text[:80]!r} "
            f"(lang={info.language}, conf={info.language_probability:.2f})"
        )
        return text or None
    except Exception as exc:
        logger.error(f"STT: whisper failed: {exc!r}")
        return None


# ---------------------------------------------------------------------------
# ElevenLabs (optional fallback when the user has chosen mode=elevenlabs).
# ---------------------------------------------------------------------------

_elevenlabs_client: Any = None
_elevenlabs_client_lock = threading.Lock()


def _voice_mode() -> str:
    try:
        from src.shared.config import get_yaml_config

        return str(get_yaml_config().get("voice", {}).get("mode", "off") or "off")
    except Exception:
        return "off"


def _elevenlabs_key() -> str | None:
    try:
        from src.shared.secrets import get_key

        return get_key("elevenlabs")
    except Exception as exc:
        logger.debug(f"STT: keyring lookup for elevenlabs failed: {exc!r}")
        return None


def _elevenlabs_enabled() -> bool:
    """Only call ElevenLabs when the user opted in via wizard and a key exists."""
    return _voice_mode() == "elevenlabs" and bool(_elevenlabs_key())


def _get_elevenlabs_client() -> Any:
    global _elevenlabs_client
    if _elevenlabs_client is not None:
        return _elevenlabs_client
    with _elevenlabs_client_lock:
        if _elevenlabs_client is not None:
            return _elevenlabs_client
        from elevenlabs.client import ElevenLabs

        key = _elevenlabs_key()
        if not key:
            raise RuntimeError("ElevenLabs key not available")
        _elevenlabs_client = ElevenLabs(api_key=key)
        return _elevenlabs_client


async def transcribe_elevenlabs(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe via ElevenLabs Scribe v2. Returns ``None`` unless opted in + reachable."""
    if not _elevenlabs_enabled():
        return None
    try:
        client = _get_elevenlabs_client()
    except Exception as exc:
        logger.warning(f"STT: ElevenLabs unavailable: {exc!r}")
        return None

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    buf.seek(0)

    def _run() -> str:
        response = client.speech_to_text.convert(
            file=buf,
            model_id="scribe_v2",
            language_code="en",
        )
        return (response.text or "").strip()

    try:
        text = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning(f"STT: ElevenLabs failed: {exc!r}")
        return None

    logger.info(f"STT (elevenlabs): {text[:80]!r}")
    return text or None


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------

_LONG_BUFFER_WARN_S = 30.0
_VERY_LONG_BUFFER_WARN_S = 45.0


async def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe audio. faster-whisper primary; ElevenLabs fallback if opted-in."""
    if _circuit_breaker.is_tripped:
        logger.debug("STT: circuit breaker tripped — dropping audio frame")
        return None

    duration = len(audio) / sample_rate
    if duration > _VERY_LONG_BUFFER_WARN_S:
        logger.warning(f"STT: audio buffer extremely long ({duration:.1f}s) — possible overflow")
    elif duration > _LONG_BUFFER_WARN_S:
        logger.warning(f"STT: audio buffer long ({duration:.1f}s) — check audio pipeline")

    text = await transcribe_whisper(audio, sample_rate)
    if text:
        _circuit_breaker.record_success()
        return text

    if _elevenlabs_enabled():
        logger.info("STT: whisper empty — falling back to ElevenLabs")
        text = await transcribe_elevenlabs(audio, sample_rate)
        if text:
            _circuit_breaker.record_success()
            return text

    _circuit_breaker.record_failure()
    return None
