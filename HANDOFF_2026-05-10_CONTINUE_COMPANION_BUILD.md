# Handoff — Continue the companion build (2026-05-10)

**Written:** 2026-05-09.
**Branch state:** `dev` at `8d16529` with **9 unpushed commits** ahead
of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Voice V1 step 2 — `SpeechProvider` trait + local
STT adapter scaffold (feature-gated, no commands, no UI).

---

## 0. Morning status

1. `dev` is `8d16529`, 9 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-09, all green:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (2 pre-existing warnings in `aether-l1-interaction`)
   - `cargo test --workspace` — all binaries green
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` — **57 / 57**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` — **107 / 107** (was 93; +14 new mic tests)
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **86 / 86**

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `eca7f60` | feat(apps/desktop): mic permission surface (Voice V1 step 1) |
| `d1d160f` | feat(apps/desktop): Settings UI row for mic permission (Voice V1 step 1) |
| `8d16529` | docs: Voice V1 step 1 execution report |

Reports:

- [VOICE_V1_STEP1_MIC_PERMISSION_SURFACE_EXECUTION_REPORT_2026-05-09.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP1_MIC_PERMISSION_SURFACE_EXECUTION_REPORT_2026-05-09.md)

## 2. Track status

### Track V — Vision V1: **DONE (maintenance only)**

No changes this round.

### Track VOICE — Voice V1: **Step 1 COMPLETE**

- **Step 1 — Mic permission surface**: done (this round).
  - `mic_permissions.rs` module, `<app_data>/mic_permissions.json`,
    additive-default-safe contract test-locked.
  - AppState integration: `attach_mic_permission_file`,
    `mic_permission`, `set_mic_permission`, `evaluate_mic_permission`.
  - Tauri commands `get_mic_permission` / `set_mic_permission`.
  - Settings UI row under a new Microphone section.
- **Step 2 — SpeechProvider trait + local STT adapter scaffold**:
  next session.
- **Steps 3–6** (voice_provider.json + VoiceRegistry;
  `transcribe_utterance` + validators; VoicePanel UI; rot guard):
  pending.

### Track PRESENCE — L3 Presence: **Not started**

Architecture doc needed before any code.

### Track MEMORY — L2 Memory maturation: **Not started**

Architecture doc needed before any code.

## 3. Current Vision V1 surface

Unchanged. The only Vision V1 touch this round was a courtesy
re-run of the rot guard (still green, 51 anchors / 12 files).

## 4. Voice V1 product surface (post-step-1)

- `<app_data>/mic_permissions.json` persists `{ "state": "ask" }`
  by default, additive-default-safe, atomic writes via
  write-to-temp + rename.
- Settings drawer has a dedicated Microphone section with the
  same tri-state control used for camera and screen. Footer now
  lists both persistence files.
- No audio capture. No `SpeechProvider`. No STT. No voice UI
  beyond the Settings row.

## 5. What to build next — Voice V1 step 2

Scope from the design doc (`docs/VOICE-V1-ARCHITECTURE.md` §2):

- Define `SpeechProvider` trait in L4 with methods mirroring
  `VisionProvider`: `id`, `label`, `transcribe`, `set_model`,
  `current_model`, `healthcheck`, `list_models`.
- Define `SpeechRequest` / `SpeechResponse` structs.
- Implement **one** local adapter candidate — whisper.cpp —
  feature-gated as `speech-whispercpp`. Healthcheck only; no
  inference wire-up yet. Config via env:
  `AETHER_WHISPERCPP_SPEECH_BASE_URL`,
  `AETHER_WHISPERCPP_SPEECH_MODEL`,
  `AETHER_WHISPERCPP_SPEECH_LANGUAGE`.
- Provider config error (`WhisperCppConfigError`) intentionally
  **not** unified with `OllamaConfigError` /
  `LlamaCppConfigError`.
- Layer-boundary rules must stay intact — the trait lives
  alongside `VisionProvider` in `packages/l4-router/`.
- No Tauri commands yet. No UI. No registry. No persistence.
  This step only stands the provider abstraction up.

Tests expected:

- Trait is object-safe (`Arc<dyn SpeechProvider>` compiles).
- `WhisperCppSpeechConfig::from_env` parses + defaults cleanly.
- Healthcheck wiring (mockable HTTP or process boundary — pick
  one in implementation and document).

## 6. Decisions for Don's review (still open)

Carried over from the step 1 report:

1. **No L5 audit event emitted from `set_mic_permission`.**
   Mirrors `set_media_permission`. If you want a hand-rolled
   audit write here, reopen — but it should also retrofit to
   media for consistency. My read: audit fires at capture time,
   not at config-toggle time.
