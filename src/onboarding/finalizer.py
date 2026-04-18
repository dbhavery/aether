"""Terminal step of the wizard — writes the durable product config.

``finalize_wizard`` is the last thing the wizard does before the user is
handed to the chat UI. API keys have already been written to the OS keyring
at their respective validation steps (``handler._dispatch``), so finalize is
limited to three durable side-effects:

1. Build + atomically write ``config.yaml`` (hard-fail with rollback).
2. Create the active persona's ChromaDB collection (best-effort).
3. Clear ``wizard_state.yaml`` (best-effort).

Step 1 is the only hard-failure: if the config file can't be written the
wizard cannot complete and the user retries. Steps 2 and 3 are retryable on
first use of the app, so failures there log a warning rather than unwind.
"""

from __future__ import annotations

import os
import uuid
from io import StringIO
from pathlib import Path
from typing import Any

from loguru import logger
from ruamel.yaml import YAML

from src.onboarding.state import WizardState, clear_wizard_state

# NOTE: ``get_config`` / ``AetherConfig`` are being built by a parallel agent
# in src/shared/config.py. Their exact shape is the YAML schema in
# docs/ARCHITECTURE-V2.md §6 — we construct a matching plain dict here so
# that when the model lands, ``AetherConfig.model_validate(plain_dict)`` will
# accept our output.
from src.shared.paths import get_config_path

# ---------------------------------------------------------------------------
# Tier-map presets — docs/LLM-PROVIDERS.md §3.
# ---------------------------------------------------------------------------

_TIER_PRESETS: dict[str, dict[str, str]] = {
    "anthropic": {
        "fast": "anthropic/claude-haiku-4-5",
        "main": "anthropic/claude-sonnet-4-6",
        "heavy": "anthropic/claude-opus-4-7",
    },
    "openai": {
        "fast": "openai/gpt-5-mini",
        "main": "openai/gpt-5",
        "heavy": "openai/gpt-5-thinking",
    },
    "google": {
        "fast": "gemini/gemini-2.5-flash-lite",
        "main": "gemini/gemini-2.5-flash",
        "heavy": "gemini/gemini-2.5-pro",
    },
    "groq": {
        "fast": "groq/llama-3.3-70b-versatile",
        "main": "groq/llama-3.3-70b-versatile",
        "heavy": "groq/llama-3.3-70b-versatile",
    },
    "openrouter": {
        "fast": "openrouter/google/gemini-flash-1.5",
        "main": "openrouter/anthropic/claude-sonnet-4-6",
        "heavy": "openrouter/anthropic/claude-opus-4-7",
    },
    "ollama": {
        "fast": "ollama/qwen2.5:7b",
        "main": "ollama/qwen2.5:14b",
        "heavy": "ollama/qwen2.5:32b",
    },
    "aether_guest": {
        "fast": "groq/llama-3.3-70b-versatile",
        "main": "groq/llama-3.3-70b-versatile",
        "heavy": "groq/llama-3.3-70b-versatile",
    },
}

_VOICE_DEFAULTS: dict[str, dict[str, Any]] = {
    "local": {
        "mode": "local",
        "stt_model": "faster-whisper-base.en",
        "tts_model": "chatterbox-turbo",
        "device": "default",
    },
    "elevenlabs": {
        "mode": "elevenlabs",
        "stt_model": "faster-whisper-base.en",
        "tts_model": "elevenlabs",
        "device": "default",
    },
    "off": {
        "mode": "off",
        "stt_model": "faster-whisper-base.en",
        "tts_model": "none",
        "device": "default",
    },
}


class FinalizeError(RuntimeError):
    """Raised when the wizard cannot write a complete, consistent config."""


async def finalize_wizard(state: WizardState) -> None:
    """Persist wizard output as the product's durable config.

    API keys have already been written to the OS keyring at their respective
    validation steps (see ``handler._dispatch``), so finalize is concerned
    only with the three remaining durable side-effects:

    1. Build + atomically write ``config.yaml``.
    2. Create the active persona's ChromaDB collection.
    3. Clear ``wizard_state.yaml``.

    Raises ``FinalizeError`` with a user-facing message if the config write
    fails (which is the only step treated as hard-failure — keyring is
    already done, Chroma and state-cleanup are retryable).
    """
    _ensure_complete(state)

    # Prefer the UUID the wizard has been using all along — keys were written
    # to the keyring under THIS username during screens 5/6, so reusing it is
    # what makes post-finalize reads succeed. Only mint a fresh one if the
    # wizard somehow reached HANDOFF without stamping one (shouldn't happen
    # because ``save_wizard_state`` populates it on first write, but keep a
    # defensive fallback rather than crashing here).
    if state.installation_id:
        installation_id = state.installation_id
    else:
        installation_id = str(uuid.uuid4())
        logger.warning(
            "WizardState reached finalize with no installation_id; "
            f"generating fallback {installation_id}. Any API keys written "
            "during the wizard may be stranded under a different username."
        )
    config_dict = _build_config_dict(state, installation_id)

    # 1. Config file — atomic temp+rename. Keys were written on validation,
    # so if this step fails we leave keys in the keyring for the retry.
    try:
        _write_config_atomically(config_dict)
    except OSError as exc:
        raise FinalizeError(f"Could not write config file: {exc}") from exc

    # Reset cached installation UUID in the secrets module so subsequent
    # keyring reads use the UUID we just wrote to config instead of the
    # "default" fallback that was used during the wizard itself. This is a
    # best-effort pragma — if ``secrets._installation_uuid`` isn't cached
    # (tests may monkeypatch it), we ignore.
    _reset_installation_uuid_cache()

    # 2. ChromaDB collection — best-effort. A missing collection can be
    # recreated on first use, so we log rather than roll back if this fails.
    try:
        _create_persona_collection(state.selected_avatar_id or "default")
    except Exception as exc:
        logger.warning(
            f"Persona Chroma collection creation failed for "
            f"{state.selected_avatar_id!r}: {exc!r} — will retry on first use"
        )

    # 3. Wizard state cleanup — also best-effort; a stale file is harmless
    # because the config's onboarding.complete flag supersedes it.
    try:
        clear_wizard_state()
    except RuntimeError as exc:
        logger.warning(f"Failed to clear wizard state after finalization: {exc!r}")

    logger.info(
        f"Onboarding finalized — installation_id={installation_id}, "
        f"persona={state.selected_avatar_id}, provider={state.llm_provider}, "
        f"voice={state.voice_mode}"
    )


