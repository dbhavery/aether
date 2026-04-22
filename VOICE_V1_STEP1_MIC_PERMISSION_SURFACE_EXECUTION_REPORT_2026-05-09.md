# Voice V1 Step 1 — mic permission surface — execution report (2026-05-09)

**Status:** Shipped locally on `dev`. Push not authorized.
**Scope:** Permission-config surface only. **No audio capture.**

## Goal

Land the smallest usable slice of Voice V1: a tri-state mic-permission
surface that mirrors the camera/screen pattern. Nothing records audio,
nothing transcribes. This is the shell-level consent record that
future capture sites (`transcribe_utterance`, step 4) must consult
before touching the microphone.

## Surfaces touched

### Rust — shell

- `apps/desktop/src-tauri/src/mic_permissions.rs` (new, 285 lines
  including tests). Mirrors `media_permissions.rs` section-by-section
  but with single-state semantics (the mic is one surface, not two
  devices).
- `apps/desktop/src-tauri/src/state.rs`:
  - `mic_permission: RwLock<MicPermission>` and
    `mic_permission_path: Option<PathBuf>` fields on `AppState`.
  - Default wiring in `build`.
  - Public API: `attach_mic_permission_file`, `mic_permission`,
    `set_mic_permission`, `evaluate_mic_permission`.
  - `set_mic_permission` emits a tracing INFO line on state change
    (`mic permission: ask -> allow`) for local observability. No
    L5 `AuditRecordEvent` is emitted here — see "Audit posture"
    below.
- `apps/desktop/src-tauri/src/commands.rs`:
  - `get_mic_permission` and `set_mic_permission` Tauri commands.
  - Same `state_value` parameter naming as `set_media_permission`
    to dodge the `State<T>` extractor collision.
- `apps/desktop/src-tauri/src/main.rs`:
  - `mod mic_permissions;`
  - Both new commands registered in the invoke handler.
  - `<app_data>/mic_permissions.json` path wired into AppState at
    boot (behind the `sqlite-backend` feature, alongside media
    permissions).

### TypeScript — frontend

- `apps/desktop/src/lib/types.ts`: new `MicPermission` interface.
  The tri-state vocabulary is shared with `MediaPermissionState` —
  the mic does not invent new states.
- `apps/desktop/src/lib/api.ts`: `getMicPermission` /
  `setMicPermission` wrappers.
- `apps/desktop/src/components/SettingsDrawer.tsx`: new "Microphone"
  section below the Media section, using the same `PermissionRow`
  component. Footer updated to list both persistence files.

## Config contract — `mic_permissions.json`

Path: `<app_data>/mic_permissions.json`.

Shape:

```json
{ "state": "ask" }
```

Contract (identical to `vision_provider.json` + `media_permissions.json`):

- **Additive** — new fields may be added by future builds.
- **Default-safe on read** — `state` has `#[serde(default)]`, so an
  empty `{}` loads as `Ask`.
- **Unknown fields silently ignored on read** — no
  `#[serde(deny_unknown_fields)]`.
- **Unknown fields dropped on rewrite** — no `serde(flatten)` extras
  bag. Documented limitation; locked by test
  (`mic_permissions::tests::unknown_fields_are_dropped_on_rewrite`).
- **Malformed JSON → default + WARN naming the path** — the shell
  still boots cleanly.
- **Single-writer through `AppState::set_mic_permission`.**
- **Atomic writes** — write-to-temp + rename, so a crash mid-write
  cannot leave a half-written file.

## Audit posture

The session prompt called for an "audit event" on `set_mic_permission`.
Investigation revealed the existing `set_media_permission` path does
**not** emit an `AuditRecordEvent`. L5 `AuditRecordEvent`s are emitted
by capture sites (the turn engine during `analyze_frame`), not by
permission-toggle commands.

Adding a hand-rolled audit write from the shell would either:

