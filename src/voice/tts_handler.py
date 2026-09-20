"""TTS event handler — bridges ``RESPONSE_TEXT_READY`` to synth, audio playback, and EventBus chunks.

Flow on ``RESPONSE_TEXT_READY`` (non-interim, voice/video modes only):

  1. Split the reply into sentences with ``_segment_for_speech``.
  2. For each sentence in order, run it through ``src.voice.tts.synthesize``
     (Chatterbox primary; ElevenLabs if the user picked that mode).
  3. Slice that sentence's audio into ~100 ms int16 PCM chunks and publish
     each as ``RESPONSE_AUDIO_CHUNK`` on the EventBus. A future avatar
     subsystem subscribes to these to drive lip-sync.
  4. Play it through the system default speakers via
     ``src.voice.audio_player.play_audio``.
  5. Publish ``RESPONSE_AUDIO_END`` once, after the last sentence.

Steps 3 and 4 run concurrently so lip-sync animation stays in lockstep with
actual speaker output.

Sentence at a time is a latency decision. Synthesis on this box runs at several
times real time, so synthesising the whole reply first made the listener wait
for audio that could already have been playing. ``first_audio_ms`` is marked on
the first chunk of the first sentence.
"""

from __future__ import annotations

import asyncio
import base64
import re

import numpy as np
from loguru import logger

from src.core import trace
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


async def _publish_audio_end(sample_rate: int, total_samples: int) -> None:
    """Emit ``RESPONSE_AUDIO_END`` once, for the whole reply.

    Separate from chunk publishing because a reply is now spoken one sentence
    at a time. Emitting this per sentence would tell the avatar and any
    lip-sync consumer that the reply had finished while the rest was still to
    come, and tying it to the last segment would skip it whenever that
    segment's synthesis failed.
    """
    await event_bus.publish(
        AetherEvent(
            type=EventType.RESPONSE_AUDIO_END,
            data={"sample_rate": sample_rate, "total_samples": total_samples},
            source_module="tts_handler",
        )
    )


async def _publish_audio_chunks(audio: np.ndarray, sample_rate: int) -> int:
    """Slice audio into ~100 ms int16 PCM chunks and emit EventBus events.

    Returns this clip's sample count. The caller owns ``RESPONSE_AUDIO_END``.
    """
    chunk_samples = max(1, int(sample_rate * _CHUNK_MS / 1000))
    # Convert once — per-chunk reconversion would waste CPU for every chunk.
    audio_int16 = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
    total_samples = int(audio_int16.shape[0])

    for start in range(0, total_samples, chunk_samples):
        chunk = audio_int16[start : start + chunk_samples]
        encoded = base64.b64encode(chunk.tobytes()).decode("ascii")
        # First chunk out is the perceived end of the wait. mark() keeps the
        # first write, so later chunks do not overwrite it.
        trace.mark("first_audio_ms")
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

    return total_samples


# A sentence boundary for speech: . ! ? followed by whitespace. Abbreviations
# are deliberately not special-cased. A wrong split costs a short pause between
# two spoken fragments; it can never change a word.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

# Below this, a fragment is glued onto the one before it. Synthesising "Yes."
# or "Okay." on its own sounds clipped, and the per-call overhead is not worth
# it.
#
# Deliberately low. This started at 25, which swallowed "Check the tires
# first." at 22 characters into the sentence after it and doubled the wait for
# first audio. The first segment wants to be as short as it can be while still
# sounding like an utterance, because every character in it is latency.
_MIN_SEGMENT_CHARS = 16


def _segment_for_speech(text: str) -> list[str]:
    """Split a reply into the units that get synthesised and spoken in order.

    Latency, not prosody, is the reason this exists. Synthesis on this box runs
    at several times real time, so synthesising a whole reply before playing
    any of it makes the listener wait for audio they could already have been
    hearing. One sentence at a time means first audio waits on the first
    sentence only.
    """
    parts = [p.strip() for p in _SENTENCE_END_RE.split(text.strip()) if p.strip()]
    if not parts:
        return []
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < _MIN_SEGMENT_CHARS:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


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

    # One sentence at a time. first_audio_ms is marked on the first chunk of
    # the first segment, so the listener waits for one sentence to synthesise
    # rather than the whole reply. trace.record_stage accumulates a repeated
    # name, so tts_synth still totals the synthesis for the turn.
    segments = _segment_for_speech(text)
    if not segments:
        return

    spoken_samples = 0
    sample_rate = 0
    for index, segment in enumerate(segments):
        with trace.stage("tts_synth"):
            result = await synthesize(segment)
        if result is None:
            # One bad segment must not silence the rest of the reply.
            logger.error(f"TTS: synthesis failed for segment {index + 1} {segment[:50]!r}")
            continue

        audio, sample_rate = result
        # playback is awaited here, so the enclosing turn total includes the
        # full spoken duration. That is why first_audio_ms, not the total, is
        # the latency figure.
        with trace.stage("tts_publish_and_play"):
            published, _ = await asyncio.gather(
                _publish_audio_chunks(audio, sample_rate),
                play_audio(audio, sample_rate),
            )
        spoken_samples += published

    if not spoken_samples:
        logger.error(f"TTS: every segment failed for {text[:50]!r}")
        return

    await _publish_audio_end(sample_rate, spoken_samples)
    trace.set_meta(
        tts_audio_seconds=round(float(spoken_samples) / float(sample_rate), 3),
        tts_segments=len(segments),
    )


def register_tts_handlers() -> None:
    """Subscribe ``on_response_text_ready`` to ``RESPONSE_TEXT_READY`` on the EventBus."""
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, on_response_text_ready)
    logger.info("TTS: handler registered")
