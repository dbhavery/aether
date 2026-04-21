# Follow-up — MediaAnalyze capability + screen capture (2026-04-25, evening)

Picks up where the multimodal-foundation handoff left off. Two of the
three "next-session" priorities completed; the vision-provider
priority is deferred because it requires a new model adapter pass
that wasn't in scope for this run.

## Commits

```
b410f7b feat(l5,apps/desktop): wire MediaCamera/MediaScreenCapture through analyze_frame
c430fb4 feat(apps/desktop): screen-capture panel reusing analyze_frame pipeline
```

## What changed

### L5 — `packages/l5-policy/src/engine.rs`

- `EngineConfig::wave3_default` now declares `MediaCamera` and
  `MediaScreenCapture` capabilities at `ApprovalMode::Auto` /
  `RiskClass::Medium`. Auto (not Ask) because the shell-side
  `media_permissions.json` gate is the user-facing per-device
  control; an L5 modal would double-prompt without changing the
  trust story.
- `default_risk_for` extended for the same media capabilities so
  persona overlays land at the right risk class.
- New test `wave3_default_grants_media_capabilities_at_medium_risk`
  locks the contract.

### Shell — `apps/desktop/src-tauri/src/commands.rs`

- `analyze_frame` now selects `Capability::MediaCamera` or
  `Capability::MediaScreenCapture` based on the request kind
  instead of the FilesRead placeholder. Audit rows now read
  `media.camera` / `media.screen_capture` in the Trust drawer.

### Frontend — `apps/desktop/src/components/ScreenPanel.tsx` (new)

- Right-side drawer mirroring CameraPanel.
- Wraps `navigator.mediaDevices.getDisplayMedia` (the standard
  browser screen-capture API) so the OS source picker drives
  selection — Aether never enumerates open windows itself.
- Same in-app permission gate (`screen` device); same
  start/stop/sample-frame model; same `analyze_frame` pipeline.
- Listens for the OS-level "Stop sharing" track end so local
  state stays in sync with the browser's screen-share toolbar.
- One screenshot per click. No continuous watching.

### Header / App wiring

- `Header.tsx` gains a "Screen" button next to "Camera".
- `App.tsx` widens the `drawer` discriminant to include `"screen"`
  and renders the new panel with the same `onFrameAnalyzed`
  handler as the camera path.

## Verification

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test --workspace` — all green.
- `cargo test -p aether-l5-policy` — 12/12 (was 11; +1 new media
  defaults test).
- `apps/desktop/src-tauri && cargo test` — 37/37.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `apps/desktop && pnpm typecheck && pnpm build` — clean.

## What's left on the multimodal track

1. **Vision-capable provider behind `analyze_frame`.** Today the data
   URL is validated and discarded server-side; the active provider
   stack is text-only. Wiring a vision-aware route (Ollama vision
   model, llama.cpp vision, or a remote provider) is the next big
   piece. The command surface is already correct — when the provider
   lands, swap the request envelope to carry the data URL.
2. **Tauri capability allowlist hardening.** `getUserMedia` and
   `getDisplayMedia` are currently permissive. Audit the Tauri
   `tauri.conf.json` capabilities before distribution.
3. **Telemetry filter UI.** Frame turns mix into the History tab.
   A "show frame turns only" toggle would help reviewers.
4. **Microphone consent (parallel track).** Out of scope for this
   foundation; mirror the model used here when the voice/STT path
   lands.
