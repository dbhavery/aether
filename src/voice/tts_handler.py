"""TTS event handler — bridges ``RESPONSE_TEXT_READY`` to synth, audio playback, and EventBus chunks.

Flow on ``RESPONSE_TEXT_READY`` (non-interim, voice/video modes only):

  1. Run the text through ``src.voice.tts.synthesize`` (Chatterbox primary;
     ElevenLabs if the user picked that mode).
  2. Slice the resulting audio into ~100 ms int16 PCM chunks and publish
     each as ``RESPONSE_AUDIO_CHUNK`` on the EventBus. A future avatar
     subsystem subscribes to these to drive lip-sync.
  3. Publish ``RESPONSE_AUDIO_END`` once the whole clip has been emitted.
  4. Play the audio through the system default speakers via
     ``src.voice.audio_player.play_audio``.

Steps 2–3 and 4 run concurrently so lip-sync animation stays in lockstep
with actual speaker output.
"""

from __future__ import annotations

import asyncio
import base64

import numpy as np
from loguru import logger

from src.core.events import event_bus
from src.shared.types import AetherEvent, EventType
from src.voice.audio_player import play_audio
from src.voice.tts import synthesize

# 100 ms per emitted chunk — gives lip-sync enough granularity without
# overwhelming the EventBus.
_CHUNK_MS = 100

# Interim RESPONSE_TEXT_READY events can be partial sentences; synthesising
# long interim strings just to throw them away wastes GPU time.
_INTERIM_SKIP_THRESHOLD_CHARS = 60


async def _publish_audio_chunks(audio: np.ndarray, sample_rate: int) -> None:
    """Slice audio into ~100 ms int16 PCM chunks and emit EventBus events."""
    chunk_samples = max(1, int(sample_rate * _CHUNK_MS / 1000))
    # Convert once — per-chunk reconversion would waste CPU for every chunk.
    audio_int16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
    total_samples = int(audio_int16.shape[0])

    for start in range(0, total_samples, chunk_samples):
        chunk = audio_int16[start : start + chunk_samples]
        encoded = base64.b64encode(chunk.tobytes()).decode("ascii")
        await event_bus.publish(
            AetherEvent(
                type=EventType.RESPONSE_AUDIO_CHUNK,
                data={
                    "audio_b64": encoded,
                    "sample_rate": sample_rate,
                    "pcm_format": "int16",
                    "channels": 1,
                },
                source_module="tts_handler",
            )
        )

    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_AUDIO_END,
            data={"sample_rate": sample_rate, "total_samples": total_samples},
            source_module="tts_handler",
        )
    )


async def on_response_text_ready(event: AetherEvent) -> None:
    """Handle ``RESPONSE_TEXT_READY``: synth + playback + lip-sync chunks."""
    text = event.data.get("text", "")
    is_interim = bool(event.data.get("is_interim", False))
    mode = event.data.get("mode", "text")

    if not text or not text.strip():
        return
    # Text/chat mode never speaks audibly.
    if mode == "text":
        return
    # Skip long interim synths — only the finalized text is worth a synth pass.
    if is_interim and len(text) > _INTERIM_SKIP_THRESHOLD_CHARS:
        return

    result = await synthesize(text)
    if result is None:
        logger.error(f"TTS: synthesis failed for {text[:50]!r}")
        return

    audio, sample_rate = result
    await asyncio.gather(
        _publish_audio_chunks(audio, sample_rate),
        play_audio(audio, sample_rate),
    )


def register_tts_handlers() -> None:
    """Subscribe ``on_response_text_ready`` to ``RESPONSE_TEXT_READY`` on the EventBus."""
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, on_response_text_ready)
    logger.info("TTS: handler registered")