- require extending L5 contracts (blocked by hard constraint "Change
  L5 audit event types without updating architecture docs and adding
  tests"), or
- couple the shell to L5 internals asymmetrically with the media
  surface (inconsistent, harder to review).

**Decision:** mirror `set_media_permission` exactly. Emit a tracing
INFO line on state change for local observability and defer audit
coverage to step 4 (`transcribe_utterance`), which — like
`analyze_frame` — will produce L5 audit rows through the normal
capability-gated turn path. This keeps the audit surface coherent:
**capture is audited, config is persisted.**

Flagged for Don's review in the handoff.

## Tests

### New (14, all green)

`apps/desktop/src-tauri/src/mic_permissions.rs::tests`:

- `defaults_are_ask` — default posture is `Ask`.
- `evaluate_returns_correct_gate_for_each_state` — all three
  `PermissionState`s map to the expected `CaptureGate`.
- `load_or_default_when_missing_returns_defaults`.
- `save_then_load_roundtrips`.
- `load_or_default_falls_back_on_malformed_json` — WARN'd fallback.
- `unknown_fields_are_silently_ignored_on_read` — additive contract.
- `unknown_fields_are_dropped_on_rewrite` — documented limitation,
  symmetrical with `VisionPersistedState`.
- `missing_state_field_falls_back_to_default` — `{}` loads as `Ask`.
- `json_uses_lowercase_state_strings`.
- `permission_path_for_lives_beside_app_data`.

`apps/desktop/src-tauri/src/state.rs::tests`:

- `mic_permission_defaults_to_ask_after_boot`.
- `set_mic_permission_updates_snapshot_and_gate`.
- `mic_permission_file_round_trips_across_appstates`.
- `mic_permission_is_independent_from_media_permissions` — locks
  the "distinct consent boundaries" promise; a mic write does not
  bleed into media, and vice versa.

### Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean (pre-existing warnings only)
- `cargo test --workspace` — green across all workspace crates
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` — **57 / 57**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **107 / 107** (was 93 + 14 new)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `apps/desktop && pnpm typecheck` — clean
- `apps/desktop && pnpm build` — clean
- `apps/desktop && pnpm test` — **86 / 86** (unchanged; no new TS tests this slice)

## Hard-constraint compliance

- No audio capture.
- No `transcribe_utterance` command.
- No `SpeechProvider` trait or adapter.
- No `voice_provider.json` work (step 3).
- No `VoicePanel` UI.
- No TTS.
- No wake word / VAD / continuous listening.
- No push authorization requested.
- No release / distribution / signing work.
- No new vision providers.
- No unification of `LlamaCppConfigError` + `OllamaConfigError`.
- No extension of L5 `AuditRecordEvent`.
- No image-persistence posture change.
- No `vision_provider.json` contract widening.
- No new test dependencies (the `tempfile` crate was already a dev
  dep, used by existing tests).

## Divergences from the design doc

Noting for the record — all are still inside the design-doc envelope:

- The doc in `docs/VOICE-V1-ARCHITECTURE.md` §0 shows
  `mic_permissions.json` with the same tri-state. Implementation
  carries **`state`** as a struct field (`{ "state": "ask" }`)
  rather than a flat string, so the JSON stays additive-default-safe
  when future fields land (e.g. `allow_devices` allowlist). This
  matches the shape every other additive config uses in this repo.
- The voice design doc imagined mic consent as a single bit. We
  preserved the tri-state explicitly because it composes with
  `CaptureGate` and the shared `PermissionState` enum without
  inventing a parallel vocabulary.

Neither divergence contradicts the design doc or the hard
constraints. Both are pragmatic reuse of existing vocabulary.

## What is deliberately NOT in this slice

- No `VoicePanel` UI — that's step 5.
- No `SpeechProvider` trait — step 2.
- No `voice_provider.json` — step 3.
- No `transcribe_utterance` command, telemetry kinds, or
  validators — step 4.
- No Trust-drawer History rendering for voice events — step 5.
- No rot guard for `VOICE-V1-ARCHITECTURE.md` — step 6. The
  existing vision rot guard does not check the voice doc (the
  voice doc is still "design-only"); when step 6 lands, a
  `tools/lint-voice-doc/` mirror will be added.

## Next step (for the session after this one)

Voice V1 step 2 — `SpeechProvider` trait + local STT adapter
scaffold. See `docs/VOICE-V1-ARCHITECTURE.md` §2 for the trait
shape and the whisper.cpp candidate adapter outline. No commands
yet, no UI; feature-gated (`speech-whispercpp`), healthcheck-only.

## Decisions for Don's review

1. **No L5 audit event emitted from `set_mic_permission`.** Mirrors
   `set_media_permission` (which does not emit either). Audit
   coverage for mic activity will come with `transcribe_utterance`
   in step 4, the same way `analyze_frame` owns the audit surface
   for camera/screen. Tracing INFO is emitted for local
   observability. If you want a hand-rolled audit write here, reopen
   and I'll extend — but it would also want retrofitting to the
   media command for consistency.
2. **JSON shape uses `{ "state": "ask" }`** rather than a flat
   string `"ask"`. Keeps the config additive-default-safe for future
   fields (e.g. `allow_devices`) without breaking old builds.
3. **`MicPermission` imports `PermissionState` + `CaptureGate`
   from `media_permissions`** rather than inventing a parallel
   three-state vocabulary. Lower conceptual surface; the mic does
   not introduce new states.
