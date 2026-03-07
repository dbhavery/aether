# Module 01: Core

Infrastructure backbone — WebSocket server, EventBus, config, health, and process supervision.

## Responsibility

Core provides the foundational layer that every other module depends on. It runs the WebSocket
server on port 8765 that connects all clients (desktop, Android), the EventBus that decouples
all inter-module communication, and the HTTP health endpoint on port 8767. It also orchestrates
startup sequencing and manages graceful shutdown on SIGTERM/SIGINT.

## Key Files

- `server.py` — WebSocket server (port 8765): authenticates clients, enforces rate limits (20
  msg/min via token bucket), routes incoming messages to EventBus events, and broadcasts
  responses and approval requests back to all connected clients. Max 10 simultaneous clients.
- `events.py` — EventBus singleton (`event_bus`): async pub/sub backbone. All modules
  communicate exclusively through this. Zero direct cross-module imports are permitted.
- `auth.py` — WebSocket token auth: generates a 64-char hex secret on first run, stores it at
  `./data\ws_token.txt`, verifies tokens with constant-time comparison.
- `health.py` — FastAPI app on port 8767: `GET /health` returns module statuses, Ollama
  reachability, GPU VRAM usage, and I: drive free space. `GET /ping` returns `{pong: true}`.
- `startup.py` — Startup orchestrator: sets up logging, registers all module handlers in order
  (memory, brain, tools, voice, TTS, avatar, notifications, persona, data server), then runs
  the health server, data server, and WebSocket server concurrently via `asyncio.gather`.
- `shutdown.py` — Graceful shutdown: ordered teardown — stops voice pipeline, flushes
  scheduler, closes shared HTTP session, clears GPU cache.
- `watchdog.py` — Process supervisor: polls `/health` every 15 seconds. After 5 consecutive
  failures, kills and restarts the server process with exponential backoff (max 5 min, max 10
  attempts). Sends a Windows toast notification on crash via `winotify`.
- `rate_limiter.py` — Token bucket rate limiter: 20 messages per 60 seconds per connection ID.

## Interface Contract

EventBus subscriptions (server.py listens to these and broadcasts to clients):
- `RESPONSE_TEXT_READY` -> broadcasts `{type: "response", text, emotion, timestamp, is_interim}`
- `WAKE_WORD_DETECTED` -> broadcasts `{type: "wake_word", listening: true}`
- `MODULE_READY` -> broadcasts avatar stream URL when avatar module is ready
- `PROACTIVE_MESSAGE` -> broadcasts `{type: "proactive", text, category, timestamp}`
- `SETTINGS_CHANGED` -> reloads `aether_config.yaml` from disk
- `APPROVAL_REQUESTED` -> broadcasts `{type: "approval_request", approval_id, action, description, risk}`

EventBus events published by server.py:
- `USER_MESSAGE` — from `{type: "message"}` or `{type: "user_message"}` WebSocket frames
- `SETTINGS_CHANGED` — from `{type: "settings_changed"}` WebSocket frames

Health module exports:
- `register_module(name, status)` — called by each module at startup
- `update_module_status(name, status)` — called when status changes to "ready"
- `GET /health` — `{status, uptime_seconds, modules: {name: status}, dependencies: {ollama, gpu, storage_i}}`

## Dependencies

External packages:
- `websockets` — WebSocket server
- `fastapi` + `uvicorn` — health HTTP server
- `loguru` — structured logging
- `httpx` — watchdog health polling
- `pydantic-settings` + `pyyaml` — config loading (in `src/shared/`)
- `winotify` — crash toast notifications (optional)
- `torch` — GPU cache clearing on shutdown (optional)

Other modules:
- `src/shared/` — `AetherEvent`, `EventType`, `get_settings()`, logging setup
- `src/tools/approval_gate` — resolves user approval responses
