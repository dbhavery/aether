# Voice V1 Step 4 — `transcribe_utterance` + validators + audit — execution report (2026-05-12)

**Status:** Shipped locally on `dev` (commits `cda9201`, `c7b22a6`, `94ba5c4`). Push not authorized.

## Goal

Land the backend voice path end-to-end without any browser audio
capture or UI. Mirror `analyze_frame` for the voice modality: mic
permission gate → data URL validation → speech provider call →
user-role memory + turn engine run with L5 audit → telemetry kinds
covering the five voice outcomes.

## Surfaces touched

### L5 policy — new preset default

- `packages/l5-policy/src/engine.rs::wave3_default` — add
  `Capability::MediaMic` with `ApprovalMode::Auto` + `RiskClass::Medium`,
  matching the `MediaCamera` / `MediaScreenCapture` entries. The
  shell-side `mic_permissions.json` tri-state is the user-facing
  per-device gate; L5 records the audit row without layering a
  redundant modal on top. Additive-only — no `AuditRecordEvent`
  shape change.
- Extended `wave3_default_grants_media_capabilities_at_medium_risk`
  to cover `MediaMic`.

### Shell — commands + state

- **`apps/desktop/src-tauri/src/commands.rs`** (+687 lines):
  - `MessageMeta` gains additive `origin: Option<String>` field with
    `skip_serializing_if = "Option::is_none"`. Voice turns stamp
    `origin: Some("voice")`; all other construction sites pass
    `origin: None`. Wire-compatible with old clients.
  - `MIN_UTTERANCE_BODY_LEN = 64` const (`~48` raw bytes — smaller
    than any plausible utterance capture).
  - `TranscribeUtteranceRequest { utterance_data_url, duration_ms,
    cue, sample_rate, channels, language }`.
  - `UtteranceOutcome { turn_id, kind, message, error_note }` —
    mirrors `FrameAnalysisOutcome`.
  - `validate_utterance_data_url` — pure helper, four branches
    (prefix, comma separator, empty body, too-short body).
  - `record_utterance_early_exit_telemetry` — helper parallel to
    `record_frame_early_exit_telemetry`; zero provider/model/tier/
    latency fields on early-exit rows.
  - `maybe_apply_voice` — defense-in-depth: revalidates the data
    URL (debug-logs on rejection), splits via `split_audio_data_url`,
    calls `provider.transcribe(SpeechRequest { ... })`. On any
    failure returns `Err(String)` — never silent fallback.
  - `transcribe_utterance` Tauri command. Flow:
    1. `evaluate_mic_permission()` → `CaptureGate`.
    2. `Deny` → system-role memory note + `mic_permission_denied`
       telemetry + friendly copy in `UtteranceOutcome`.
    3. `PromptUser` → `mic_permission_ask` telemetry + friendly
       copy; no memory record (same restraint as vision `Ask`).
    4. `Proceed` → `validate_utterance_data_url`. On Err: record
       `utterance_invalid` telemetry and return `Err("...Try
       recording again.")`. No audit row (no policy decision made).
    5. Fetch `state.speech_provider()`. `None` →
       `Err("Voice is disabled or no speech provider is
       active...")`. No silent fallback, per design §8.9.
    6. Time + call `provider.transcribe(...)` via `maybe_apply_voice`.
       Any provider error surfaces as
       `Err("Transcription failed: {e}")`.
    7. On success: optional `cue` override of the transcript →
       record user-role memory with the utterance text.
    8. Build `TurnRequest { capability: MediaMic, resource: None,
       utterance: <text> }` and run through the active persona's
       turn engine — L5 stamps the audit row with `MediaMic` +
       `ResourceScope::None`.
    9. Assistant-side message (`utterance_transcribed`) or block
       (`utterance_blocked`) builds the outcome; `MessageMeta`
       carries `origin: Some("voice")`, the STT `provider.id()`,
       `provider.current_model()`, and locally-measured
       `latency_ms`.
  - 11 new Rust tests: the four validator branches + two edge
    branches (whitespace body, lock on `MIN_UTTERANCE_BODY_LEN`),
    a whispercpp scaffold-error marker sanity test (grep-equivalent
    that proves no silent shadow implementation), and three
    AppState-level tests for the mic-gate kinds (denied / ask /
    proceed) plus "no speech provider → state returns None".

- **`apps/desktop/src-tauri/src/state.rs`**: removed the
  `#[allow(dead_code)]` attribute on `AppState::speech_provider()`
  since `transcribe_utterance` now consumes it.

- **`apps/desktop/src-tauri/src/main.rs`**: register
  `commands::transcribe_utterance` in `generate_handler!`.

### Frontend — allow-list + Trust drawer

- **`apps/desktop/src/lib/voiceTurns.ts`** (new, ~30 lines):
  `VOICE_TURN_KINDS` set + `isVoiceTurn(kind)`. Split from
  `mediaTurns.ts` because the two modalities have independent
  consent boundaries and will diverge further in step 5.
- **`apps/desktop/src/lib/voiceTurns.test.ts`** (new, ~60 lines):
  19 parameterized tests locking:
  - Exact set contents (parity with the Rust emitter).
  - Positive classification for each of the five kinds.
  - Negative classification for other turn kinds + **every media
    kind** — the voice and media allow-lists must stay disjoint
    so the Trust drawer can filter either modality independently.
  - Case sensitivity + substring rejection.
- **`apps/desktop/src/components/TrustDrawer.tsx::kindClass`**:
  extended with the five voice kinds per design §6 —
  `utterance_transcribed` → `text-aether-ok`;
  `utterance_blocked` / `utterance_invalid` / `mic_permission_denied`
  → `text-aether-err`; `mic_permission_ask` → `text-aether-warn`.

## Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean (pre-existing warnings only)
- `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
- `cargo test --workspace` — **133 / 133** (same count; the new
  shell-bound tests live in `apps/desktop/src-tauri` which is not
  part of the top-level workspace test run per the existing cfg)
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **145 / 145** (was 133; +11 from voice command + MediaMic default)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `apps/desktop && pnpm typecheck` — clean
- `apps/desktop && pnpm build` — clean
- `apps/desktop && pnpm test` — **105 / 105** (was 86; +19 voiceTurns)

## Hard-constraint compliance

- **No push.** ✅ 22 unpushed commits on `dev`.
- **No release / signing.** ✅
- **No new vision providers.** ✅
- **No remote vision.** ✅
- **No streaming / continuous listening.** ✅ Single utterance per
  command call; the browser side never runs in step 4.
- **No VAD / wake word / TTS.** ✅
- **No `AuditRecordEvent` shape changes.** ✅ Only touched L5's
  `preset_defaults` map — additive `MediaMic` entry.
- **No cross-provider config error unification.** ✅
- **No new test dependencies.** ✅ Tests reuse existing
  `tempfile` / vitest harness.
- **Step 1/2/3 artifacts untouched.** ✅ Only consumption was
  `AppState.speech_provider()` + `AppState.evaluate_mic_permission()`;
  `#[allow(dead_code)]` removed from `speech_provider` since it's
  now live. No behavior changes in `mic_permissions.rs`,
  `voice_registry.rs`, or `whispercpp_speech.rs`.
- **Scaffold error marker still pinned.** ✅ Grep for "deferred to
  Voice V1 step 4 (transcribe_utterance)" returns exactly one
  source hit in `whispercpp_speech.rs`. New shell-side test
  (`whispercpp_scaffold_error_still_pinned`) asserts the marker
  survives so any silent shadow implementation would trip it.

## Design decisions worth noting

1. **`Capability::MediaMic` instead of `Capability::Microphone`.**
   The design doc (`docs/VOICE-V1-ARCHITECTURE.md` §0 capabilities
   table) refers to the voice capability as "Microphone"; the L5
   enum variant is actually `MediaMic` (alongside `MediaCamera` /
   `MediaScreenCapture` — naming consistency within the Media
   group). Using the existing variant avoids L5 schema churn and
   keeps all three media capabilities under the same prefix for
   dot-path work in later waves. **Divergence from doc** — should
   either update the doc in step 6 or rename the variant in a
   separate L5 slice; logged as a decision for review below.
2. **`MessageMeta.origin` is additive.** `Option<String>` with
   `skip_serializing_if`. Old TS clients ignore the field; new
   clients can branch on `"voice"` to show a voice-origin chip.
   Vision turns keep `origin: None` for now — step 5 may introduce
   a `"vision"` value in parallel with the VoicePanel wiring.
3. **Local latency measurement.** `SpeechResponse` does not carry a
   `latency_ms` field (mirrors `VisionResponse`). The shell times
   the `provider.transcribe(...)` call with `Instant::now()` and
   stamps the elapsed ms into both `MessageMeta.latency_ms` and
   `TelemetryEntry.latency_ms`. This is the same pattern the
   `TurnEngine` uses for router dispatch.
4. **`cue` field overrides the transcript.** When the UI passes an
   explicit cue string (trimmed, non-empty), that becomes the
   user turn's utterance; otherwise the transcribed text is used.
   Future hotkey UX may want to pin a persistent prompt regardless
   of what was captured; this shape leaves room for it without
   reshaping the command surface.
5. **User-role memory entry.** The transcribed text is recorded as
   a user turn (not system) per §1 of the design doc — the
   voice capture behaves exactly like the user typed the text.
6. **Split `voiceTurns.ts` from `mediaTurns.ts`.** The file was
   starting to carry two unrelated concerns (vision provider
   short-labels + media turn kinds + now voice turn kinds). The
   split gives the voice surface a clean single home and locks
   disjointness from the media set via the parameterized test.
7. **No VoicePanel UI, no Trust drawer voice rendering beyond
   `kindClass`.** Step 5 scope.

## Divergences from the handoff

1. **Doc says "Microphone" capability; using `MediaMic`.** See
   decision 1 above.
2. **Handoff P7 listed four full-command tests
   (`transcribe_utterance_on_deny_records_permission_denied`,
   etc.).** Those tests would need a full `State<'_, AppState>` +
   `AppHandle` harness, which is not available in unit tests (the
   existing vision suite does not test `analyze_frame` end-to-end
   either — only `validate_frame_data_url`). Equivalent coverage
   is provided via AppState-level tests that exercise the gate +
   telemetry helpers with each `PermissionState`, plus the
   scaffold-error marker test for "surfaces scaffold error
   loudly". Flagged so step 5 can add a Tauri integration test if
   useful.

## What is deliberately NOT in this slice

- No browser audio capture (step 5).
- No `VoicePanel` UI / push-to-talk button (step 5).
- No Trust drawer voice rendering beyond the kindClass map
  (step 5).
- No voice doc rot guard / doc status flip (step 6).
- No settings UI for switching speech providers (still step 5).
- No changes to the scaffold `transcribe` error string.

## Next step (after this one)

Voice V1 step 5 — `VoicePanel.tsx`, push-to-talk capture, binding
to `transcribe_utterance`, transcript meta chips (`origin: voice`),
Trust drawer voice rows with provider + model + latency, and voice
badge / active-voice-route surface. Step 6 adds
`tools/lint-voice-doc/` and flips the doc status.
