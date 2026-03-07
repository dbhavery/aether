"""
TTS pipeline — Chatterbox Turbo (primary, local, free) -> ElevenLabs Flash v2.5 (cloud fallback).
"""

import asyncio
import re
import threading
from pathlib import Path

import numpy as np
from loguru import logger

from src.shared.config import get_settings, get_yaml_config

_chatterbox_model = None
_chatterbox_lock = threading.Lock()


def _get_chatterbox():
    global _chatterbox_model
    if _chatterbox_model is None:
        with _chatterbox_lock:
            if _chatterbox_model is None:
                from chatterbox.tts import ChatterboxTTS

                logger.info("TTS: Loading Chatterbox TTS model (CUDA)...")
                _chatterbox_model = ChatterboxTTS.from_pretrained(device="cuda")
                logger.info(f"TTS: Chatterbox ready (sr={_chatterbox_model.sr}Hz)")
    return _chatterbox_model


async def synthesize_chatterbox(
    text: str,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
) -> tuple[np.ndarray, int] | None:
    """Synthesize speech with Chatterbox using Aether's cloned voice. Returns (audio, sample_rate)."""
    config = get_yaml_config()
    ref_path_str = config.get("voice", {}).get("reference_voice_path")
    if not ref_path_str:
        logger.error("TTS: voice.reference_voice_path not set in config")
        return None
    ref_path = Path(ref_path_str)
    if not ref_path.is_absolute():
        ref_path = Path(__file__).resolve().parent.parent.parent / ref_path
    if not ref_path.exists():
        logger.error(f"TTS: Reference voice not found at {ref_path}")
        return None
    try:
        # Load model in thread to avoid blocking event loop on first call (~10s)
        model = await asyncio.to_thread(_get_chatterbox)

        # Parse emotion tags from text for exaggeration, then strip them
        text_clean = text
        if "[laugh]" in text or "[chuckle]" in text:
            exaggeration = 0.7
        elif "[sigh]" in text or "[sad]" in text:
            exaggeration = 0.4
        elif "[excited]" in text or "[happy]" in text:
            exaggeration = 0.65
        text_clean = re.sub(r"\[(?:laugh|chuckle|sigh|sad|excited|happy)\]", "", text_clean).strip()

        wav = await asyncio.to_thread(
            model.generate,
            text_clean,
            audio_prompt_path=str(ref_path),
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
        )
        audio = wav.squeeze().cpu().numpy()
        logger.debug(f"TTS (Chatterbox): {len(text)} chars -> {len(audio) / model.sr:.1f}s audio")
        return audio, model.sr
    except Exception as e:
        logger.error(f"TTS: Chatterbox failed: {e}")
        return None


_elevenlabs_tts_client = None
_elevenlabs_tts_lock = threading.Lock()


def _get_elevenlabs_tts_client():
    """Return the module-level ElevenLabs client singleton for TTS."""
    global _elevenlabs_tts_client
    if _elevenlabs_tts_client is None:
        with _elevenlabs_tts_lock:
            if _elevenlabs_tts_client is None:
                from elevenlabs.client import ElevenLabs

                settings = get_settings()
                if not settings.elevenlabs_api_key:
                    raise RuntimeError("ELEVENLABS_API_KEY not set")
                _elevenlabs_tts_client = ElevenLabs(api_key=settings.elevenlabs_api_key)
                logger.debug("TTS: ElevenLabs client singleton created")
    return _elevenlabs_tts_client


async def synthesize_elevenlabs(text: str) -> tuple[np.ndarray, int] | None:
    """Synthesize speech with ElevenLabs Flash v2.5. Cloud fallback."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        logger.warning("TTS: ELEVENLABS_API_KEY not set — ElevenLabs unavailable")
        return None
    try:
        from elevenlabs import VoiceSettings

        client = _get_elevenlabs_tts_client()

        config = get_yaml_config()
        voice_id = config.get("voice", {}).get("elevenlabs_voice_id", "9BWtsMINqrJLrRacOk9x")
        voice_settings = VoiceSettings(
            stability=config.get("voice", {}).get("voice_stability", 0.5),
            similarity_boost=config.get("voice", {}).get("voice_similarity", 0.75),
        )

        def _synthesize_and_collect():
            """Call ElevenLabs API and consume the byte generator in the worker thread."""
            chunks = client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_flash_v2_5",
                output_format="pcm_24000",
                voice_settings=voice_settings,
            )
            return b"".join(chunks)

        audio_data = await asyncio.to_thread(_synthesize_and_collect)
        audio = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        logger.debug(f"TTS (ElevenLabs): {len(text)} chars -> {len(audio) / 24000:.1f}s audio")
        return audio, 24000
    except Exception as e:
        logger.error(f"TTS: ElevenLabs failed: {e}")
        return None


async def synthesize(text: str) -> tuple[np.ndarray, int] | None:
    """Synthesize with Chatterbox primary, ElevenLabs fallback."""
    if not text.strip():
        return None
    result = await synthesize_chatterbox(text)
    if result:
        return result
    logger.info("TTS: Chatterbox failed, trying ElevenLabs fallback")
    return await synthesize_elevenlabs(text)
