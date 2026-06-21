# Aether v1.0 Architecture

**Applies to:** `dev` branch productization work.
**Supersedes:** the PySide6-only architecture documented in the root `README.md` (which describes the `master` snapshot).
**See also:** `PRODUCT-PLAN.md`, `PERSONA-SCHEMA.md`, `ONBOARDING-SPEC.md`, `LLM-PROVIDERS.md`.

---

## 1. Process topology

```
                        User's machine
+-----------------------------------------------------------------+
|                                                                 |
|   +-------------------------+     +---------------------------+ |
|   |  Desktop Shell          |     |  Backend (Python 3.13)    | |
|   |  (pywebview + WebView2) |     |                           | |
|   |                         |     |  FastAPI + websockets     | |
|   |  Loads static Next.js   |     |  :8765  WebSocket         | |
|   |  bundle from            |     |  :8767  Health            | |
|   |  frontend/out/          |     |  :8770  Avatar MJPEG      | |
|   |                         |     |                           | |
|   |  ws://localhost:8765 <--+-----+--> EventBus + modules     | |
|   |  http://localhost:8770 -+-----+--> Avatar frame stream    | |
|   +-------------------------+     +---------------------------+ |
|                                                                 |
|   +----------------------------------+                          |
|   |  User data (%APPDATA%/aether/)   |                          |
|   |                                  |                          |
|   |  config.yaml                     |                          |
|   |  secrets.enc  (OS keyring index) |                          |
|   |  chroma/                         |                          |
|   |  logs/                           |                          |
|   |  models/      (downloaded)       |                          |
|   |  personas/    (active overrides) |                          |
|   +----------------------------------+                          |
|                                                                 |
+-----------------------------------------------------------------+

                         Cloud (optional)
+-----------------------------------------------------------------+
|  Anthropic  OpenAI  Google  Groq  OpenRouter  ElevenLabs        |
|  (only when user has configured keys — default is local-only)   |
+-----------------------------------------------------------------+
```

Two OS processes on the user's machine:
1. **Backend** — Python, headless, owns all models, database, LLM calls, audio IO, avatar rendering.
2. **Desktop shell** — pywebview window hosting a WebView2 instance that loads the Next.js static export. All UI runs in the web view; backend talks to it over localhost WebSocket.

Rationale: the same Next.js bundle can be deployed to the portfolio website (the live widget), so **one UI codebase serves two surfaces** — desktop and web.

The legacy PySide6 app under `src/desktop_legacy/` (renamed from `src/desktop/` in P1) still boots via `python -m src.desktop_legacy.app` but is not the v1.0 product UI. It stays for historical/showcase purposes only.

---

## 2. Directory layout (target state after P1–P2)

```
aether/
├── src/                              Python backend
│   ├── main.py                       Entry point (boots WS server, modules)
│   ├── core/                         WebSocket, EventBus, health, auth, rate limiting
│   ├── shared/                       Config, types, logging, HTTP client, paths
│   ├── voice/                        STT, TTS, VAD, audio IO (no speaker verify, no wake word)
│   ├── avatar/                       LivePortrait engine, compositor, idle animator, MJPEG server
│   ├── brain/                        LLM router using litellm, prompt construction, persona application
│   ├── memory/                       ChromaDB hybrid search, per-persona isolation
│   ├── personas/                     Loader + validator for persona packs
│   ├── onboarding/                   Wizard state machine + config writer (server-side validation)
│   └── desktop_legacy/               Former PySide6 app (read-only, not shipped in v1.0 installer)
│
├── frontend/                         Next.js 15 + React 19 + TypeScript
│   ├── app/                          App router
│   │   ├── (chat)/                   Chat mode route
│   │   ├── (sandbox)/                Settings / sandbox route
│   │   ├── (video)/                  Video mode route
│   │   ├── (onboarding)/             Wizard routes
│   │   └── layout.tsx                Shared shell, theme provider
│   ├── components/                   Reusable UI primitives
│   ├── lib/
│   │   ├── ws.ts                     WebSocket client matching backend :8765 protocol
│   │   ├── mjpeg.ts                  MJPEG stream consumer for video mode
│   │   └── config.ts                 Settings reader/writer (via backend API)
│   ├── design/                       Tokens, theme, shadcn overrides
│   └── public/                       Static assets
│
├── desktop/                          pywebview shell
│   ├── main.py                       Launches webview window pointing at frontend/out/
│   ├── bridge.py                     JS-Python bridge for native file dialogs, keyring
│   └── installer/                    Inno Setup scripts
│
├── personas/                         Bundled persona packs
│   ├── SCHEMA.md                     Canonical schema (see PERSONA-SCHEMA.md)
│   ├── _example/                     Reference persona showing required structure
│   ├── aurora/
│   ├── caelum/
│   └── ...                           (10–12 total by P4)
│
├── scripts/
│   ├── persona_generator/            Tools to generate a new persona pack
│   └── preprocess_avatar.py          Landmark extraction, crop verification
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/                          Playwright end-to-end against full stack
│
├── docs/                             This directory
│
├── RUNWAY.md                         Session-to-session handoff
├── LICENSE                           MIT (unchanged)
├── PRIVACY.md                        (added in P5)
├── TERMS.md                          (added in P5)
├── README.md                         Public-facing (updated in P5)
├── pyproject.toml                    Python dependencies
├── package.json                      (added in P2 for frontend)
└── aether_config.yaml               Default config
```

