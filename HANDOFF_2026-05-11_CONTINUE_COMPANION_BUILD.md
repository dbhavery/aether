# Handoff — Continue the companion build (2026-05-11)

**Written:** 2026-05-10.
**Branch state:** `dev` at `316f45a` with **13 unpushed commits**
ahead of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Voice V1 step 3 — `voice_provider.json` +
`VoiceRegistry`, mirroring the Vision V1 registry pattern.

---

## 0. Morning status

1. `dev` is `316f45a`, 13 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-10, all green:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (2 pre-existing warnings in
     `aether-l1-interaction`)
   - `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
   - `cargo test --workspace` — **133 passed / 0 failed**
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86** (was 57; +29)
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **107 / 107**
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **86 / 86**

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `97fd43a` | feat(l4-router): SpeechProvider trait + SpeechRequest/Response (Voice V1 step 2) |
| `9c57196` | feat(l4-router): whisper.cpp speech adapter scaffold (Voice V1 step 2, healthcheck only) |
| `316f45a` | docs: Voice V1 step 2 execution report |

Reports:

- [VOICE_V1_STEP2_SPEECHPROVIDER_SCAFFOLD_EXECUTION_REPORT_2026-05-10.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP2_SPEECHPROVIDER_SCAFFOLD_EXECUTION_REPORT_2026-05-10.md)

## 2. Track status

### Track V — Vision V1: **DONE (maintenance only)**

No changes this round.

### Track VOICE — Voice V1: **Steps 1 + 2 COMPLETE**

- **Step 1 — Mic permission surface**: done (2026-05-09).
- **Step 2 — `SpeechProvider` trait + local STT adapter scaffold**:
  done (this round).
  - `packages/l4-router/src/speech.rs` — `SpeechProvider`,
    `SpeechRequest`, `SpeechResponse`, `split_audio_data_url`,
    compile-time object-safety assertion.
  - `packages/l4-router/src/providers/whispercpp_speech.rs` —
    `WhisperCppSpeechProvider`, `WhisperCppSpeechConfig`,
    `WhisperCppConfigError`. Feature-gated `speech-whispercpp`.
    Healthcheck probes `/`. `transcribe` returns a loud
    deferred-to-step-4 error.
  - 29 new tests.
- **Step 3 — `voice_provider.json` + `VoiceRegistry`**: next session.
- **Steps 4–6** (`transcribe_utterance` + validators;
  VoicePanel UI; rot guard): pending.

### Track PRESENCE — L3 Presence: **Not started**

Architecture doc needed before any code.

### Track MEMORY — L2 Memory maturation: **Not started**

Architecture doc needed before any code.

## 3. Current Vision V1 surface

Unchanged.

## 4. Voice V1 surface (post-step-2)

- `<app_data>/mic_permissions.json` tri-state persistence.
- Settings UI row for mic permission.
- `SpeechProvider` trait in L4. `Arc<dyn SpeechProvider>` is the
  shape future shell code will hold.
- One local adapter scaffold — `WhisperCppSpeechProvider`,
  feature-gated `speech-whispercpp`. Env-driven config
  (`AETHER_WHISPERCPP_SPEECH_{MODEL,BASE_URL,LANGUAGE,TIMEOUT_MS}`).
- Healthcheck wiring works against a live whisper.cpp server and
  fails cleanly against an unreachable one.
- **No transcription wiring, no audio capture, no commands, no UI
  beyond the Settings row from step 1.**

## 5. What to build next — Voice V1 step 3

Scope from `docs/VOICE-V1-ARCHITECTURE.md` §3 and §4:

- Add `VoiceRegistry` in the shell
  (`apps/desktop/src-tauri/src/voice_registry.rs`) mirroring
  `vision_registry.rs`:
  - `VoicePersistedState { active: Option<String>, model_per_provider: HashMap<String, String> }`.
  - Additive-default-safe contract: `#[serde(default)]` on
    `model_per_provider`, no `deny_unknown_fields`, unknown
    fields silently ignored on read AND dropped on rewrite
    (documented limitation, test-locked).
  - Persistence file `<app_data>/voice_provider.json`.
  - `voice_persistence_path_for(app_data_dir)` helper.
  - Single-writer through `VoiceRegistry`.
  - Register / list / set_active / set_active_model APIs.
  - `auto_select_first_if_unset` and `seed_missing_models_from_adapters`
    equivalents.
