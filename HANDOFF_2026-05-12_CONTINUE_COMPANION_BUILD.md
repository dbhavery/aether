# Handoff — Continue the companion build (2026-05-12)

**Written:** 2026-05-11.
**Branch state:** `dev` at `7836dec` with **18 unpushed commits**
ahead of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Voice V1 step 4 — `transcribe_utterance` +
validators + early-exit telemetry + L5 audit at capture time.

---

## 0. Morning status

1. `dev` is `7836dec`, 18 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-11 after Voice V1 step 3,
   all green:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (pre-existing warnings only)
   - `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
   - `cargo test --workspace` — **133 / 0**
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **133 / 133** (was 107; +26 voice registry)
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **86 / 86**

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `2178da8` | feat(apps/desktop): VoiceRegistry + voice_provider.json (Voice V1 step 3) |
| `da76de5` | docs: Voice V1 step 3 execution report (VoiceRegistry) |
| `e910454` | docs: Presence V1 architecture reference (design only) |
| `7836dec` | docs: Memory V2 architecture reference (design only) |

Reports:

- [VOICE_V1_STEP3_VOICE_REGISTRY_EXECUTION_REPORT_2026-05-11.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP3_VOICE_REGISTRY_EXECUTION_REPORT_2026-05-11.md)
- [PRESENCE_V1_STEP0_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-11.md](file:///C:/Users/dbhav/Projects/aether/PRESENCE_V1_STEP0_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-11.md)
- [MEMORY_V2_STEP0_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-11.md](file:///C:/Users/dbhav/Projects/aether/MEMORY_V2_STEP0_ARCHITECTURE_DOC_EXECUTION_REPORT_2026-05-11.md)

Architecture docs (new):

- [docs/PRESENCE-V1-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/PRESENCE-V1-ARCHITECTURE.md)
- [docs/MEMORY-V2-ARCHITECTURE.md](file:///C:/Users/dbhav/Projects/aether/docs/MEMORY-V2-ARCHITECTURE.md)

## 2. Track status

### Track V — Vision V1: **DONE (maintenance only)**

No changes this round.

### Track VOICE — Voice V1: **Steps 1–3 COMPLETE**

- Step 1 — Mic permission surface: done.
- Step 2 — SpeechProvider trait + whisper.cpp scaffold: done.
- **Step 3 — voice_provider.json + VoiceRegistry: done (this run).**
- Step 4 — `transcribe_utterance` + validators + telemetry + audit:
  next session.
- Steps 5–6 (VoicePanel UI, rot guard): pending.

### Track PRESENCE — Presence V1: **Step 0 COMPLETE**

- **Step 0 — Architecture doc: done (this run).**
- Step 1 — `presence.json` config + Settings toggles: pending.
- Steps 2–6 (controller, engine, Tauri commands, UI, rot guard):
  pending.

### Track MEMORY — Memory V2: **Step 0 COMPLETE**

- **Step 0 — Architecture doc: done (this run).**
- Step 1 — L5 capability additions (`MemoryWrite`, `MemoryRead`,
  `MemoryForget`, `MemoryEdit`): pending.
- Steps 2–7 (policy surface, write/read plumbing, Memory tab,
  retention sweep, embeddings, rot guard): pending.

## 3. Current Voice V1 surface (post-step-3)

- `<app_data>/mic_permissions.json` — tri-state mic consent.
- `<app_data>/voice_provider.json` — active speech provider id +
  `model_per_provider`, additive-default-safe, atomic writes.
- `SpeechProvider` trait in L4. `Arc<dyn SpeechProvider>` held by
  `AppState.voice: RwLock<VoiceRegistry>`.
- `WhisperCppSpeechProvider` registered at boot when
  `AETHER_WHISPERCPP_SPEECH_MODEL` is set and healthcheck passes.
  `transcribe` still returns the pinned scaffold error.
- Shell APIs (all `#[allow(dead_code)]` pending step 4 consumers):
  `register_speech_provider`, `attach_voice_persistence`,
  `voice_auto_select_if_unset`, `voice_seed_missing_models`,
  `speech_provider`, `speech_active_id`, `speech_provider_label`,
  `speech_provider_list`, `set_active_speech_provider`,
  `speech_active_model`, `set_active_speech_model`.
- Settings UI: Microphone section with the tri-state control (from
  step 1). No voice-provider UI yet — step 5.

## 4. What to build next — Voice V1 step 4

Scope from `docs/VOICE-V1-ARCHITECTURE.md` §1, §5, §6:

### Command surface

