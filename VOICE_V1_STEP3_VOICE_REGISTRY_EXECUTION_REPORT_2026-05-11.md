# Voice V1 Step 3 — `voice_provider.json` + `VoiceRegistry` — execution report (2026-05-11)

**Status:** Shipped locally on `dev` (commit `2178da8`). Push not authorized.

## Goal

Land the speech-provider registry in the shell, mirroring Vision V1's
`VisionRegistry` + `vision_provider.json`. No Tauri commands, no
`transcribe_utterance`, no UI — pure wiring for the future step 4
capture path and step 5 UI surface.

## Surfaces touched

### New

- **`apps/desktop/src-tauri/src/voice_registry.rs`** (~640 lines
  including 26 tests). Section-by-section mirror of
  `vision_registry.rs`:
  - `VoicePersistedState { active, model_per_provider }` with the
    additive-default-safe contract. `#[serde(default)]` on
    `model_per_provider`, `BTreeMap` for deterministic key order.
  - `SpeechProviderInfo { id, label, active }` for UI snapshots.
  - `VoiceRegistry` with full API:
    - `empty`, `register` (de-dups by id), `attach_persistence`.
    - `auto_select_first_if_unset`, `active`, `active_id`,
      `active_label`, `list`.
    - `set_active` (persists, reapplies per-provider model on swap),
      `set_active_model`, `active_model`, `model_for`.
    - `seed_missing_models_from_adapters` (first-launch hook,
      idempotent, skips passive adapters + whitespace-only models).
    - `len`, `is_empty` for logging.
  - `voice_persistence_path_for(app_data_dir)` helper resolving
    `<app_data>/voice_provider.json`.
  - `load_persisted` / `save_persisted` with atomic
    write-to-temp + rename, malformed fallback + WARN naming path.

### Modified

- **`apps/desktop/src-tauri/src/state.rs`**:
  - Import `SpeechProvider` from `aether_l4_router` and the new
    `VoiceRegistry` / `SpeechProviderInfo`.
  - New `voice: RwLock<VoiceRegistry>` field on `AppState`.
  - Field default wiring in `build`.
  - Public API (all `#[allow(dead_code)]` pending step 4 consumers):
    `register_speech_provider`, `attach_voice_persistence`,
    `voice_auto_select_if_unset`, `voice_seed_missing_models`,
    `speech_provider`, `speech_active_id`, `speech_provider_label`,
    `speech_provider_list`, `set_active_speech_provider`,
    `speech_active_model`, `set_active_speech_model`.
- **`apps/desktop/src-tauri/src/main.rs`**:
  - `mod voice_registry;`.
  - New `wire_voice_registry` called from both the `sqlite-backend`
    path and the in-memory fallback path — parallel to
    `wire_vision_registry`.
  - `register_whispercpp_speech_if_configured` feature-gated
    against `speech-whispercpp`, mirrors the two vision
    registration functions. Logs boot candidate, base URL on
    healthcheck failure, and registered label on success.
- **`apps/desktop/src-tauri/Cargo.toml`**:
  - New `speech-whispercpp = ["aether-l4-router/speech-whispercpp"]`
    passthrough feature. Independent of the vision features.

## Contract verification

Locked by tests (26 total):

### `VoiceRegistry` behavior (21 tests)

- `empty_registry_has_no_active_provider`.
- `auto_select_first_picks_insertion_order`.
- `list_marks_exactly_the_active_provider`.
- `set_active_rejects_unknown_id`.
- `set_active_none_disables_voice` — the "disable voice" contract.
- `register_dedups_by_id`.
- `persistence_round_trips_active_selection`.
- `persisted_unknown_id_falls_back_to_first_registered`.
- `persisted_explicit_none_keeps_voice_disabled`.
- `missing_persistence_file_uses_fallback_select`.
- `set_active_model_writes_through_provider_and_map`.
- `set_active_model_errors_when_no_active_provider`.
- `provider_swap_preserves_each_providers_last_model`.
- `persisted_model_map_round_trips_and_reapplies_on_reopen`.
- `persisted_model_for_unknown_provider_is_retained_but_not_applied`.
- `unknown_top_level_field_is_ignored_on_load` — additive contract.
- `load_persisted_directly_tolerates_unknown_fields` — type-level
  proof that serde is the gate, not best-effort swallowing.
