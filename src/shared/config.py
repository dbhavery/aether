"""Aether configuration — env-var settings plus structured YAML config.

This module exposes two layers:

1. ``AetherSettings`` (via ``get_settings``) — process-level knobs that come
   from environment variables or an adjacent ``.env`` file. Used for
   developer convenience (API keys during local dev, port overrides,
   logging verbosity) and by code paths that run before the YAML config is
   available. API keys here are wrapped in ``SecretStr``; production keys
   should live in the OS keyring (``src.shared.secrets``), not in env vars.

2. ``AetherConfig`` (via ``get_config`` / ``save_config``) — the structured
   user configuration persisted to ``<user_config_dir>/aether/config.yaml``
   and defined in ``docs/ARCHITECTURE-V2.md`` §6. Loaded with ``ruamel.yaml``
   round-trip so user comments and key ordering survive edits.

Legacy callers using ``get_yaml_config`` / ``reload_yaml_config`` continue
to work; they receive the same dict-shaped view of the YAML file that
existed before the refactor.
"""

from __future__ import annotations

import copy
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from src.shared.paths import get_config_path

# ---------------------------------------------------------------------------
# Env-var settings (developer / process-level)
# ---------------------------------------------------------------------------


class AetherSettings(BaseSettings):
    """Environment-variable settings: ports, log level, dev-only API keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Dev-convenience API keys. Production deployments store keys in the OS
    # keyring via src.shared.secrets; these env vars are a fallback only.
    anthropic_api_key: SecretStr = Field(SecretStr(""), validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr = Field(SecretStr(""), validation_alias="OPENAI_API_KEY")
    google_api_key: SecretStr = Field(SecretStr(""), validation_alias="GOOGLE_API_KEY")
    elevenlabs_api_key: SecretStr = Field(SecretStr(""), validation_alias="ELEVENLABS_API_KEY")

    # Infrastructure knobs.
    ollama_base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    websocket_port: int = Field(8765, validation_alias="WEBSOCKET_PORT")
    health_port: int = Field(8767, validation_alias="HEALTH_PORT")
    server_host: str = Field("127.0.0.1", validation_alias="SERVER_HOST")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    # Data-dir override; primarily consumed by src.shared.paths but exposed
    # here for parity with the rest of the env surface.
    aether_data_dir: str = Field("", validation_alias="AETHER_DATA_DIR")


@lru_cache(maxsize=1)
def get_settings() -> AetherSettings:
    """Return the cached process-level settings object."""
    return AetherSettings()


# ---------------------------------------------------------------------------
# Structured YAML config (user-facing)
# ---------------------------------------------------------------------------


class TelemetrySettings(BaseModel):
    """Opt-in telemetry flags."""

    enabled: bool = False
    crash_reports: bool = False


class AetherMeta(BaseModel):
    """Top-level metadata for the config file itself."""

    version: int = 1
    user_installation_id: str = ""
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)


class OnboardingState(BaseModel):
    """Wizard completion state."""

    complete: bool = False
    current_step: str = "welcome"
    completed_at: str | None = None


class PersonaSelection(BaseModel):
    """Which persona is active and its user-facing display name."""

    active: str = ""
    display_name: str = ""


class LLMTierMap(BaseModel):
    """Mapping from abstract tiers (fast/main/heavy) to litellm model IDs."""

    fast: str = "ollama/qwen2.5:7b"
    main: str = "ollama/qwen2.5:14b"
    heavy: str = "ollama/qwen2.5:32b"


class LLMSettings(BaseModel):
    """Primary LLM provider and per-tier model selection."""

    provider: str = "ollama"
    tier_map: LLMTierMap = Field(default_factory=LLMTierMap)


class VoiceSettings(BaseModel):
    """STT / TTS engine selection and audio device."""

    mode: str = "local"
    stt_model: str = "faster-whisper-base.en"
    tts_model: str = "chatterbox-turbo"
    device: str = "default"


class UISettings(BaseModel):
    """Desktop-shell window and theme preferences."""

    theme: str = "dark"
    always_on_top: bool = False
    window_position: list[int] | None = None
    window_size: list[int] | None = None


class MemorySettings(BaseModel):
    """Long-term memory / history bounds."""

    enabled: bool = True
    max_history_turns: int = 200
    retrieval_top_k: int = 5


class AvatarSettings(BaseModel):
    """Avatar engine configuration."""

    engine: str = "liveportrait"
    fps_target: int = 25
    quality: str = "standard"


class AetherConfig(BaseModel):
    """Full structured config loaded from and saved to config.yaml."""

    aether: AetherMeta = Field(default_factory=AetherMeta)
    onboarding: OnboardingState = Field(default_factory=OnboardingState)
    persona: PersonaSelection = Field(default_factory=PersonaSelection)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    ui: UISettings = Field(default_factory=UISettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    avatar: AvatarSettings = Field(default_factory=AvatarSettings)


# ---------------------------------------------------------------------------
# Loader / saver
# ---------------------------------------------------------------------------


def _yaml_engine() -> YAML:
    """Return a ruamel.yaml engine configured for round-trip preservation."""
    engine = YAML(typ="rt")
    engine.preserve_quotes = True
    engine.indent(mapping=2, sequence=4, offset=2)
    engine.width = 120
    return engine


def _default_template_path() -> Path:
    """Return the path to the bundled default config template."""
    return Path(__file__).resolve().parents[2] / "configs" / "default_config.yaml"


def _initialize_config_file(target: Path) -> None:
    """Seed ``target`` from the default template, stamping a fresh install UUID.

    Atomic: writes to a temp sibling then renames into place so an interrupted
    write cannot leave a partially-copied file.
    """
    template = _default_template_path()
    if not template.exists():
        raise FileNotFoundError(
            f"Default config template missing at {template}. This indicates a broken install."
        )

    engine = _yaml_engine()
    with template.open("r", encoding="utf-8") as fh:
        data = engine.load(fh)

    if not isinstance(data, CommentedMap):
        raise ValueError(
            f"Default config template at {template} did not parse as a mapping."
        )

    # Stamp a fresh install UUID so two machines that both first-run off the
    # same template still end up with distinct IDs.
    aether_block = data.get("aether")
    if isinstance(aether_block, CommentedMap):
        aether_block["user_installation_id"] = str(uuid.uuid4())

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        engine.dump(data, fh)
    os.replace(tmp, target)
    logger.info(f"Initialized Aether config at {target}")


def _load_raw_yaml(path: Path) -> CommentedMap:
    """Load the YAML file at ``path`` preserving comments; create from template if missing."""
    if not path.exists():
        logger.info(f"No config at {path}; seeding from default template")
        _initialize_config_file(path)

    engine = _yaml_engine()
    with path.open("r", encoding="utf-8") as fh:
        data = engine.load(fh)

    if data is None:
        # Empty file — treat as empty mapping so defaults apply.
        return CommentedMap()
    if not isinstance(data, CommentedMap):
        raise ValueError(
            f"{path} parsed as {type(data).__name__}, expected a YAML mapping"
        )
    return data


def _commented_map_to_plain(node: Any) -> Any:
    """Recursively convert ruamel CommentedMap/Seq into plain dict/list for Pydantic."""
    if isinstance(node, CommentedMap) or isinstance(node, dict):
        return {k: _commented_map_to_plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_commented_map_to_plain(v) for v in node]
    return node


# Module-level cache. We keep BOTH the validated model and the round-trip
# raw document so save_config() can preserve user comments.
_config_cache: AetherConfig | None = None
_raw_cache: CommentedMap | None = None
_raw_cache_path: Path | None = None


def _load_and_cache() -> tuple[AetherConfig, CommentedMap, Path]:
    """Load config from disk, validate, and populate the module caches."""
    global _config_cache, _raw_cache, _raw_cache_path

    path = get_config_path()
    raw = _load_raw_yaml(path)
    plain = _commented_map_to_plain(raw)

    try:
        cfg = AetherConfig.model_validate(plain)
    except Exception as exc:
        logger.error(f"Config at {path} failed validation: {exc!r}")
        raise

    # If the file didn't carry an installation ID (e.g. empty template on an
    # older install), stamp one and persist it so future launches are stable.
    if not cfg.aether.user_installation_id:
        cfg.aether.user_installation_id = str(uuid.uuid4())
        aether_block = raw.setdefault("aether", CommentedMap())
        if isinstance(aether_block, CommentedMap):
            aether_block["user_installation_id"] = cfg.aether.user_installation_id
        _atomic_write(path, raw)
        logger.info(f"Stamped fresh installation UUID into {path}")

    _config_cache = cfg
    _raw_cache = raw
    _raw_cache_path = path
    return cfg, raw, path


def get_config() -> AetherConfig:
    """Return the validated Aether config, loading from disk on first call."""
    if _config_cache is None:
        cfg, _, _ = _load_and_cache()
        return cfg
    return _config_cache


def _atomic_write(path: Path, data: CommentedMap) -> None:
    """Write ``data`` to ``path`` atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    engine = _yaml_engine()
    with tmp.open("w", encoding="utf-8") as fh:
        engine.dump(data, fh)
    os.replace(tmp, path)