2. **`mic_permissions.json` shape is `{ "state": "ask" }`** (not
   a flat `"ask"`). Keeps the contract additive-default-safe for
   future fields (e.g. `allow_devices` allowlist).
3. **`MicPermission` imports `PermissionState` + `CaptureGate`
   from `media_permissions`** instead of inventing parallel
   vocabulary.

## 7. Risks / things to review first

- **9 unpushed commits.** `fb2ce1c`, `88159f8`, `4d67da8`,
  `e65e35f`, `ccd1a2d`, `b198a3a`, `eca7f60`, `d1d160f`,
  `8d16529`. Review the batch and authorize a push when ready.
- **Mic permission has no real capture site yet** — which means
  the `evaluate_mic_permission` path is live but unused. Marked
  `#[allow(dead_code)]` with a comment pointing at step 4.
- **Voice V1 doc `Status:` is "design-only".** When step 6 lands
  the rot guard, we flip it to "current". Until then, code
  and doc can drift — nothing enforces the mirror yet.
- **Settings drawer footer now claims two files.** A user reading
  the copy will expect both `media_permissions.json` and
  `mic_permissions.json` to exist on disk after first settings
  change. Verify in manual QA next session or whenever the app
  is booted.

## 8. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `8d16529`, 9 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 is stable and rot-guarded.
- Voice V1 step 1 (mic permission surface) is COMPLETE. Settings
  UI, Tauri commands, persistence, tests all landed.

Mandatory first steps (in order, before editing):
1. Read `HANDOFF_2026-05-10_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read `VOICE_V1_STEP1_MIC_PERMISSION_SURFACE_EXECUTION_REPORT_2026-05-09.md`.
4. Read `docs/VOICE-V1-ARCHITECTURE.md` §2 (Providers) and §3
   (voice_provider.json contract — for awareness only; step 3,
   not step 2).
5. Read these existing modules for the pattern:
   - `packages/l4-router/src/vision.rs` (VisionProvider trait)
   - `packages/l4-router/src/providers/ollama_vision.rs`
   - `packages/l4-router/src/providers/llamacpp_vision.rs`

Session focus: Voice V1 step 2 — SpeechProvider trait + local STT
adapter scaffold (feature-gated, no commands, no UI).

Scope:
- Add `SpeechProvider` trait in `packages/l4-router/src/`. Methods
  mirror `VisionProvider` (id, label, transcribe, set_model,
  current_model, healthcheck, list_models).
- Add `SpeechRequest` / `SpeechResponse` structs.
- Implement ONE local adapter candidate — whisper.cpp — feature-
  gated as `speech-whispercpp`. HEALTHCHECK ONLY; no inference
  wire-up yet.
- Config via env: `AETHER_WHISPERCPP_SPEECH_BASE_URL`,
  `AETHER_WHISPERCPP_SPEECH_MODEL`, optional
  `AETHER_WHISPERCPP_SPEECH_LANGUAGE`.
- `WhisperCppConfigError` type; do NOT unify with other provider
  config errors.
- Tests: trait object-safety, config parsing, healthcheck wiring.

Out of scope (do NOT do in this session):
- Tauri commands.
- Frontend UI.
- `voice_provider.json` or any registry — that's step 3.
- `transcribe_utterance` command — step 4.
- Any actual STT inference.
- Audio capture.
- Persistent voice provider selection.

Hard constraints (don't drift):
- No push.
- No release / distribution / signing.
- No mic/voice capture.
- No streaming or continuous listening.
- No new vision providers.
- No unification of LlamaCppConfigError + OllamaConfigError
  with new speech error types.
- No L5 AuditRecordEvent changes.
- No widening of vision_provider.json.
- No new test dependencies unless the design doc justifies them
  explicitly.
- Do NOT modify mic_permissions behavior from step 1.

Process:
1. Draft the trait, request/response structs, and feature flag.
2. Scaffold the whisper.cpp adapter with the env-config parser
   and healthcheck only.
3. Unit tests for config parsing and trait object-safety.
4. Full check matrix:
   - cargo fmt --all -- --check
   - cargo check --workspace (with and without feature)
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp
   - python tools/lint-layer-boundaries/check.py
   - python tools/lint-vision-doc/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
5. Fix all failures.
6. Commit in scoped slices.
7. Update `docs/VOICE-V1-ARCHITECTURE.md` ONLY if implementation
   revealed a concrete correction.

Before stopping:
- Clean git status.
- Execution report for step 2.
- Fresh handoff file following the same shape.
- Leave commits unpushed; note in the handoff.

Stay strictly on step 2. No drift into step 3 or beyond.
```

---

(end of handoff)
