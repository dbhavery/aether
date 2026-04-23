# Presence V1 Step 1 — presence.json + Settings toggles — execution report (2026-05-13)

**Status:** Shipped locally on `dev` (commit `209fca1`). Push not authorized.

## Goal

Land the first Presence V1 code slice — the config surface the
future presence controller and Trust drawer will read from. No
controller, no event capture, no UI history rendering — those stay
in later steps.

## Surfaces touched

### New config module

- **`apps/desktop/src-tauri/src/presence_config.rs`**:
  - `PresenceConfig { enabled, idle_after_s, away_after_s,
    history_in_trust_drawer }` — `#[serde(default)]` on every
    field, design-doc defaults (true / 120 / 600 / true).
  - `load_or_default(path)` — lenient; missing / malformed files
    resolve to defaults with a WARN naming the path.
  - `save(path, &cfg)` — atomic write-to-temp + rename, creates
    parent dirs as needed.
  - `config_path_for(app_data_dir)` — `<app_data>/presence.json`.
  - `DEFAULT_IDLE_AFTER_S = 120`, `DEFAULT_AWAY_AFTER_S = 600`
    exposed as public constants so the future controller can
    reference them without re-reading the doc.
- **9 tests** covering the additive-safe contract:
  - `defaults_match_design_doc`
  - `load_or_default_when_missing_returns_defaults`
  - `save_then_load_roundtrips`
  - `load_or_default_falls_back_on_malformed_json`
  - `unknown_fields_are_silently_ignored_on_read`
  - `unknown_fields_are_dropped_on_rewrite`
  - `missing_fields_fall_back_to_defaults`
  - `partial_config_preserves_provided_fields_only`
  - `config_path_for_lives_beside_app_data`

### AppState + main.rs wiring

- **`state.rs`**: new `presence_config: RwLock<PresenceConfig>`
  field + `presence_config_path: Option<PathBuf>`.
  `attach_presence_config_file`, `presence_config`, and
  `set_presence_config` accessors mirror the mic-permission
  pattern. Persistence failures surface as `Err` so the UI can
  show the user the change did not stick.
- **`main.rs`**: attaches the presence config file at boot in the
  sqlite-backend path (in-memory fallback boots without
  persistence — identical pattern to mic/media permissions).
- **`commands.rs`**: two Tauri commands —
  `get_presence_config` + `set_presence_config` (full-snapshot
  replacement, no partial-patch semantics).

### Frontend — types + api + Settings toggles

- **`types.ts`**: `PresenceConfig` interface mirroring the Rust
  struct.
- **`api.ts`**: `getPresenceConfig` + `setPresenceConfig`
  wrappers.
- **`SettingsDrawer.tsx`**: new Presence section with two
  `ToggleRow` entries:
  - "Track presence" → `enabled`
  - "Show presence in Trust history" → `history_in_trust_drawer`
  Below the toggles, a read-only line showing the current
  `idle_after_s` / `away_after_s` thresholds ("Threshold editing
  is deferred to Presence V1 step 2").
- Footer updated to list `presence.json` alongside the media and
  mic permission files.

## Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean
- `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
- `cargo test --workspace` — **133 / 133**
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **154 / 154** (was 145; +9 presence_config)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `python tools/lint-voice-doc/check.py` — OK, 48 anchors
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — 145 / 145

## Hard-constraint compliance

- **No push.** ✅
- **No L5 capability or audit-row changes.** ✅ Presence is
  observational per design §4.
- **No presence event capture / UI history rendering.** ✅ The
  Settings UI shows the two toggles + read-only threshold line;
  actual presence polling and Trust drawer history rendering are
  step 2 / step 3.
- **No new heavy dependencies.** ✅ Config uses `serde_json` /
  `fs` — already in the shell.
- **Additive-safe contract locked by tests.** ✅ Unknown fields
  tolerated on read, dropped on rewrite, malformed → defaults
  with WARN.

## Design decisions worth noting

1. **Threshold editing deferred to step 2.** Per the prompt — the
   session goal was "presence.json + Settings toggles", not "full
   presence controller". The read-only threshold line keeps the
   Settings UI honest about what's active while leaving the UI
   affordance for step 2 without adding half-finished controls.
2. **Full-snapshot `set_presence_config`.** No partial-patch on
   the wire. Simpler contract and easier for the TS side to
   express — the Settings UI always sends the full merged object.
3. **Presence config lives separately from permission files.**
   Mirrors the mic-permission split from media-permissions: the
   camera/screen consent boundary and the mic consent boundary
   are independent, and presence (observational) has its own file
   too. Keeping files narrow makes incident-response grep cleaner.
4. **Defaults match the design doc exactly** (`enabled=true`,
   `idle_after_s=120`, `away_after_s=600`,
   `history_in_trust_drawer=true`). A test locks this so a future
   "let's make this opt-in" change is a conscious edit to both
   the doc and the test.

## What is deliberately NOT in this slice

- Presence event capture / poll loop.
- OS-idle probe.
- L1 turn-state gating.
- Trust drawer history rendering of presence events.
- Presence rot guard (will land alongside the first real code
  that references the design doc's flow — likely the controller
  in step 2 or 3).
- Threshold editing controls in Settings.

## Next step

Presence V1 step 2 — presence controller (Active / Idle / Away
state machine), OS-idle probe, event emission, and threshold
editing controls in Settings. Trust drawer history rendering is
step 3. Presence rot guard is step 4.
