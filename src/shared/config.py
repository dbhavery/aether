"""Config loader — reads .env and aether_config.yaml. Zero hardcoded values."""

import copy
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AetherSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field("", validation_alias="ANTHROPIC_API_KEY")
    google_api_key: str = Field("", validation_alias="GOOGLE_API_KEY")
    elevenlabs_api_key: str = Field("", validation_alias="ELEVENLABS_API_KEY")
    picovoice_access_key: str = Field("", validation_alias="PICOVOICE_ACCESS_KEY")
    aether_data_path: str = Field("./data", validation_alias="AETHER_DATA_PATH")
    chroma_path: str = Field("./data/chroma", validation_alias="CHROMA_PATH")
    obsidian_vault: str = Field("./docs/vault", validation_alias="OBSIDIAN_VAULT")
    websocket_port: int = Field(8765, validation_alias="WEBSOCKET_PORT")
    health_port: int = Field(8767, validation_alias="HEALTH_PORT")
    data_server_port: int = Field(8766, validation_alias="DATA_SERVER_PORT")
    server_host: str = Field("127.0.0.1", validation_alias="SERVER_HOST")
    ollama_base_url: str = Field("http://localhost:11434", validation_alias="OLLAMA_BASE_URL")
    android_device_token: str = Field("", validation_alias="ANDROID_DEVICE_TOKEN")
    log_level: str = Field("DEBUG", validation_alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> AetherSettings:
    return AetherSettings()


@lru_cache(maxsize=1)
def _load_yaml_config() -> dict:
    """Internal: load and cache the raw YAML config (immutable reference)."""
    # Resolve relative to project root (2 levels up from src/shared/config.py)
    config_path = Path(__file__).resolve().parent.parent.parent / "aether_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"aether_config.yaml not found at {config_path}")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"aether_config.yaml is empty or invalid (parsed as {type(data).__name__})")
    return data


def get_yaml_config() -> dict:
    """Return a deep copy of the cached config — safe to mutate without corrupting the cache."""
    return copy.deepcopy(_load_yaml_config())


def reload_yaml_config() -> dict:
    """Clear cached config and reload from disk. Call after settings changes."""
    _load_yaml_config.cache_clear()
    return copy.deepcopy(_load_yaml_config())