def _merge_model_into_raw(model_dict: dict[str, Any], raw: CommentedMap) -> None:
    """Update ``raw`` in-place with values from ``model_dict``, preserving comments.

    Keys already present in ``raw`` are overwritten (preserving their attached
    comments); keys only in ``model_dict`` are appended. Recurses into nested
    mappings.
    """
    for key, value in model_dict.items():
        if isinstance(value, dict):
            existing = raw.get(key)
            if isinstance(existing, CommentedMap):
                _merge_model_into_raw(value, existing)
            else:
                nested = CommentedMap()
                _merge_model_into_raw(value, nested)
                raw[key] = nested
        else:
            raw[key] = value


def save_config(cfg: AetherConfig) -> None:
    """Persist ``cfg`` to the user config path atomically, preserving comments."""
    global _config_cache, _raw_cache, _raw_cache_path

    path = get_config_path()

    # Load the on-disk doc (or create it from template) so we can preserve
    # whatever comments/formatting the user has added.
    if _raw_cache is not None and _raw_cache_path == path:
        raw = _raw_cache
    else:
        raw = _load_raw_yaml(path)

    _merge_model_into_raw(cfg.model_dump(mode="json"), raw)
    _atomic_write(path, raw)

    _config_cache = cfg
    _raw_cache = raw
    _raw_cache_path = path
    # Invalidate legacy dict-view cache so get_yaml_config sees the new state.
    _load_yaml_dict.cache_clear()
    logger.debug(f"Saved Aether config to {path}")


def is_onboarding_complete() -> bool:
    """Return True iff the onboarding wizard has been marked complete."""
    return get_config().onboarding.complete


# ---------------------------------------------------------------------------
# Legacy dict-based accessors (kept for callers that predate AetherConfig)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_yaml_dict() -> dict[str, Any]:
    """Internal: load config as a plain dict and cache it."""
    path = get_config_path()
    raw = _load_raw_yaml(path)
    return _commented_map_to_plain(raw)


def get_yaml_config() -> dict[str, Any]:
    """Return a deep copy of the cached config as a plain dict (legacy API)."""
    return copy.deepcopy(_load_yaml_dict())


def reload_yaml_config() -> dict[str, Any]:
    """Clear caches and reload config from disk (legacy API)."""
    global _config_cache, _raw_cache, _raw_cache_path
    _config_cache = None
    _raw_cache = None
    _raw_cache_path = None
    _load_yaml_dict.cache_clear()
    return copy.deepcopy(_load_yaml_dict())
