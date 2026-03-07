"""Audio playback — plays synthesized speech through the system speakers."""

import asyncio

import numpy as np
import sounddevice as sd
from loguru import logger

from src.shared.config import get_yaml_config

_playback_lock = asyncio.Lock()


async def play_audio(audio: np.ndarray, sample_rate: int) -> None:
    """Play audio array through system speakers. Non-blocking via asyncio."""
    async with _playback_lock:
        try:
            config = get_yaml_config()
            output_device = config["audio"]["output_device"]

            def _play_and_wait() -> None:
                sd.play(audio, samplerate=sample_rate, device=output_device)
                sd.wait()

            await asyncio.to_thread(_play_and_wait)
            logger.debug(f"Audio: played {len(audio) / sample_rate:.1f}s")
        except Exception as e:
            logger.error(f"Audio: playback error: {e}")


async def stop_playback() -> None:
    """Stop any currently playing audio (for interruptions)."""
    try:
        sd.stop()
        logger.debug("Audio: playback stopped")
    except Exception as e:
        logger.error(f"Audio: stop error: {e}")