def _reset_installation_uuid_cache() -> None:
    """Clear ``src.shared.secrets._installation_uuid`` lru_cache if present.

    During the wizard the secrets module's UUID falls back to ``"default"``
    because no config.yaml exists. Now that we've written one, the cache
    must be invalidated so keyring reads under the real UUID succeed.
    """
    try:
        from src.shared import secrets as _secrets

        cache_clear = getattr(_secrets._installation_uuid, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug(f"Could not clear installation UUID cache: {exc!r}")


# ---------------------------------------------------------------------------
# Config assembly.
# ---------------------------------------------------------------------------


def _ensure_complete(state: WizardState) -> None:
    """Fail fast if ``state`` lacks any field required to build a valid config."""
    missing: list[str] = []
    if not state.selected_avatar_id:
        missing.append("avatar")
    if not state.selected_archetype:
        missing.append("personality")
    if not state.display_name:
        missing.append("display_name")
    if not state.llm_provider:
        missing.append("llm_provider")
    if not state.voice_mode:
        missing.append("voice_mode")
    if state.accepted_terms_at is None:
        missing.append("terms_acceptance")
    if missing:
        raise FinalizeError(f"Wizard state incomplete: {', '.join(missing)}")


def _build_config_dict(state: WizardState, installation_id: str) -> dict[str, Any]:
    """Translate validated wizard state into the config.yaml dict.

    Matches the schema in docs/ARCHITECTURE-V2.md §6 verbatim so the parallel
    config-module's ``AetherConfig.model_validate`` will accept it without
    further coercion.
    """
    provider = state.llm_provider or "aether_guest"
    tier_map = dict(_TIER_PRESETS.get(provider, _TIER_PRESETS["aether_guest"]))
    # Apply per-tier overrides if the wizard's LLM screen captured any.
    if state.llm_tier_map:
        for tier in ("fast", "main", "heavy"):
            override = state.llm_tier_map.get(tier)
            if isinstance(override, str) and override.strip():
                tier_map[tier] = override.strip()

    voice_defaults = _VOICE_DEFAULTS[state.voice_mode or "off"]
    voice_block: dict[str, Any] = {**voice_defaults, **(state.voice_settings or {})}
    # Never persist the api_key into YAML even if a caller sneaks one in.
    voice_block.pop("api_key", None)

    accepted_iso = (
        state.accepted_terms_at.isoformat() if state.accepted_terms_at is not None else None
    )

    return {
        "aether": {
            "version": 1,
            "user_installation_id": installation_id,
            "telemetry": {
                "enabled": state.telemetry.crash_reports or state.telemetry.usage_counters,
                "crash_reports": state.telemetry.crash_reports,
                "usage_counters": state.telemetry.usage_counters,
            },
        },
        "onboarding": {
            "complete": True,
            "completed_at": accepted_iso,
            "wizard_started_at": state.started_at.isoformat(),
        },
        "persona": {
            "active": state.selected_avatar_id,
            "archetype": state.selected_archetype,
            "display_name": state.display_name,
        },
        "llm": {
            "provider": provider,
            "tier_map": tier_map,
        },
        "voice": voice_block,
        "ui": {
            "theme": "dark",
            "always_on_top": False,
        },
        "memory": {
            "enabled": True,
            "max_history_turns": 200,
            "retrieval_top_k": 5,
        },
        "avatar": {
            "engine": "liveportrait",
            "fps_target": 25,
            "quality": "standard",
        },
    }


# ---------------------------------------------------------------------------
# Atomic YAML write.
# ---------------------------------------------------------------------------


def _write_config_atomically(config: dict[str, Any]) -> None:
    """Write ``config`` to ``config.yaml`` via a temp-file + os.replace sequence."""
    path: Path = get_config_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.default_flow_style = False
    buf = StringIO()
    yaml.dump(config, buf)
    payload = buf.getvalue()

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError:
        _silently_remove(tmp_path)
        raise
    logger.info(f"Wrote onboarded config to {path}")


def _silently_remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning(f"Could not remove temp config file {path}: {exc!r}")


# ---------------------------------------------------------------------------
# ChromaDB collection creation.
# ---------------------------------------------------------------------------


def _create_persona_collection(persona_id: str) -> None:
    """Create the per-persona ChromaDB collection if it doesn't already exist."""
    import chromadb  # Local import — chroma startup is heavy and we don't need it elsewhere.
    from chromadb.config import Settings as ChromaSettings

    from src.shared.paths import get_chroma_dir

    chroma_root = get_chroma_dir() / persona_id
    chroma_root.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(chroma_root),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
    )
    # ``get_or_create_collection`` is idempotent — safe on re-runs.
    client.get_or_create_collection(name=f"persona_{persona_id}")
    logger.info(f"ChromaDB collection ready for persona='{persona_id}' at {chroma_root}")
