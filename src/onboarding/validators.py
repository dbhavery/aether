"""Per-step wizard input validation.

Every ``validate_*`` function returns a ``(passed, error_message)`` tuple:

    (True, None)             on success
    (False, "explanation")   on failure

The frontend surfaces the message verbatim, so messages are short, actionable,
and never leak key material or low-level errors. Provider test calls use
``litellm`` so the same code path is exercised in validation as in production.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

import aiohttp
from loguru import logger

from src.shared.paths import get_bundled_personas_dir, get_data_dir, get_personas_dir

# ---------------------------------------------------------------------------
# Canonical data — mirrors docs/PERSONA-SCHEMA.md §7.
# ---------------------------------------------------------------------------

# The 12 canonical avatar IDs shipped with v1.0. The wizard shows a card per
# ID; any selection must land in this set OR on a user-override persona
# folder under ``%APPDATA%/aether/personas/``.
CANONICAL_AVATAR_IDS: frozenset[str] = frozenset(
    {
        "aurora",
        "caelum",
        "luma",
        "rhea",
        "kai",
        "nova",
        "onyx",
        "sage",
        "milo",
        "ivy",
        "atlas",
        "wren",
    }
)

# The 12 personality archetypes from docs/PERSONA-SCHEMA.md §2 (persona.yaml.
# personality.archetype). The wizard's personality grid maps 1:1 to these.
CANONICAL_ARCHETYPES: frozenset[str] = frozenset(
    {
        "warm_supportive",
        "analytical_precise",
        "playful_witty",
        "formal_executive",
        "calm_zen",
        "energetic_enthusiastic",
        "dry_sardonic",
        "mentor_teacher",
        "peer_collaborator",
        "creative_artistic",
        "technical_engineer",
        "curious_inquisitive",
    }
)

# Display-name rules — v1.0 constraint: no HTML, no emoji, <=40 chars.
_MAX_DISPLAY_NAME_LEN = 40
_HTML_MARKUP_RE = re.compile(r"<[^>]*>")
# Match anything outside the BMP (covers most emoji + ZWJ sequences) and the
# BMP-resident miscellaneous-symbols / dingbats / supplemental-arrow ranges.
_DISALLOWED_CHAR_RE = re.compile(
    r"[\U00010000-\U0010FFFF"  # all supplementary planes (emoji)
    r"\u2600-\u27BF"  # misc symbols + dingbats (warning signs, stars, etc.)
    r"\uFE0F"  # variation selector-16 (emoji presentation)
    r"]"
)

# Ollama defaults — the ``/api/tags`` endpoint is served by a vanilla Ollama
# install on localhost. We probe it with a short timeout so the wizard doesn't
# hang when Ollama isn't running.
OLLAMA_DEFAULT_URL = "http://localhost:11434"
_OLLAMA_TIMEOUT_SECONDS = 3.0

# Provider test-call knobs. One token is enough to prove the key works; a
# tight timeout keeps the wizard responsive when a key is wrong or the
# provider is flaky.
_LLM_TEST_TIMEOUT_SECONDS = 10.0
_LLM_TEST_MAX_TOKENS = 1

# Probe models used only for key-validation calls. Picked to be the cheapest
# "always-available" model on each provider as of 2026-04.
_PROVIDER_TEST_MODELS: dict[str, str] = {
    "anthropic": "anthropic/claude-haiku-4-5",
    "openai": "openai/gpt-5-mini",
    "google": "gemini/gemini-2.5-flash-lite",
    "groq": "groq/llama-3.3-70b-versatile",
    "openrouter": "openrouter/google/gemini-flash-1.5",
}

# Minimum free disk + VRAM requirements for the local voice path. Numbers
# come from ONBOARDING-SPEC.md §Screen 6 (faster-whisper base ~200 MB +
# Chatterbox Turbo ~800 MB, with working headroom). 6 GB VRAM is the spec's
# stated cut-off before we recommend cloud voice.
_LOCAL_VOICE_MIN_FREE_DISK_BYTES = 3 * 1024**3  # 3 GB headroom above the 1 GB model footprint
_LOCAL_VOICE_MIN_VRAM_BYTES = 6 * 1024**3  # 6 GB

_ValidationResult = tuple[bool, str | None]


# ---------------------------------------------------------------------------
# Avatar / archetype / name — pure validators (no I/O).
# ---------------------------------------------------------------------------


def validate_avatar(avatar_id: str) -> _ValidationResult:
    """Confirm ``avatar_id`` refers to a bundled or user-override persona.

    The wizard ships 12 canonical avatars (``CANONICAL_AVATAR_IDS``). Power
    users can also drop a custom persona pack into
    ``%APPDATA%/aether/personas/<id>/`` — if that directory exists, the id is
    also accepted.
    """
    if not isinstance(avatar_id, str) or not avatar_id.strip():
        return False, "Please choose an avatar."
    cleaned = avatar_id.strip().lower()
    if cleaned in CANONICAL_AVATAR_IDS:
        return True, None
    # Accept any persona pack the user has installed under their data dir.
    override_dir = get_personas_dir() / cleaned
    if override_dir.is_dir():
        return True, None
    # Fall back to a bundled persona folder match (useful when canonical
    # list grows post-v1.0 before this file is updated).
    bundled_dir = get_bundled_personas_dir() / cleaned
    if bundled_dir.is_dir() and not cleaned.startswith("_"):
        return True, None
    return False, f"Unknown avatar '{avatar_id}'."


def validate_archetype(archetype: str) -> _ValidationResult:
    """Confirm ``archetype`` is one of the 12 canonical personality archetypes."""
    if not isinstance(archetype, str) or not archetype.strip():
        return False, "Please choose a personality."
    if archetype.strip() not in CANONICAL_ARCHETYPES:
        return False, f"Unknown personality '{archetype}'."
    return True, None


def validate_display_name(name: str) -> _ValidationResult:
    """Enforce v1.0 display-name rules: non-empty, <=40 chars, no HTML, no emoji."""
    if not isinstance(name, str):
        return False, "Display name must be text."
    stripped = name.strip()
    if not stripped:
        return False, "Display name cannot be empty."
    if len(stripped) > _MAX_DISPLAY_NAME_LEN:
        return False, f"Display name must be {_MAX_DISPLAY_NAME_LEN} characters or fewer."
    if _HTML_MARKUP_RE.search(stripped):
        return False, "Display name cannot contain HTML or markup."
    if _DISALLOWED_CHAR_RE.search(stripped):
        return False, "Display name cannot contain emoji or symbol characters."
    return True, None


# ---------------------------------------------------------------------------
# LLM provider — async; performs one real test call via litellm or HTTP.
# ---------------------------------------------------------------------------


async def validate_llm_provider(
    provider: str,
    key: str | None,
    model_overrides: dict[str, str] | None = None,
) -> _ValidationResult:
    """Verify the user's LLM choice by making one real call.

    Rules:
    - ``"aether_guest"``: always valid (no user key; rate-limited hosted proxy).
    - ``"ollama"``: probes ``GET /api/tags`` on localhost — no key required.
    - Other providers: require ``key``; issue one minimal completion through
      ``litellm.acompletion`` to prove the key is live.
    """
    if not isinstance(provider, str) or not provider.strip():
        return False, "Please choose an LLM provider."

    provider_lc = provider.strip().lower()

    if provider_lc == "aether_guest":
        return True, None

    if provider_lc == "ollama":
        return await _probe_ollama(model_overrides)

    if provider_lc not in _PROVIDER_TEST_MODELS:
        return False, f"Unsupported LLM provider '{provider}'."

    if not key or not key.strip():
        return False, "API key is required for this provider."

    model = (model_overrides or {}).get("fast") or _PROVIDER_TEST_MODELS[provider_lc]
    return await _probe_litellm(provider_lc, model, key.strip())


async def _probe_ollama(model_overrides: dict[str, str] | None) -> _ValidationResult:
    """Check the local Ollama daemon and — if a model is named — that it's pulled."""
    tags_url = f"{OLLAMA_DEFAULT_URL}/api/tags"
    try:
        timeout = aiohttp.ClientTimeout(total=_OLLAMA_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as resp:
                if resp.status != 200:
                    return False, (
                        f"Ollama returned HTTP {resp.status}. "
                        "Make sure Ollama is running."
                    )
                payload = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning(f"Ollama probe failed: {exc!r}")
        return False, (
            "Ollama isn't reachable at localhost:11434. "
            "Start Ollama and try again."
        )

    installed = {m.get("name") for m in (payload.get("models") or []) if isinstance(m, dict)}
    required = (model_overrides or {}).get("fast") or (model_overrides or {}).get("main")
    if required:
        # Normalise "ollama/qwen2.5:7b" → "qwen2.5:7b" for matching tags output.
        canonical = required.split("/", 1)[1] if required.startswith("ollama/") else required
        if canonical not in installed:
            return False, f"Ollama is running, but the model '{canonical}' is not pulled yet."
    return True, None


async def _probe_litellm(provider: str, model: str, key: str) -> _ValidationResult:
    """Run one minimal completion through litellm and translate exceptions to messages."""
    try:
        import litellm  # Imported lazily so module import doesn't pull it in for pure validators.
    except ImportError:
        logger.error("litellm is not installed — cannot validate LLM key")
        return False, "LLM validation is unavailable (missing litellm dependency)."

    api_key_kwarg = _litellm_api_key_kwarg(provider)
    messages = [{"role": "user", "content": "ping"}]
    try:
        await asyncio.wait_for(
            litellm.acompletion(
                model=model,
                messages=messages,
                max_tokens=_LLM_TEST_MAX_TOKENS,
                stream=False,
                **{api_key_kwarg: key},
            ),
            timeout=_LLM_TEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return False, "Provider didn't respond within 10 seconds. Try again."
    except Exception as exc:  # litellm raises provider-specific subclasses
        return False, _translate_litellm_error(exc)
    return True, None


def _litellm_api_key_kwarg(provider: str) -> str:
    """Return the kwarg name litellm uses to pass a per-call key for ``provider``."""
    # litellm accepts ``api_key`` generically for most providers; Google/Gemini
    # is the exception (``api_key`` still works via env but passing the kwarg
    # directly is the most reliable path). We use ``api_key`` uniformly.
    return "api_key"


def _translate_litellm_error(exc: Exception) -> str:
    """Map a litellm exception to a short, user-safe message."""
    text = str(exc).lower()
    if "authenticationerror" in type(exc).__name__.lower() or "401" in text or "invalid api key" in text:
        return "That API key was rejected by the provider."
    if "permission" in text or "403" in text:
        return "Your API key doesn't have permission for this model."
    if "ratelimit" in text or "429" in text:
        return "Provider rate limit hit. Wait a minute and try again."
    if "not found" in text or "404" in text:
        return "The selected model isn't available on this provider."
    if "timeout" in text or "timed out" in text:
        return "Provider didn't respond in time. Try again."
    # Generic fallback — don't leak raw provider error text into the UI.
    logger.warning(f"Unmapped litellm error during validation: {exc!r}")
    return "Couldn't reach the provider. Check your network and try again."


# ---------------------------------------------------------------------------
# Voice — async; GPU/disk probe for local, key test for ElevenLabs, no-op for off.
# ---------------------------------------------------------------------------


async def validate_voice_mode(mode: str, settings: dict[str, Any]) -> _ValidationResult:
    """Verify the voice choice is viable on this machine."""
    if not isinstance(mode, str) or not mode.strip():
        return False, "Please choose a voice option."
    mode_lc = mode.strip().lower()

    if mode_lc == "off":
        return True, None

    if mode_lc == "local":
        return _probe_local_voice()

    if mode_lc == "elevenlabs":
        key = (settings or {}).get("api_key")
        if not isinstance(key, str) or not key.strip():
            return False, "ElevenLabs API key is required."
        return await _probe_elevenlabs(key.strip())

    return False, f"Unknown voice option '{mode}'."


def _probe_local_voice() -> _ValidationResult:
    """Synchronous hardware check — disk headroom + (optional) CUDA VRAM."""
    data_root: Path = get_data_dir()
    try:
        free_bytes = shutil.disk_usage(data_root).free
    except OSError as exc:
        logger.warning(f"disk_usage failed for {data_root}: {exc!r}")
        return False, "Couldn't check free disk space."
    if free_bytes < _LOCAL_VOICE_MIN_FREE_DISK_BYTES:
        needed_gb = _LOCAL_VOICE_MIN_FREE_DISK_BYTES / 1024**3
        return False, f"Local voice needs at least {needed_gb:.0f} GB of free disk space."

    # Torch is optional at import time — a machine without a GPU may not have
    # it installed, and a clean failure path must not crash the wizard.
    try:
        import torch  # noqa: PLC0415 — lazy import keeps the wizard import cheap
    except ImportError:
        logger.info("torch not installed — local voice will run on CPU")
        return True, None

    if not torch.cuda.is_available():
        # CPU-only is allowed but slow; we let the user through and the
        # wizard UI warns them. Treating this as a hard failure would
        # needlessly block machines that can genuinely run TTS on CPU.
        logger.info("CUDA not available — local voice will run on CPU")
        return True, None

    try:
        props = torch.cuda.get_device_properties(0)
    except Exception as exc:
        logger.warning(f"Could not read GPU properties: {exc!r}")
        return True, None  # GPU detected but details unreadable — don't block

    if props.total_memory < _LOCAL_VOICE_MIN_VRAM_BYTES:
        needed_gb = _LOCAL_VOICE_MIN_VRAM_BYTES / 1024**3
        have_gb = props.total_memory / 1024**3
        return False, (
            f"Local voice needs ~{needed_gb:.0f} GB VRAM; this GPU has {have_gb:.1f} GB. "
            "Consider cloud voice or text-only mode."
        )
    return True, None


async def _probe_elevenlabs(key: str) -> _ValidationResult:
    """GET /v1/user on ElevenLabs with the provided key."""
    url = "https://api.elevenlabs.io/v1/user"
    headers = {"xi-api-key": key, "Accept": "application/json"}
    try:
        timeout = aiohttp.ClientTimeout(total=_LLM_TEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return True, None
                if resp.status in (401, 403):
                    return False, "That ElevenLabs API key was rejected."
                return False, f"ElevenLabs returned HTTP {resp.status}."
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning(f"ElevenLabs probe failed: {exc!r}")
        return False, "Couldn't reach ElevenLabs. Check your network and try again."


# ---------------------------------------------------------------------------
# Terms & Privacy — pure boolean check.
# ---------------------------------------------------------------------------


def validate_terms_acceptance(
    accepted: bool, crash_reports: bool, usage_counters: bool
) -> _ValidationResult:
    """The ToS checkbox must be ticked; telemetry opt-ins are free-form booleans."""
    if not isinstance(accepted, bool) or not accepted:
        return False, "You must agree to the Terms of Service and Privacy Policy to continue."
    if not isinstance(crash_reports, bool) or not isinstance(usage_counters, bool):
        return False, "Telemetry preferences must be boolean."
    return True, None