- `unknown_fields_are_dropped_on_rewrite` — documented limitation.
- `malformed_json_falls_back_to_default_state`.
- `old_persistence_without_model_map_still_loads`.
- `voice_persistence_path_helper_lives_beside_app_data`.

### Seeding (5 tests)

- `seed_missing_models_writes_through_for_first_launch`.
- `seed_missing_models_is_idempotent_after_user_pick`.
- `seed_missing_models_skips_providers_with_no_current_model`
  (with a local `PassiveSpeech` adapter — proves the default-None
  path).
- `seed_missing_models_skips_whitespace_only_models`.
- `seed_missing_models_no_op_when_persistence_unwired`.

Tests use `StubSpeech` / `PassiveSpeech` adapters defined in-module.
No new test dependencies.

## Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean (pre-existing warnings only)
- `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
- `cargo test --workspace` — **133 / 0**
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **133 / 133** (was 107; +26)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `apps/desktop && pnpm typecheck` — clean
- `apps/desktop && pnpm build` — clean
- `apps/desktop && pnpm test` — **86 / 86**

## Hard-constraint compliance

- No Tauri commands (step 4).
- No `transcribe_utterance` (step 4).
- No UI (step 5).
- No actual STT inference, audio capture, or telemetry changes.
- No unification of `WhisperCppConfigError` with other provider
  config errors.
- No L5 `AuditRecordEvent` changes.
- No widening of `vision_provider.json`.
- No new test dependencies.
- Mic permission behavior from step 1 unchanged.
- L4 `SpeechProvider` trait behavior from step 2 unchanged.

## Design decisions worth noting

1. **`SpeechProviderInfo` struct name** (not `VoiceProviderInfo`) —
   matches the trait naming (`SpeechProvider`), not the file name.
   Keeps symbol naming consistent with the L4 trait.
2. **`speech_*` prefix on AppState accessors, `voice_*` on registry
   wiring helpers.** The distinction is intentional: `voice_*` is
   about the subsystem (the mic + transcription track); `speech_*`
   is about the concrete trait (speech provider). Same asymmetry
   vision uses (`vision_*` for subsystem, but providers are
   registered + fetched by the same name — vision gets away with
   one word). For voice the split is clearer.
3. **`wire_voice_registry` is called from both the sqlite-backend
   path and the in-memory fallback path** — so tests / CI / any
   sandbox build that can't open the data dir still goes through
   the registry code.
4. **`speech-whispercpp` passthrough feature on src-tauri** — so
   the src-tauri test matrix can include `speech-whispercpp` and
   exercise the full wire-up. Today the feature only gates
   `register_whispercpp_speech_if_configured`; the registry itself
   is unconditional (same pattern as `VisionRegistry`).
5. **`#[allow(dead_code)]` on the voice accessors** — they're
   public API waiting for step 4's `transcribe_utterance` and step
   5's Tauri commands. Mirrors vision's approach.

## Divergences from the design doc

None. Doc §3 and §4 describe exactly this shape.

## What is deliberately NOT in this slice

- No `transcribe_utterance` — step 4.
- No VoicePanel UI — step 5.
- No Trust drawer voice rows — step 5.
- No Tauri commands for voice provider listing / swap — step 4 or 5.
- No tools/lint-voice-doc rot guard — step 6.
- No audio capture, no actual STT inference.

## Next step (after this one)

Voice V1 step 4 — `transcribe_utterance` Tauri command +
utterance validators + early-exit telemetry + L5 audit at capture
time. Involves reaching into the `speech_provider()` accessor
landed here, the `validate_audio_data_url` helper exported from
step 2, and the mic permission gate from step 1.