---

## 3. Port assignments

| Port | Purpose | Bound to | Exposed outside localhost? |
|-----:|---------|----------|:--------------------------:|
| 3000 | Next.js dev server | 127.0.0.1 | No (dev-time only) |
| 8765 | Main WebSocket (UI ↔ backend) | 127.0.0.1 | No |
| 8766 | Data REST API (optional) | 127.0.0.1 | No |
| 8767 | Health endpoint | 127.0.0.1 | No |
| 8770 | Avatar MJPEG stream | 127.0.0.1 | No |

All loopback-only. No LAN exposure in v1.0. The Tailscale pattern from the upstream codebase is **deferred** — if users want it later, they run Tailscale themselves and we add an explicit "allow LAN" config flag in a future version.

---

## 4. Module responsibilities and interface contracts

### 4.1 Core (`src/core/`)
- WebSocket server on :8765, EventBus, health, auth (no-op in v1.0 — local only), shutdown.
- Startup orchestration: boots modules in order, waits for MODULE_READY events.
- **Interface:** `event_bus.subscribe(type, handler)`, `event_bus.publish(event)`.

### 4.2 Shared (`src/shared/`)
- Config loader reads `aether_config.yaml` + env overrides.
- `paths.py` — all file paths derived from `AETHER_DATA_DIR` (default `%APPDATA%/aether/`). **No hardcoded paths anywhere else in the codebase.**
- Types: `EventType` enum, `AetherEvent` dataclass.
- Logging: structured loguru.

### 4.3 Voice (`src/voice/`)
- **Input:** audio capture (sounddevice), Silero VAD, faster-whisper STT.
- **Output:** Chatterbox Turbo local TTS, ElevenLabs cloud fallback if configured.
- **Removed from the upstream codebase:** Porcupine wake word, ECAPA-TDNN speaker verification, owner-specific reference voice.
- **Trigger:** push-to-talk event from frontend (hold spacebar → USER_SPEECH_START → USER_SPEECH_END).
- **Events:** USER_SPEECH_START, USER_SPEECH_END, TRANSCRIPT_READY, RESPONSE_AUDIO_CHUNK, RESPONSE_AUDIO_END.

### 4.4 Avatar (`src/avatar/`)
- LivePortrait engine only (v1.0). Other engines stay in the upstream codebase, dormant here.
- MJPEG server on :8770.
- Idle animator with blink, state transitions, micro-movements.
- Compositor for face paste-back on reference images.
- **Events in:** AVATAR_STATE_CHANGED (from brain/voice), RESPONSE_AUDIO_CHUNK (for lip-sync).
- **Events out:** AVATAR_FRAME_READY (internal), MODULE_READY.

### 4.5 Brain (`src/brain/`)
- Receives TRANSCRIPT_READY or USER_MESSAGE, calls LLM via litellm, emits RESPONSE_TEXT_READY.
- LLM selection: unified provider abstraction (see LLM-PROVIDERS.md).
- Prompt construction: base prompt + persona prompt (from active persona pack) + recent memory context.
- Streaming: emits RESPONSE_TEXT_CHUNK events; frontend assembles.
- **Acknowledgment phrases** pool (from spec): when a tier-switch or long-running call is detected, brain emits a short filler via the fast local tier while the slow call streams — exact pool defined in persona's `voice.yaml`.

### 4.6 Memory (`src/memory/`)
- ChromaDB at `%APPDATA%/aether/chroma/<persona_id>/` — one collection per persona for isolation.
- Hybrid search: BM25 + dense vectors (nomic-embed-text via Ollama, or configurable).
- Conversation history in SQLite at `%APPDATA%/aether/conversations.db`.
- Exposes: `search(query, persona_id)`, `store_turn(role, content, persona_id)`, `store_fact(key, value, importance, persona_id)`, `clear_persona(persona_id)`.

### 4.7 Personas (`src/personas/`)
- Loader scans `personas/` directory, validates each pack against schema, returns `PersonaManifest` objects.
- Active persona cached; switching fires PERSONA_CHANGED event so other modules reload voice/avatar.
- User-created personas under `%APPDATA%/aether/personas/` override bundled ones with the same ID.

### 4.8 Onboarding (`src/onboarding/`)
- State machine mirroring the 7 wizard screens.
- Validates API keys by making one real test call per provider.
- Writes config atomically (temp file → rename) when wizard completes.

---

## 5. Events catalog (additions beyond upstream)

