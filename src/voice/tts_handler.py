"""TTS event handler — bridges EventBus to TTS synthesis and audio playback."""

import asyncio
import base64

import numpy as np
from loguru import logger

from src.core.events import event_bus
from src.shared.types import EventType, AetherEvent
from src.voice.audio_player import play_audio
from src.voice.tts import synthesize

# Chunk size for lip sync: 100ms at 16kHz = 1600 samples = 3200 bytes (int16)
_LIP_SYNC_CHUNK_MS = 100


async def _send_audio_to_avatar(audio: np.ndarray, sample_rate: int) -> None:
    """Split audio into chunks and send to avatar for lip sync."""
    try:
        from src.avatar.client import get_avatar_client

        client = get_avatar_client()
        if not client.available:
            return

        # Convert float32 audio to int16 bytes for the avatar server
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        chunk_samples = int(sample_rate * _LIP_SYNC_CHUNK_MS / 1000)

        for i in range(0, len(audio_int16), chunk_samples):
            chunk = audio_int16[i : i + chunk_samples]
            chunk_b64 = base64.b64encode(chunk.tobytes()).decode()
            await client.send_audio_chunk(chunk_b64)
    except Exception as e:
        logger.debug(f"TTS: avatar lip sync failed (non-critical): {e}")


async def on_response_text_ready(event: AetherEvent) -> None:
    text = event.data.get("text", "")
    is_interim = event.data.get("is_interim", False)
    mode = event.data.get("mode", "text")

    if not text or not text.strip():
        return

    # Skip TTS synthesis in text/chat mode — only speak in voice/video modes
    if mode == "text":
        return

    # Skip synthesis for very long interim messages (just text)
    if is_interim and len(text) > 60:
        return

    result = await synthesize(text)
    if result:
        audio, sample_rate = result
        # Signal echo canceller that TTS is starting
        from src.voice.echo_cancel import get_echo_canceller

        echo = get_echo_canceller()
        echo.on_tts_start()
        try:
            # Send audio to avatar and play audio concurrently for lip sync timing
            await asyncio.gather(
                _send_audio_to_avatar(audio, sample_rate),
                play_audio(audio, sample_rate),
            )
        finally:
            echo.on_tts_stop()
        # Signal avatar that speaking is done
        if not is_interim:
            try:
                from src.avatar.client import get_avatar_client

                await get_avatar_client().set_speaking(False)
            except Exception as e:
                logger.debug(f"TTS: avatar set_speaking(False) failed (non-critical): {e}")
    else:
        logger.error(f"TTS: synthesis completely failed for text: '{text[:50]}'")


def register_tts_handlers() -> None:
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, on_response_text_ready)
    logger.info("TTS: handler registered")