- New Tauri command: `transcribe_utterance`.
  - Input: `{ kind: "voice", utterance_data_url: String, duration_ms: u32, cue?: Option<String> }`.
  - Evaluates mic permission gate (Deny / Ask / Allow → CaptureGate).
  - On Deny / Ask: records a `mic_permission_denied` /
    `mic_permission_ask` telemetry entry, short-circuits with a
    friendly error string, no provider call.
  - On Allow: calls `validate_utterance_data_url` (see below),
    then `AppState.speech_provider()`, then
    `provider.transcribe(SpeechRequest { ... })`.
  - On provider error: surface a clear error to the user. **No
    silent fallback.**
  - On success: produce an assistant-like transcript entry
    annotated with provider + model meta (same MessageMeta fields
    vision uses).

### Validator

- `validate_utterance_data_url(data_url)` in commands.rs, mirror
  of `validate_frame_data_url`. Rules from the design doc §5:
  - Must start with `data:audio/wav`.
  - Must contain a comma separator.
  - Body must be non-empty, non-whitespace, at least
    `MIN_UTTERANCE_BODY_LEN` (propose 64) chars.
- `maybe_apply_voice` mirror of `maybe_apply_vision` for defense
  in depth; logs at debug, not WARN.

### Telemetry kinds

Five kinds (matching the Voice V1 doc):

- `utterance_transcribed` (in audit as a turn).
- `utterance_blocked` (in audit as a turn).
- `utterance_invalid` (no audit).
- `mic_permission_denied` (no audit).
- `mic_permission_ask` (no audit).

Extend `apps/desktop/src/lib/mediaTurns.ts` (or split into a new
`voiceTurns.ts`) + parity tests.

### L5 audit at capture time

When `transcribe_utterance` reaches the provider call, the turn
goes through the policy engine the same way `analyze_frame` does
today, producing an `AuditRecordEvent` with
`capability: Microphone`, `scope: none`. **Do NOT extend
`AuditRecordEvent` shape.**

### Tests

Mirror the vision test suite where applicable:

- `validate_utterance_data_url` — all six branches.
- Permission gate Deny/Ask/Allow → expected kinds + memory record
  for Deny.
- Scaffold transcribe error surfaces to the user (no silent
  success).
- Telemetry kinds parity (TS ↔ Rust).

### Out of scope for step 4

- No audio capture in the browser (step 5).
- No VoicePanel UI (step 5).
- No Trust drawer voice rows (step 5).
- No rot guard (step 6).

## 5. Decisions for Don's review (still open)

Carried over + new:

1. **No L5 audit event on `set_mic_permission` toggles.** Audit
   lands at capture time (step 4), not on policy-config toggle.
   Same as `set_media_permission`.
2. **`mic_permissions.json` shape is `{ "state": "ask" }`.**
3. **`MicPermission` reuses `PermissionState` / `CaptureGate`
   from `media_permissions`.**
4. **`WhisperCppConfigError::EmptyLanguage`** added to the error
   taxonomy (design doc §2 only listed invalid-timeout + empty
   base URL).
5. **Scaffold `transcribe` returns error pinned to marker**
   `"deferred to Voice V1 step 4 (transcribe_utterance)"`. Step 4
   should grep that marker to verify no shadow implementations.
6. **Whisper healthcheck probes `/`**, not `/health`. whisper.cpp
   HTTP wrappers vary across builds; `/` is universal.
7. **`list_models` uses the trait default (empty vec)** until a
   concrete discovery surface is worth the lock-in.
8. **VoiceRegistry symbol names:** `speech_*` prefix on AppState
   accessors, `voice_*` on registry-wiring helpers — intentional
   asymmetry to keep "subsystem" and "trait" distinct.
9. **`SpeechProviderInfo`** (not `VoiceProviderInfo`) — matches
   trait naming.
10. **Presence V1 has NO L5 audit rows** — presence is observation,
    not a policy-gated action. Two Settings toggles are the
    consent surface instead of a tri-state capability.
11. **Memory V2 reads audit by sampling (every ~100 per domain
    per session)** rather than per-call. Full per-read audit would
    drown the Trust drawer.
12. **Memory V2 user-sensitive domains default to Ask** (Facts,
    Artifacts). Flipping these to Auto requires a design update.

## 6. Risks / things to review first

- **18 unpushed commits.** Hash sequence:
  - `fb2ce1c`, `88159f8`, `4d67da8` — 2026-05-07 roadmap/decision.
  - `e65e35f`, `ccd1a2d`, `b198a3a` — 2026-05-08 rot guard + voice design.
  - `eca7f60`, `d1d160f`, `8d16529`, `e0d52db` — Voice step 1.
  - `97fd43a`, `9c57196`, `316f45a`, `77a59a0` — Voice step 2.
  - `2178da8`, `da76de5` — Voice step 3.
  - `e910454`, `7836dec` — Presence + Memory design docs.
- **Voice V1 doc is still "design-only"** even though steps 1–3
  are implemented. The flip to "current" + rot-guard comes at step
  6. Until then, code and doc can drift silently. The pattern is
  intentional — we lock the doc when the full surface is stable.
