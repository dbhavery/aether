"""Voice input pipeline — push-to-talk model.

The frontend holds the trigger (spacebar). It publishes
``USER_SPEECH_START`` when the user presses down and ``USER_SPEECH_END``
when they release. This module listens for those events, captures the
audio between them via ``sounddevice``, runs it through
``src.voice.stt.transcribe``, and publishes ``TRANSCRIPT_READY`` plus
``USER_MESSAGE`` so the brain handles voice identically to chat.

Wake-word detection and speaker verification — both present in the
upstream codebase — are deliberately absent. Per docs/PRODUCT-PLAN.md §1
decision 10, v1.0 replaces wake word with push-to-talk; the old modules
were removed during the port.

Threading:
- ``sounddevice`` runs the audio callback on its own thread (PortAudio).
- The event loop dispatches ``USER_SPEECH_START`` / ``USER_SPEECH_END``
  handlers on the asyncio thread.
- The callback only appends to a shared buffer when ``_listening`` is
  True; both the flag and the buffer are guarded by ``_buffer_lock``.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import numpy as np
from loguru import logger

from src.core.events import event_bus
from src.shared.config import get_yaml_config
from src.shared.types import AetherEvent, EventType
from src.voice.stt import transcribe

# Push-to-talk captures at 16 kHz mono — the rate faster-whisper prefers and
# what every downstream module in the voice stack assumes. Making this
# configurable would require re-sampling elsewhere; punt to v1.1.
_SAMPLE_RATE = 16000
_CHANNELS = 1

# Hard cap on a single speech segment: long enough for normal monologue
# but short enough that a stuck trigger can't exhaust memory. At 16 kHz
# mono float32 this is ~7.7 MB.
_MAX_SEGMENT_SECONDS = 120.0
_MAX_SEGMENT_SAMPLES = int(_SAMPLE_RATE * _MAX_SEGMENT_SECONDS)


def _resolve_input_device() -> Any:
    """Map ``config.voice.device`` to the ``sounddevice`` ``device`` argument.

    ``sounddevice`` accepts ``int`` (index), ``str`` (name substring), or
    ``None`` (system default). The config key ships as ``"default"`` which
    is not a literal device name; treat any value in
    {"", "default", None} as "use system default".
    """
    raw = get_yaml_config().get("voice", {}).get("device")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.lower() == "default":
        return None
    return value


class VoicePipeline:
    """Push-to-talk voice capture driven by frontend events."""

    def __init__(self) -> None:
        self._input_device = _resolve_input_device()
        self._buffer_lock = threading.Lock()
        self._buffer: list[np.ndarray] = []
        self._buffer_samples = 0
        self._listening = False
        self._running = False
        self._stream: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Lazily imported so unit tests can stub sounddevice without
        # importing the real driver.
        self._sd: Any = None

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        """Open the audio device, subscribe to push-to-talk events, go live."""
        self._loop = asyncio.get_running_loop()
        self._running = True

        event_bus.subscribe(EventType.USER_SPEECH_START, self._on_speech_start)
        event_bus.subscribe(EventType.USER_SPEECH_END, self._on_speech_end)

        try:
            import sounddevice as sd  # type: ignore[import-not-found]

            self._sd = sd
            self._stream = sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="float32",
                device=self._input_device,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception:
            logger.exception("voice_pipeline: failed to open audio input stream")
            self._running = False
            self._report_status("error")
            return

        device_label = self._input_device if self._input_device is not None else "system-default"
        logger.info(
            f"voice_pipeline: push-to-talk ready "
            f"(device={device_label}, sr={_SAMPLE_RATE}Hz)"
        )
        self._report_status("ready")

    def stop(self) -> None:
        """Close the audio stream and detach from the event bus."""
        self._running = False
        with self._buffer_lock:
            self._listening = False
            self._buffer = []
            self._buffer_samples = 0

        event_bus.unsubscribe(EventType.USER_SPEECH_START, self._on_speech_start)
        event_bus.unsubscribe(EventType.USER_SPEECH_END, self._on_speech_end)

        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                logger.debug(f"voice_pipeline: stream.stop() raised {exc!r}")
            try:
                stream.close()
            except Exception as exc:
                logger.debug(f"voice_pipeline: stream.close() raised {exc!r}")

        logger.info("voice_pipeline: stopped")

    # -- audio callback (PortAudio thread) -----------------------------------

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        if status:
            logger.warning(f"voice_pipeline: audio status: {status}")
        with self._buffer_lock:
            if not self._listening:
                return
            chunk = indata[:, 0].copy()
            self._buffer.append(chunk)
            self._buffer_samples += chunk.shape[0]
            if self._buffer_samples > _MAX_SEGMENT_SAMPLES:
                # Stuck trigger guard: drop the oldest chunks. Users get a
                # truncated transcript rather than an OOM.
                drop = self._buffer_samples - _MAX_SEGMENT_SAMPLES
                while self._buffer and drop > 0:
                    oldest = self._buffer[0]
                    if oldest.shape[0] <= drop:
                        drop -= oldest.shape[0]
                        self._buffer_samples -= oldest.shape[0]
                        self._buffer.pop(0)
                    else:
                        self._buffer[0] = oldest[drop:]
                        self._buffer_samples -= drop
                        drop = 0

    # -- event handlers (asyncio thread) -------------------------------------

    async def _on_speech_start(self, event: AetherEvent) -> None:
        with self._buffer_lock:
            if self._listening:
                logger.debug("voice_pipeline: USER_SPEECH_START while already listening — resetting buffer")
            self._buffer = []
            self._buffer_samples = 0
            self._listening = True
        logger.debug("voice_pipeline: capture started")

    async def _on_speech_end(self, event: AetherEvent) -> None:
        with self._buffer_lock:
            if not self._listening:
                logger.debug("voice_pipeline: USER_SPEECH_END without active capture — ignored")
                return
            self._listening = False
            chunks = self._buffer
            total_samples = self._buffer_samples
            self._buffer = []
            self._buffer_samples = 0

        if not chunks:
            logger.debug("voice_pipeline: USER_SPEECH_END with empty buffer")
            return

        duration = total_samples / _SAMPLE_RATE
        logger.info(f"voice_pipeline: captured {duration:.1f}s — transcribing")
        audio = np.concatenate(chunks)

        text = await transcribe(audio, _SAMPLE_RATE)
        if not text:
            logger.info("voice_pipeline: empty transcript — dropping")
            return

        await event_bus.publish(
            AetherEvent(
                type=EventType.TRANSCRIPT_READY,
                data={"text": text, "confidence": 1.0},
                source_module="voice_pipeline",
            )
        )
        # Forward to the brain under the same contract chat uses so the LLM
        # pipeline treats voice and text identically.
        await event_bus.publish(
            AetherEvent(
                type=EventType.USER_MESSAGE,
                data={"text": text, "mode": "voice"},
                source_module="voice_pipeline",
            )
        )

    # -- health reporting (optional; only during start/stop) ------------------

    def _report_status(self, status: str) -> None:
        try:
            from src.core.health import update_module_status

            update_module_status("voice", status)
        except Exception as exc:
            logger.debug(f"voice_pipeline: health update skipped ({exc!r})")


# ---------------------------------------------------------------------------
# Module-level singleton API. ``src.core.startup`` calls
# ``start_voice_pipeline``; ``src.core.shutdown`` calls ``stop_voice_pipeline``.
# ---------------------------------------------------------------------------

_pipeline: VoicePipeline | None = None
_pipeline_lock = threading.Lock()


async def start_voice_pipeline() -> None:
    """Start (or restart) the global voice pipeline."""
    global _pipeline
    with _pipeline_lock:
        existing = _pipeline
        _pipeline = None
    if existing is not None:
        existing.stop()

    instance = VoicePipeline()
    await instance.start()

    with _pipeline_lock:
        _pipeline = instance


def stop_voice_pipeline() -> None:
    """Stop the global voice pipeline. No-op if it was never started."""
    global _pipeline
    with _pipeline_lock:
        existing = _pipeline
        _pipeline = None
    if existing is not None:
        existing.stop()
