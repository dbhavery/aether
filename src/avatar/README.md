# Module 06: Avatar

Thin connector between the Aether server and a separately-running animated face backend.

## Responsibility

The avatar module does not run any ML inference itself. It manages the lifecycle of an
external avatar process (PersonaLive preferred, LivePortrait as fallback), monitors its health
on port 8770, and signals the desktop client with the MJPEG stream URL when the backend is
ready. It also listens for `RESPONSE_TEXT_READY` events on the EventBus so it can toggle the
backend's speaking state as Aether talks. If no backend is available the system degrades
silently — the Video view shows a placeholder and nothing else breaks.

## Key Files

- `client.py` — `AvatarClient` singleton; wraps the LivePortrait REST API; exposes
  `check_health() -> bool`, `set_speaking(bool)`, `stream_url`, and `available` properties;
  reads `avatar.liveportrait_url` and `avatar.stream_url` from `aether_config.yaml`
- `handler.py` — EventBus subscriber functions; `initialize_avatar()` calls `check_health()`
  at startup and publishes a `MODULE_READY` event with `stream_url` when available;
  `on_response_ready()` calls `set_speaking(True)` on final (non-interim) responses;
  `register_avatar_handlers()` wires `RESPONSE_TEXT_READY` to `on_response_ready`
- `server.py` — `start_avatar_server()` coroutine called by `startup.py`; tries PersonaLive
  at `~\Projects\personalive\aether_server.py` first, then falls back to
  LivePortrait at `models\liveportrait\liveportrait_server.py`; polls `/health` every 2 s
  up to 45 s (PersonaLive) or 30 s (LivePortrait) before giving up; returns engine name string

## Interface Contract

**Publishes (EventBus):**
- `MODULE_READY` — `{module: "avatar", stream_url: str, available: bool}` — broadcast at
  startup when backend is confirmed healthy; Core WS server relays this to desktop clients
  as `{type: "avatar_stream", url: str, available: true}`

**Subscribes (EventBus):**
- `RESPONSE_TEXT_READY` — calls `AvatarClient.set_speaking(True)` on non-interim events

**REST calls made by this module (outbound):**
- `GET  http://localhost:8770/health` — health probe; expects `{status: "ok"|"loading"}`
- `POST http://localhost:8770/speaking` — body `{speaking: bool}`; fire-and-forget, 1 s timeout

**Exports (importable functions):**
- `get_avatar_client() -> AvatarClient` — singleton accessor
- `register_avatar_handlers()` — called by startup to wire EventBus subscriptions
- `start_avatar_server() -> str` — called by `startup.py`; returns engine name or `"none"`

## Dependencies

**External packages:**
- `aiohttp` — async HTTP client in `AvatarClient`
- `httpx` — async HTTP client in `server.py` health polling
- `loguru` — logging

**Internal modules:**
- `src.core.events` — `event_bus` pub/sub
- `src.core.health` — `register_module()`, `update_module_status()`
- `src.shared.config` — `get_yaml_config()` for avatar config block
- `src.shared.types` — `EventType`, `AetherEvent`
