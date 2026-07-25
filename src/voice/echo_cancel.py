"""Echo cancellation — suppresses audio input while Aether is speaking.

Simple gate-based approach: during TTS playback, the audio input to wake word
and VAD is gated (suppressed). After TTS stops, a configurable ring-down period
(200ms default) allows residual echo to decay before re-enabling input.

This module provides a shared state flag that the audio capture callback
in pipeline.py checks on every frame.
"""

import threading
import time

from loguru import logger

from src.shared.config import get_yaml_config


class EchoCanceller:
    """Gate-based echo cancellation using TTS playback state tracking.

    Thread-safe — called from both the asyncio thread (TTS handler)
    and the PortAudio callback thread (audio capture).
    """

    def __init__(self, ring_down_ms: float | None = None):
        config = get_yaml_config()
        voice_config = config.get("voice", {})
        self._ring_down_ms = (
            ring_down_ms if ring_down_ms is not None else voice_config.get("echo_cancel_ring_down_ms", 200.0)
        )
        self._lock = threading.Lock()
        self._is_speaking = False
        self._speaking_stopped_at: float = 0.0

    @property
    def should_gate_input(self) -> bool:
        """Return True if audio input should be suppressed (Aether is speaking or in ring-down).

        Called from the PortAudio callback thread — must be fast and lock-free where possible.
        """
        with self._lock:
            if self._is_speaking:
                return True
            if self._speaking_stopped_at > 0:
                elapsed_ms = (time.monotonic() - self._speaking_stopped_at) * 1000
                if elapsed_ms < self._ring_down_ms:
                    return True
                # Ring-down complete — clear the timestamp
                self._speaking_stopped_at = 0.0
            return False

    def on_tts_start(self) -> None:
        """Called when TTS playback begins."""
        with self._lock:
            self._is_speaking = True
            self._speaking_stopped_at = 0.0
        logger.debug("EchoCanceller: TTS started — gating audio input")

    def on_tts_stop(self) -> None:
        """Called when TTS playback ends. Starts ring-down period.

        Idempotent: if already stopped (e.g., barge-in already called this),
        does not reset the ring-down timer.
        """
        with self._lock:
            if not self._is_speaking:
                return  # Already stopped — don't reset ring-down timer
            self._is_speaking = False
            self._speaking_stopped_at = time.monotonic()
        logger.debug(f"EchoCanceller: TTS stopped — ring-down {self._ring_down_ms:.0f}ms")

    @property
    def is_speaking(self) -> bool:
        """Check if Aether is currently speaking (without ring-down check)."""
        with self._lock:
            return self._is_speaking


# Module-level singleton — thread-safe (called from PortAudio callback + asyncio)
_echo_canceller: EchoCanceller | None = None
_echo_canceller_lock = threading.Lock()


def get_echo_canceller() -> EchoCanceller:
    """Get or create the module-level echo canceller (thread-safe)."""
    global _echo_canceller
    if _echo_canceller is None:
        with _echo_canceller_lock:
            if _echo_canceller is None:
                _echo_canceller = EchoCanceller()
    return _echo_canceller
