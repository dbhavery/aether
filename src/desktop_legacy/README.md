# Module 07: Desktop Client

PySide6 native Windows GUI — the interface the user sees and uses every day.

## Responsibility

Renders three interaction views (Chat, Voice, Video) in a dark-themed 420x650 window that
sits bottom-right on screen and stays always on top. Manages a persistent WebSocket connection
to Core (port 8765) and routes incoming server messages to the correct view. Provides a modal
settings dialog that reads and writes `aether_config.yaml` with comment preservation.

## Key Files

- `app.py` — entry point; creates `QApplication` and launches `MainWindow`
- `main_window.py` — root window; owns the `WebSocketClient`, `QStackedWidget` with four
  pages (Chat=0, Voice=1, Video=2, Tasks=3), title bar status label, and mode-switch bar
- `chat_view.py` — scrollable `ChatBubble` list with text input; emits `message_submitted`
  signal; supports interim (streaming) messages that are replaced on final response
- `voice_call_view.py` — static headshot + status indicator (idle/listening/thinking/speaking)
  + live transcript scroll area; loads portrait from `models/avatar/aether_portrait.jpg`
- `video_view.py` — full-screen MJPEG consumer; `MJPEGWorker` runs in a daemon thread,
  parses JPEG boundaries (SOI/EOI markers), and emits `frame_ready` signals to `QLabel`
- `ws_client.py` — `QWebSocket` wrapper; appends auth token to URL; auto-reconnects every
  3 s on disconnect; handles message types: `response`, `wake_word`, `avatar_stream`,
  `approval_request`, `proactive`, `error`; sends `user_message` and `approval_response`
- `settings_panel.py` — modal `QDialog`; nine config sections (Connection, Voice, Persona,
  LLM, Notifications, Memory, Security, Appearance, About); uses `ruamel.yaml` when
  available to preserve YAML comments on save; notifies server via `settings_changed` message
- `task_panel.py` — polls `task_registry.get_task_summary()` every 5 s; renders status cards
  colour-coded by state (pending/running/complete/failed); accessible via toolbar "Tasks" button
- `theme.py` — single source of truth for the design system; defines palette constants and
  QSS helper functions (`input_qss`, `send_button_qss`, `mode_button_qss`)

## Interface Contract

**Sends to Core (port 8765):**
- `{type: "user_message", text: str, timestamp: ISO8601}` — user text input
- `{type: "approval_response", approval_id: str, approved: bool}` — gate approval
- `{type: "settings_changed"}` — notifies server after config save
- `{type: "ping"}` — heartbeat

**Receives from Core:**
- `{type: "response", text: str, is_interim: bool}` — Aether's reply
- `{type: "wake_word"}` — sets status label to "Listening..."
- `{type: "avatar_stream", url: str, available: bool}` — unlocks Video view
- `{type: "approval_request", approval_id: str, description: str, action: str}`

**Signals (internal Qt):**
- `WebSocketClient.connected / disconnected / message_received / error_occurred`
- `ChatView.message_submitted(str)`

## Dependencies

**External packages:**
- `PySide6` 6.10.2 — widgets, WebSockets, signals/slots
- `PySide6.QtWebSockets` — `QWebSocket`
- `loguru` — logging
- `ruamel.yaml` — comment-preserving YAML (optional; falls back to `pyyaml`)
- `sounddevice` — audio device enumeration in settings (optional; falls back gracefully)

**Internal modules:**
- `src.core.auth` — `get_token_for_client()` for WebSocket auth token
- `src.agents.task_registry` — `get_task_summary()`, `clear_completed_tasks()` for TaskPanel
- `src.shared.config` — not used directly by desktop; config path is `aether_config.yaml`