- Wire `VoiceRegistry` into `AppState`:
  - Field behind `RwLock`.
  - `register_speech_provider` (behind feature gate).
  - `attach_voice_persistence`.
  - `speech_provider` / `speech_active_id` / `speech_provider_label` accessors.
- Mirror the tests from `vision_registry.rs` — schema tolerance,
  unknown-fields drop-on-rewrite, active-fallback, model survival
  across provider swaps.
- Mirror the lint contract: `tools/lint-layer-boundaries/check.py`
  should still pass (the trait lives in `aether-l4-router`, the
  registry in the shell).
- **No Tauri commands this step.** That's step 4.

## 6. Decisions for Don's review (still open)

Carried over:

1. **No L5 audit event emitted from `set_mic_permission`.** Mirrors
   `set_media_permission`. Step 4's `transcribe_utterance` will
   produce L5 audit rows at capture time, same way `analyze_frame`
   does.
2. **`mic_permissions.json` shape is `{ "state": "ask" }`** (not a
   flat string) so the contract stays additive-default-safe.
3. **`MicPermission` reuses `PermissionState` + `CaptureGate`**
   from `media_permissions`.

New this round:

4. **Added `WhisperCppConfigError::EmptyLanguage`** to the error
   taxonomy — an empty / whitespace `AETHER_WHISPERCPP_SPEECH_LANGUAGE`
   is rejected rather than silently falling through to auto-detect.
   Inside the design-doc envelope (which says "adapter owns its own
   taxonomy"), but slightly broader than what §2 explicitly listed.
5. **`WhisperCppSpeechProvider::transcribe` returns a loud scaffold
   error** pinned to the literal string
   `"deferred to Voice V1 step 4 (transcribe_utterance)"`. Step 4
   grep that exact marker to confirm the scaffold error is the
   only path (no accidental shadow implementations got left
   behind). Same "no silent STT fallback" rule the design doc
   locked.
6. **Healthcheck probes `/`, not `/health` or `/v1/models`.**
   whisper.cpp wrappers vary across builds; `/` is universal.
   Trade-off: a server that accepts HTTP but is internally broken
   passes this healthcheck. Acceptable because step 4's real
   `transcribe` call is the authoritative "can do work" signal.
7. **`list_models` uses the trait default (empty vec).** Real
   discovery deferred to step 3 alongside the registry.

## 7. Risks / things to review first

- **13 unpushed commits.** `fb2ce1c`, `88159f8`, `4d67da8`,
  `e65e35f`, `ccd1a2d`, `b198a3a`, `eca7f60`, `d1d160f`,
  `8d16529`, `e0d52db`, `97fd43a`, `9c57196`, `316f45a`.
- **Voice V1 doc `Status:` is still "design-only".** Flipping to
  "current" happens in step 6 with the rot guard, not earlier.
- **Feature matrix for tests.** The l4-router tests run under
  all three feature flags (`ollama-provider,vision-llamacpp,speech-whispercpp`).
  The src-tauri tests currently build with only the two vision
  features; step 4 will add `speech-whispercpp` to the src-tauri
  feature set so the `transcribe_utterance` command can compile
  against the whispercpp adapter. Flagged so it's not a surprise
  in step 4.
- **`ENV_MUTEX` pattern** in the whispercpp tests serializes
  env-var access — lifted verbatim from `llamacpp_vision.rs`.
  Reliable under `cargo test` default parallelism; if a future
  runner uses process-based isolation this becomes unnecessary.

## 8. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `316f45a`, 13 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 is stable and rot-guarded.
- Voice V1 step 1 (mic permission) is COMPLETE.
- Voice V1 step 2 (SpeechProvider trait + whisper.cpp scaffold) is
  COMPLETE. Feature flag speech-whispercpp. Healthcheck only.
  transcribe returns a loud scaffold error pinned to the marker
  "deferred to Voice V1 step 4 (transcribe_utterance)".

Mandatory first steps (in order, before editing):
1. Read `HANDOFF_2026-05-11_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read
   `VOICE_V1_STEP2_SPEECHPROVIDER_SCAFFOLD_EXECUTION_REPORT_2026-05-10.md`.
4. Read `docs/VOICE-V1-ARCHITECTURE.md` §3 (voice_provider.json
   contract) and §4 (provider/model selection rules).
5. Read the Vision V1 registry for the pattern:
   - `apps/desktop/src-tauri/src/vision_registry.rs`
   - the tests at the bottom of that file
6. Read for AppState-integration shape:
   - the `vision` / `vision_registry` fields in
     `apps/desktop/src-tauri/src/state.rs`
   - `wire_vision_registry` in `main.rs`

Session focus: Voice V1 step 3 — `voice_provider.json` +
`VoiceRegistry`.

Scope:
- New `apps/desktop/src-tauri/src/voice_registry.rs` mirroring
  `vision_registry.rs` section by section.
- `VoicePersistedState { active, model_per_provider }` with the
  same additive-default-safe contract as `VisionPersistedState`.
- `<app_data>/voice_provider.json` persistence file. Atomic
  write-to-temp + rename. Single-writer through `VoiceRegistry`.
- `voice_persistence_path_for(app_data_dir)` helper.
- `VoiceRegistry` APIs: register, list, active, set_active,
  set_active_model, model_for, auto_select_first_if_unset,
  seed_missing_models_from_adapters.
- Wire into `AppState`: `voice: RwLock<VoiceRegistry>` field,
  `register_speech_provider` (feature-gated), `attach_voice_persistence`,
  `speech_provider` / `speech_active_id` / `speech_provider_label`
  accessors. No Tauri commands yet — those are step 4.
- Tests mirror `vision_registry.rs`:
  - defaults, round-trip, malformed fallback,
  - unknown fields tolerated on read,
  - unknown fields dropped on rewrite (documented limitation),
  - active fallback to first registered when persisted id is unknown,
  - `model_per_provider` survives provider swap,
  - first-launch seeding idempotent.

Out of scope (do NOT do in this session):
- Any Tauri command (`get_speech_providers`, `set_active_speech_provider`, etc. — step 4).
- `transcribe_utterance` — step 4.
- VoicePanel UI — step 5.
- Trust drawer voice rows — step 5.
- Actual STT inference.
- Audio capture.
- Rot guard flip — step 6.

Hard constraints:
- No push.
- No release / distribution / signing.
- No mic capture.
- No streaming or continuous listening.
- No new vision providers.
- No unification of Config error types across provider families.
- No L5 AuditRecordEvent changes.
- No widening of vision_provider.json.
- No new test dependencies.
- Do NOT modify Voice V1 step 1/2 artifacts except where step 3
  genuinely requires (e.g. adding `register_speech_provider` on
  AppState).

Process:
1. Scaffold `voice_registry.rs` with the persisted-state struct and
   contract tests.
2. Add registry API (register, set_active, set_active_model,
   model_for, auto_select_first_if_unset).
3. Add seed_missing_models_from_adapters.
4. Wire into AppState (fields, constructors, accessors).
5. Tests for each phase.
6. Full check matrix:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp
   - python tools/lint-layer-boundaries/check.py
   - python tools/lint-vision-doc/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
7. Fix all failures.
8. Commit in scoped slices.
9. Update `docs/VOICE-V1-ARCHITECTURE.md` ONLY if implementation
   revealed a concrete correction.
10. Write execution report + fresh handoff.

Note: step 3 needs `speech-whispercpp` added to the src-tauri
feature matrix if the tests are to exercise the wiring. Decide
based on Vision V1 precedent (where the src-tauri tests already
run with both vision features).

Stay strictly on step 3. No drift into step 4 or beyond.
```

---

(end of handoff)