Events unchanged from the upstream codebase: USER_MESSAGE, TRANSCRIPT_READY, RESPONSE_TEXT_READY, RESPONSE_TEXT_CHUNK, RESPONSE_AUDIO_CHUNK, RESPONSE_START, RESPONSE_END, AVATAR_STATE_CHANGED, MODULE_READY.

Events added for v1.0:
- `USER_SPEECH_START` / `USER_SPEECH_END` — push-to-talk events (replaces wake_word_detected + Silero auto-detect).
- `PERSONA_CHANGED` — fires when user switches active persona in sandbox mode; data: `{persona_id: str, previous_id: str}`.
- `PROVIDER_CHANGED` — user changed LLM/voice provider mid-session.
- `ONBOARDING_STEP` — wizard progress events (for analytics if telemetry is on).

Events removed (from upstream):
- `WAKE_WORD_DETECTED` — not emitted in v1.0.
- `SPEAKER_VERIFIED` — not emitted (speaker verify disabled by default).

---

## 6. Config schema sketch

`%APPDATA%/aether/config.yaml`:

```yaml
aether:
  version: 1
  user_installation_id: "<uuid4, generated at install, used for telemetry grouping if enabled>"
  telemetry:
    enabled: false
    crash_reports: false

persona:
  active: "aurora"
  display_name: "Aurora"       # user-editable, defaults to persona canonical name

llm:
  provider: "anthropic"        # anthropic | openai | google | groq | openrouter | ollama
  tier_map:
    fast:  "ollama/qwen2.5:7b"
    main:  "claude-sonnet-4-6"
    heavy: "claude-opus-4-6"
  # Keys stored separately in OS keyring under service name "aether.<provider>"

voice:
  mode: "local"                # local | elevenlabs | off
  stt_model: "faster-whisper-base.en"
  tts_model: "chatterbox-turbo"
  device: "default"            # audio device name from sounddevice

ui:
  theme: "dark"
  always_on_top: false
  window_position: [x, y]      # persisted
  window_size: [w, h]

memory:
  enabled: true
  max_history_turns: 200
  retrieval_top_k: 5

avatar:
  engine: "liveportrait"       # only option in v1.0
  fps_target: 25
  quality: "standard"          # standard | high (high = more VRAM)
```

All secrets live in the OS keyring (Windows Credential Manager via the `keyring` Python lib), not in the YAML. Config file is human-readable and safe to commit to screenshots.

---

## 7. Technology choices and rationale

| Layer | Choice | Why |
|-------|--------|-----|
| Backend language | Python 3.13 | Matches the upstream codebase. Rewriting to Rust is a v2 task. |
| HTTP/WS server | FastAPI + websockets + uvicorn | Already in deps, well-supported, typed. |
| Frontend framework | Next.js 15 (App Router) + React 19 | Matches portfolio stack. Static export works for both pywebview and web. |
| Styling | Tailwind v4 | Fast iteration, consistent with portfolio. |
| Component primitives | shadcn/ui where appropriate | Headless, accessible, easy to theme. |
| State | Zustand for app state; React Query for server-state. | Simple, proven. |
| Desktop shell | pywebview + WebView2 | Don's locked rule. Cross-platform story: WebView2 on Windows, WKWebView on macOS, WebKit on Linux. |
| LLM abstraction | litellm | 100+ providers via one interface. |
| STT local | faster-whisper (distil-large-v3 on GPU, base.en on CPU fallback) | Upstream already uses it. |
| TTS local | Chatterbox Turbo | Upstream already uses it. Supports voice cloning from short references. |
| VAD | Silero | Upstream already uses it. Lightweight. |
| Avatar | LivePortrait (TensorRT) | Best quality/VRAM for headshots. |
| Memory | ChromaDB 1.5.2 | Upstream already uses it. Hybrid search built in. |
| Embeddings | nomic-embed-text via Ollama (default) or user-configurable | Local, free, good quality. |
| Installer (Windows) | Inno Setup | Upstream already has scaffold. |
| Auto-update | Custom updater checking GitHub Releases | No third-party dep; source-verifiable. |

---

## 8. Coexistence with legacy

`src/desktop_legacy/` keeps working. Someone can still run `python -m src.desktop_legacy.app` against the backend and get the PySide6 UI. This is useful for:
- Regression testing during P1 port.
- Don's personal daily-driver use if he prefers it.
- Demonstrating that the backend is truly UI-agnostic.

It will **not** be packaged in the v1.0 installer. It is a development artifact, not a product surface.

---

## 9. Cross-platform considerations

v1.0 ships Windows-only. macOS and Linux are **code-ready** (Python is cross-platform, pywebview supports all three) but not tested or packaged. P7 (post-launch) spin-up on macOS and Linux if there's demand.

Paths in `src/shared/paths.py` use `platformdirs` to get the right per-OS directory. No hardcoded `%APPDATA%` anywhere — it's always `user_data_dir("aether")`.
