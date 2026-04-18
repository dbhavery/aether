"""Text-to-speech — Chatterbox Turbo local (primary) + ElevenLabs Flash v2.5 fallback.

v1.0 synthesises with Chatterbox, cloning the active persona's voice from
``<persona>/voice/reference.wav`` when that file exists. If the persona has
no reference (or no persona is active yet), Chatterbox's own default voice
is used so the pipeline stays functional during onboarding and for
persona packs that are still being authored.

ElevenLabs is attempted only when BOTH:

  1. ``config.voice.mode == "elevenlabs"`` (user opted in), and
  2. An ``elevenlabs`` API key resolves via the OS keyring (or env-var fallback).

When the ElevenLabs path is active it takes priority — the user's whole
point in choosing ``elevenlabs`` mode is that they want the cloud voice.
If the cloud call fails, Chatterbox still runs as a safety net so speech
never goes silent.
"""

from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

# ---------------------------------------------------------------------------
# Emotion tag handling — shared by both engines.
# ---------------------------------------------------------------------------
#
# ``[laugh]``, ``[sad]`` etc. inside the text are consumed here: they bias
# the Chatterbox ``exaggeration`` parameter and are stripped from the string
# so they don't end up pronounced.

_EMOTION_PATTERN = re.compile(r"\[(?:laugh|chuckle|sigh|sad|excited|happy)\]")
_EMOTION_MAP: dict[str, float] = {
    "laugh": 0.7,
    "chuckle": 0.7,
    "sigh": 0.4,
    "sad": 0.4,
    "excited": 0.65,
    "happy": 0.65,
}


def _extract_emotion_exaggeration(text: str, default: float) -> float:
    for tag, value in _EMOTION_MAP.items():
        if f"[{tag}]" in text:
            return value
    return default


def _strip_emotion_tags(text: str) -> str:
    return _EMOTION_PATTERN.sub("", text).strip()


# ---------------------------------------------------------------------------
# Chatterbox (primary, local).
# ---------------------------------------------------------------------------

_chatterbox_model: Any = None
_chatterbox_lock = threading.Lock()


def _resolve_persona_reference() -> Path | None:
    """Return the active persona's ``voice/reference.wav`` if present, else ``None``."""
    try:
        from src.personas.manager import get_persona_manager

        pack = get_persona_manager().active_persona
    except Exception as exc:
        logger.debug(f"TTS: persona manager unavailable: {exc!r}")
        return None

    if pack is None:
        return None

    ref = pack.reference_wav_path
    if ref.exists():
        return ref
    logger.debug(f"TTS: persona {pack.id!r} has no reference.wav at {ref}")
    return None


def _get_chatterbox() -> Any:
    global _chatterbox_model
    if _chatterbox_model is not None:
        return _chatterbox_model
    with _chatterbox_lock:
        if _chatterbox_model is not None:
            return _chatterbox_model
        from chatterbox.tts import ChatterboxTTS

        try:
            logger.info("TTS: loading Chatterbox on CUDA")
            _chatterbox_model = ChatterboxTTS.from_pretrained(device="cuda")
        except Exception as exc:
            logger.warning(f"TTS: Chatterbox CUDA load failed ({exc!r}); trying CPU")
            _chatterbox_model = ChatterboxTTS.from_pretrained(device="cpu")
        logger.info(f"TTS: Chatterbox ready (sr={_chatterbox_model.sr}Hz)")
        return _chatterbox_model


async def synthesize_chatterbox(
    text: str,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
) -> tuple[np.ndarray, int] | None:
    """Synthesize ``text`` with Chatterbox. Returns ``(audio_float32, sample_rate)`` or None."""
    clean = _strip_emotion_tags(text)
    if not clean:
        return None
    exaggeration = _extract_emotion_exaggeration(text, default=exaggeration)

    try:
        model = await asyncio.to_thread(_get_chatterbox)
    except Exception as exc:
        logger.error(f"TTS: Chatterbox load failed: {exc!r}")
        return None

    ref_path = _resolve_persona_reference()

    def _run() -> np.ndarray:
        kwargs: dict[str, Any] = {
            "exaggeration": exaggeration,
            "cfg_weight": cfg_weight,
        }
        if ref_path is not None:
            kwargs["audio_prompt_path"] = str(ref_path)
        wav = model.generate(clean, **kwargs)
        return wav.squeeze().cpu().numpy()

    try:
        audio = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.error(f"TTS: Chatterbox synthesize failed: {exc!r}")
        return None

    logger.debug(
        f"TTS (chatterbox): {len(text)} chars -> {len(audio) / model.sr:.1f}s "
        f"(ref={'persona' if ref_path else 'default'})"
    )
    return audio, int(model.sr)


# ---------------------------------------------------------------------------
# ElevenLabs (optional — only when the user picked mode=elevenlabs).
# ---------------------------------------------------------------------------

_elevenlabs_client: Any = None
_elevenlabs_client_lock = threading.Lock()

# Placeholder "generic warm" ElevenLabs voice. Overridable at runtime via the
# (optional) ``voice.elevenlabs_voice_id`` config key.
_DEFAULT_ELEVENLABS_VOICE_ID = "9BWtsMINqrJLrRacOk9x"


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
        logger.debug(f"TTS: keyring lookup for elevenlabs failed: {exc!r}")
        return None


def _elevenlabs_enabled() -> bool:
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


async def synthesize_elevenlabs(text: str) -> tuple[np.ndarray, int] | None:
    """Synthesize via ElevenLabs Flash v2.5. Returns float32 @ 24 kHz or ``None``."""
    if not _elevenlabs_enabled():
        return None
    clean = _strip_emotion_tags(text)
    if not clean:
        return None

    try:
        client = _get_elevenlabs_client()
    except Exception as exc:
        logger.warning(f"TTS: ElevenLabs unavailable: {exc!r}")
        return None

    try:
        from elevenlabs import VoiceSettings

        from src.shared.config import get_yaml_config

        vc = get_yaml_config().get("voice", {}) or {}
        voice_id = str(vc.get("elevenlabs_voice_id") or _DEFAULT_ELEVENLABS_VOICE_ID)
        settings = VoiceSettings(
            stability=float(vc.get("voice_stability", 0.5)),
            similarity_boost=float(vc.get("voice_similarity", 0.75)),
        )
    except Exception as exc:
        logger.error(f"TTS: ElevenLabs settings setup failed: {exc!r}")
        return None

    def _run() -> bytes:
        chunks = client.text_to_speech.convert(
            text=clean,
            voice_id=voice_id,
            model_id="eleven_flash_v2_5",
            output_format="pcm_24000",
            voice_settings=settings,
        )
        return b"".join(chunks)

    try:
        audio_bytes = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.error(f"TTS: ElevenLabs synthesize failed: {exc!r}")
        return None

    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    logger.debug(f"TTS (elevenlabs): {len(text)} chars -> {len(audio) / 24000:.1f}s")
    return audio, 24000


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


async def synthesize(text: str) -> tuple[np.ndarray, int] | None:
    """Synthesize ``text``. Routes by ``voice.mode``; Chatterbox safety-net on failure."""
    if not text or not text.strip():
        return None

    # ElevenLabs mode: honor the user's cloud preference; fall back to Chatterbox
    # if the cloud call fails so speech is never silent.
    if _elevenlabs_enabled():
        result = await synthesize_elevenlabs(text)
        if result is not None:
            return result
        logger.info("TTS: ElevenLabs failed — falling back to Chatterbox")

    return await synthesize_chatterbox(text)
