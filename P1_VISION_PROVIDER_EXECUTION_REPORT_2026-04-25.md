# P1 — Vision-capable provider behind analyze_frame (2026-04-25, late evening)

## Goal

Make `analyze_frame` actually multimodal: when a vision provider is
configured, the model sees the pixels. When none is configured, the
existing text-only behaviour stays as a safe fallback. Audit, memory,
permission gate, and capability tagging all unchanged.

## What shipped

### L4 — `packages/l4-router/src/vision.rs` (new)

- `struct VisionRequest { cue, image_b64, mime }` — owned, base64
  body without `data:` prefix.
- `struct VisionResponse { text, prompt_tokens, completion_tokens }`.
- `trait VisionProvider: Send + Sync { id, label, healthcheck, analyze }`.
- `fn split_data_url(data_url) -> Result<(mime, body)>` helper.
- 6 unit tests cover the data-URL parser end to end.

### L4 — `packages/l4-router/src/providers/ollama_vision.rs` (new)

- `struct OllamaVisionConfig { base_url, model, timeout_ms }`. Default
  timeout 120 s (vision is slower than text).
- `OllamaVisionConfig::from_env() -> Option<Result<…>>` — returns
  `None` when `AETHER_OLLAMA_VISION_MODEL` is unset (the opt-in
  signal); returns `Some(Err(_))` only when the env is present but
  malformed. Inherits `AETHER_OLLAMA_BASE_URL` when
  `AETHER_OLLAMA_VISION_BASE_URL` is unset.
- `struct OllamaVisionProvider` — `VisionProvider` impl using
  `/api/chat` with the `images` array per Ollama spec.
- `build_vision_payload` and `parse_vision_response` exposed for tests.
- 8 unit tests: env on/off, base-URL inheritance, malformed timeout,
  payload shape, response parse with/without token counts, response
  parse failure, empty-image rejection.

### L4 — `lib.rs`, `providers/mod.rs`

- `vision` module always registered.
- Ollama vision adapter re-exported under the existing
  `ollama-provider` feature.

### Shell — `apps/desktop/src-tauri/src/state.rs`

- `AppState` carries `Option<Arc<dyn VisionProvider>>`.
- `attach_vision_provider`, `vision_provider`, `vision_provider_label`
  accessors. `attach_vision_provider` is `#[allow(dead_code)]` because
  it's only invoked under the `ollama-provider` feature.

### Shell — `apps/desktop/src-tauri/src/main.rs`

- New `attach_vision_provider_if_configured` helper, feature-gated.
  Reads `OllamaVisionConfig::from_env`, builds the provider, runs the
  daemon healthcheck, and only attaches when both succeed.
  Tracing logs the outcome (`info` on attach, `warn` on fall back).
- Called from both the durable + in-memory boot paths.

### Shell — `apps/desktop/src-tauri/src/commands.rs`

- `vision_status` command + `VisionStatus { enabled, label }` struct
  for the UI to surface the active vision provider.
- `analyze_frame` flow now:
  1. permission gate (unchanged),
  2. policy/audit through `TurnEngine` (unchanged — keeps the L5
     audit row for `MediaCamera` / `MediaScreenCapture`),
  3. **new:** `maybe_apply_vision` — if a vision provider is
     attached AND policy allowed a route, decode the data URL,
     call `provider.analyze`, and substitute `route.response_text`
     + provider/tier metadata + token counts.
- Failure modes (no provider, malformed URL, daemon error) leave the
  text-only output as a clean fallback.

### Frontend — `lib/types.ts`, `lib/api.ts`

- `VisionStatus` type + `visionStatus()` typed wrapper.

### Frontend — `apps/desktop/src/components/VisionBadge.tsx` (new)

- Tiny status badge — green when a vision provider is attached
  (shows the label), neutral when not (shows the env var to set).
- Rendered in both `CameraPanel` and `ScreenPanel` next to the
  Analyze button so users always know which path is live.

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test --workspace` — all green.
- `cargo test -p aether-l4-router --features ollama-provider` —
  **35 passed** (was 21; +14 new vision tests).
- `apps/desktop/src-tauri && cargo test` — 37/37 default,
  43/43 with `ollama-provider`.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `apps/desktop && pnpm typecheck && pnpm build` — clean.

## Key decisions for review

1. **No new feature flag.** Vision rides on the existing
   `ollama-provider` feature because it talks to the same daemon
   over the same endpoint. Keeps the build matrix small. Env-only
   opt-in (`AETHER_OLLAMA_VISION_MODEL`) is the runtime gate.
2. **Vision substitutes text output instead of replacing the engine
   call.** `analyze_frame` still calls `TurnEngine::handle_turn`
   so the L5 audit row + telemetry + memory writes are unchanged.
   When vision is available, only the assistant text + provider
   label change. Trade-off: one extra text-model call (or reflex
   stub) per frame turn; benefit: zero policy-engine changes
   needed, full audit story preserved.
3. **Image bytes are NEVER persisted.** `image_b64` flows
   request → provider only. Memory stores the cue text + assistant
   reply, never the data URL. SQLite stays small.
4. **Data URL enters the IPC; the trait gets raw base64.**
   `split_data_url` is the seam. Adapters that need the prefix can
   reattach locally; the trait surface stays small.
5. **Vision provider id (`"ollama-vision"`) is distinct from text
   (`"ollama"`)** so the Trust drawer's History tab (and the new
   media filter — see P3 report) can distinguish vision-served
   turns from text-served turns.

## What remains on the multimodal track

- Native (Rust-side) capture path for camera + screen — would let
  the daemon-less workflow capture without a webview round trip.
  Lower priority; the current webview path covers the foundation.
- Tool-call dispatch on top of vision — letting the model invoke a
  follow-up search / write based on what it saw. Out of scope until
  the L5 tool-call work lands.
- Multi-frame / video — explicitly NOT in scope per session rules.