- **`speech-whispercpp` feature added to src-tauri matrix.** Tests
  run under all three feature flags together now. If a future CI
  config builds with a subset, double-check.
- **Memory V2 step 1 requires L5 changes.** The capability enum
  gets new variants (`MemoryWrite`, `MemoryRead`, `MemoryForget`,
  `MemoryEdit`). Those are additive-only; tests must ship
  L5-first before any L2 consumer. Flag for when that track
  activates.

## 7. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `7836dec`, 18 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 stable and rot-guarded.
- Voice V1 steps 1–3 complete: mic permission surface, SpeechProvider
  + whisper.cpp scaffold, VoiceRegistry + voice_provider.json.
- Presence V1 step 0 complete: `docs/PRESENCE-V1-ARCHITECTURE.md`
  (design-only).
- Memory V2 step 0 complete: `docs/MEMORY-V2-ARCHITECTURE.md`
  (design-only).

Mandatory first steps:
1. Read `HANDOFF_2026-05-12_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read
   `VOICE_V1_STEP3_VOICE_REGISTRY_EXECUTION_REPORT_2026-05-11.md`.
4. Read `docs/VOICE-V1-ARCHITECTURE.md` §1 (end-to-end flow),
   §5 (utterance validation), §6 (telemetry kinds).
5. Skim code:
   - `apps/desktop/src-tauri/src/commands.rs::analyze_frame` +
     `::validate_frame_data_url` + `::maybe_apply_vision` +
     `::record_frame_early_exit_telemetry` (these are the
     patterns to mirror).
   - `apps/desktop/src/lib/mediaTurns.ts` (kind allow-list + parity
     tests).
   - `apps/desktop/src-tauri/src/mic_permissions.rs` (the gate).
   - `apps/desktop/src-tauri/src/voice_registry.rs` (the provider
     lookup).
   - `packages/l4-router/src/speech.rs::split_audio_data_url`
     (validator helper).

Session focus: Voice V1 step 4 — `transcribe_utterance` + validators
+ early-exit telemetry + L5 audit at capture time.

Scope:
- New Tauri command `transcribe_utterance` mirroring
  `analyze_frame`: evaluate mic gate; on Deny/Ask record
  mic_permission_* telemetry and short-circuit; on Allow validate
  the audio data URL, call the active SpeechProvider, produce a
  transcript entry on success, surface a loud error on provider
  failure (NO silent fallback).
- `validate_utterance_data_url` helper + `maybe_apply_voice`
  mirror (debug log only).
- Five telemetry kinds: utterance_transcribed, utterance_blocked,
  utterance_invalid, mic_permission_denied, mic_permission_ask.
  TS allow-list mirror + parity test.
- L5 audit at capture: the turn goes through the policy engine
  the same way analyze_frame does today. Capability: Microphone.
  Do NOT change AuditRecordEvent shape.
- Tests:
  - validate_utterance_data_url: all branches.
  - Permission gate Deny/Ask/Allow behavior.
  - Scaffold provider error surfaces to user.
  - TS ↔ Rust kind parity.

Out of scope:
- No audio capture in the browser (step 5).
- No VoicePanel UI.
- No Trust drawer voice rendering.
- No rot guard.

Hard constraints:
- No push.
- No release / signing.
- No new vision providers.
- No remote vision.
- No streaming or continuous listening.
- No VAD / wake word / TTS.
- No AuditRecordEvent shape changes; only use the existing
  Microphone capability.
- No cross-provider config error unification.
- No new test dependencies.
- Do NOT modify Voice V1 step 1/2/3 artifacts beyond what step 4
  genuinely needs (e.g. reading from AppState.speech_provider()).

Process:
1. Write validate_utterance_data_url in commands.rs (mirror of
   validate_frame_data_url).
2. Write record_utterance_early_exit_telemetry helper.
3. Write transcribe_utterance command + maybe_apply_voice.
4. Extend mediaTurns.ts (or add voiceTurns.ts) with the five
   kinds + TS parity tests.
5. Register the new command in main.rs.
6. Add tests.
7. Full check matrix:
   - cargo fmt --all -- --check
   - cargo check --workspace
   - cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp
   - cargo test --workspace
   - cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp
   - apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp
   - python tools/lint-layer-boundaries/check.py
   - python tools/lint-vision-doc/check.py
   - apps/desktop && pnpm typecheck && pnpm build && pnpm test
8. Fix all failures.
9. Commit in scoped slices.
10. Update `docs/VOICE-V1-ARCHITECTURE.md` ONLY if implementation
    reveals a concrete correction.
11. Execution report + fresh handoff.

Stay strictly on step 4. No drift into step 5 UI work.
```

---

(end of handoff)
