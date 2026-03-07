# Module: Shared

Cross-cutting utilities imported by every module — types, config, logging, VRAM, and HTTP.

## Responsibility

Shared is not a runtime module and has no event handlers. It is a pure library of primitives
that all other modules import. It defines the common language (types and events) that the
EventBus carries, loads configuration from `.env` and `aether_config.yaml`, sets up
structured logging, and provides GPU memory utilities and a singleton HTTP client session.

## Key Files

- `types.py` — All shared dataclasses and enums:
  - `EventType` (StrEnum) — all valid EventBus event names (USER_MESSAGE, RESPONSE_TEXT_READY,
    TRANSCRIPT_READY, TOOL_CALL_REQUESTED, TOOL_RESULT_READY, APPROVAL_REQUESTED, and ~20 more)
  - `AetherEvent` — dataclass: `{type, data: dict, timestamp: float, source_module: str}`
  - `ConversationMessage` — dataclass: `{role: MessageRole, content, timestamp, mode}`
  - `InteractionMode` (StrEnum) — TEXT, VOICE, VIDEO
  - `MessageRole` (StrEnum) — USER, ASSISTANT, SYSTEM

- `config.py` — Config loader backed by `pydantic-settings`:
  - `get_settings()` — cached singleton `AetherSettings` loaded from `.env`. Fields include
    API keys (Anthropic, Google, ElevenLabs, Picovoice), data paths, port numbers, Ollama URL.
  - `get_yaml_config()` — cached dict from `aether_config.yaml` (LLM model names, token
    limits, feature flags).
  - `reload_yaml_config()` — clears the LRU cache and reloads from disk (called by server.py
    on SETTINGS_CHANGED events).

- `logging_config.py` — `setup_logging(log_level)`: configures loguru with colorized stderr
  output and daily rotating file logs at `logs/aether_YYYY-MM-DD.log` (30-day retention).

- `vram_manager.py` — GPU memory utilities:
  - `get_vram_stats()` — returns allocated/total/free MB and utilization ratio.
  - `free_vram_cache()` — calls `torch.cuda.empty_cache()` and logs how much was freed.
  - `check_vram_pressure()` — returns `"ok"`, `"warning"` (>85%), or `"critical"` (>95%).
    At critical threshold, automatically calls `free_vram_cache()`.

- `http_client.py` — Shared `aiohttp.ClientSession` singleton:
  - `get_shared_session()` — returns the app-lifetime session (lazy init, 30s timeout, 20
    connection pool limit). Avoids per-request session churn.
  - `close_shared_session()` — called by `shutdown.py` during graceful teardown.

## Interface Contract

Nothing in `shared/` subscribes to or publishes EventBus events.

Exported functions used across the codebase:
- `from src.shared.types import EventType, AetherEvent, ConversationMessage, InteractionMode`
- `from src.shared.config import get_settings, get_yaml_config, reload_yaml_config`
- `from src.shared.logging_config import setup_logging`
- `from src.shared.vram_manager import get_vram_stats, free_vram_cache, check_vram_pressure`
- `from src.shared.http_client import get_shared_session, close_shared_session`

## Dependencies

External packages:
- `pydantic-settings` — `.env` loading and field validation
- `pyyaml` — `aether_config.yaml` parsing
- `loguru` — structured logging
- `aiohttp` — shared async HTTP session
- `torch` — VRAM stats and cache clearing (optional; degrades gracefully if unavailable)

Other modules: none. `shared/` has zero imports from the rest of `src/`.
