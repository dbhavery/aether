# Handoff — Continue the companion build (2026-05-13)

**Written:** 2026-05-12.
**Branch state:** `dev` at `94ba5c4` with **22 unpushed commits**
ahead of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Voice V1 step 5 — VoicePanel UI +
browser capture + transcript origin chips + Trust drawer voice
rows.

---

## 0. Morning status

1. `dev` is `94ba5c4`, 22 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-12 after Voice V1 step 4,
   all green:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean (pre-existing warnings only)
   - `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
   - `cargo test --workspace` — **133 / 133**
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **145 / 145** (was 133; +11 voice + media-default)
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **105 / 105** (was 86; +19 voiceTurns)

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `cda9201` | feat(l5-policy): add MediaMic to wave3_default |
| `c7b22a6` | feat(apps/desktop): transcribe_utterance command (Voice V1 step 4) |
| `94ba5c4` | feat(apps/desktop/src): VOICE_TURN_KINDS + TrustDrawer kindClass |

Reports:

- [VOICE_V1_STEP4_TRANSCRIBE_UTTERANCE_EXECUTION_REPORT_2026-05-12.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP4_TRANSCRIBE_UTTERANCE_EXECUTION_REPORT_2026-05-12.md)

## 2. Track status

### Track V — Vision V1: **DONE (maintenance only)**

No changes this round.

### Track VOICE — Voice V1: **Steps 1–4 COMPLETE**

- Step 1 — Mic permission surface: done.
- Step 2 — SpeechProvider trait + whisper.cpp scaffold: done.
- Step 3 — voice_provider.json + VoiceRegistry: done.
- **Step 4 — `transcribe_utterance` + validators + telemetry +
  audit: done (this run).**
- Step 5 — VoicePanel UI + browser capture + transcript origin
  chips + Trust drawer voice rows: next session.
- Step 6 — Rot guard + flip `docs/VOICE-V1-ARCHITECTURE.md` to
  "current": pending.

### Track PRESENCE — Presence V1: **Step 0 COMPLETE**

Unchanged from 2026-05-12 handoff.

- **Step 0 — Architecture doc: done.**
- Step 1 — `presence.json` config + Settings toggles: pending.
- Steps 2–6 (controller, engine, Tauri commands, UI, rot guard):
  pending.

### Track MEMORY — Memory V2: **Step 0 COMPLETE**

Unchanged from 2026-05-12 handoff.

- **Step 0 — Architecture doc: done.**
- Steps 1–7 pending.

## 3. Current Voice V1 surface (post-step-4)

- `<app_data>/mic_permissions.json` — tri-state mic consent (step 1).
- `<app_data>/voice_provider.json` — active speech provider + per-
  provider model map, additive-default-safe (step 3).
- `SpeechProvider` trait in L4 (step 2); `WhisperCppSpeechProvider`
  scaffold whose `transcribe` is still pinned to the "deferred to
  Voice V1 step 4 (transcribe_utterance)" marker. **Step 4 does
  NOT replace this scaffold** — real wire/FFI inference is whisper
  adapter work in a separate slice.
- `transcribe_utterance` Tauri command (new this step):
  - Input: `{ utterance_data_url, duration_ms, cue?, sample_rate,
    channels, language? }`.
  - Output: `Result<UtteranceOutcome, String>` where the outcome
    `kind` is one of the five telemetry kinds.
- `validate_utterance_data_url` + `maybe_apply_voice` helpers.
- Five TS voice turn kinds via `src/lib/voiceTurns.ts` (new):
  `utterance_transcribed`, `utterance_blocked`,
  `utterance_invalid`, `mic_permission_denied`,
  `mic_permission_ask`. Parameterized parity test locks
  disjointness from `MEDIA_TURN_KINDS`.
- `TrustDrawer.kindClass` updated for the five kinds
  (ok / err / warn coloring per design §6).
- `MessageMeta.origin: Option<String>` field (wire-additive);
  voice turns stamp `Some("voice")`.
- L5 `wave3_default` now includes `Capability::MediaMic` as Auto /
  Medium, same rationale as `MediaCamera` / `MediaScreenCapture`.

## 4. What to build next — Voice V1 step 5

Scope per `docs/VOICE-V1-ARCHITECTURE.md` §7:

### Browser capture + VoicePanel UI

- `apps/desktop/src/components/VoicePanel.tsx`:
  - Push-to-talk button (hold-to-record or tap-to-toggle —
    call it in the design; keep it single-utterance either way).
  - `navigator.mediaDevices.getUserMedia({ audio: { sampleRate:
    16000, channelCount: 1 } })` (or equivalent) — decode to PCM
    16 kHz mono WAV, base64-encode as `data:audio/wav;base64,...`,
    call `transcribe_utterance`.
  - Visible mic-active state + clear error states.
  - No continuous listening, no VAD, no wake word, no streaming.

### Transcript meta chip

- Transcript user turns whose `meta.origin === "voice"` show a
  subtle chip (e.g. a small "voice" label next to the provider /
  model / latency footer).
- Assistant turns served from a voice origin carry the STT model
  id in `meta.model` and a `latency_ms` reflecting the STT call.

### Trust drawer voice rows

- Voice turn rows render provider + model + latency (mirror the
  vision row layout; long ids middle-truncate via the shared
  `truncateMiddleForDisplay`).
- Audit tab annotations: capability + scope only
  (provider/model intentionally absent — audit contract).

### Voice badge / active-voice-route surface

- Mirror `VisionBadge` / `ActiveVisionRoute` — dot + provider +
  model + status, and a "→ provider · model" hint above the
  Record button.
- Read from a new `src/lib/speechProviders.ts` (id ↔ short-label
  table, mirror of `visionProviders.ts`).

### Tauri commands (needed by step 5 UI)

- `voice_status` + `list_voice_providers` + `list_speech_models` +
  `refresh_speech_models` + `set_active_speech_provider` +
  `set_active_speech_model`.
- All backed by the `AppState::speech_*` accessors already landed
  in step 3 (currently `#[allow(dead_code)]`; drop the attrs as
  each is consumed).

### Tests

- VoicePanel unit tests (mocked `invoke`).
- TrustDrawer voice-row rendering tests.
- Parity test for `SPEECH_PROVIDER_IDS`.
- TrustDrawer kindClass snapshot (optional).

## 5. Decisions for Don's review (still open)

Carried over + new:

1–12. (Carried from 2026-05-12 handoff.) No changes this run.
13. **L5 variant name vs design doc.** The voice design doc calls
    the capability "Microphone"; the L5 enum variant is
    `MediaMic`. Step 4 uses `MediaMic` to avoid L5 schema churn.
    Either (a) update the doc in step 6 when it flips to current,
    or (b) rename the variant in a standalone L5 slice (additive-
    only: add `Microphone` as an alias → deprecate `MediaMic`).
    Recommend (a) — doc correction is cheap; renaming the enum
    touches the audit contract and the existing media-group
    naming symmetry.
14. **`MessageMeta.origin` semantic.** Currently only `"voice"`
    is emitted. Future modalities can add values (e.g. `"vision"`
    during step 5 if useful for transcript chipping, `"text"`
    never — text is the baseline). Worth deciding whether vision
    turns should stamp `origin: "vision"` for symmetry.
15. **User cue override vs transcription.** Step 4 honors an
    explicit `cue` when non-empty, overriding the transcribed
    text. If step 5's push-to-talk UI never passes a cue, this is
    dead code. Keep it for hotkey-pinned prompts, or remove in
    step 5 if the shape is settled.

## 6. Risks / things to review first

- **22 unpushed commits.** Hash sequence:
  - Prior 19 (pre-step-4, see 2026-05-12 handoff).
  - `cda9201` — L5 MediaMic default.
  - `c7b22a6` — transcribe_utterance command + tests.
  - `94ba5c4` — VOICE_TURN_KINDS + TrustDrawer kindClass.
- **Voice V1 doc is still "design-only"** — steps 1–4 implemented
  but doc flip comes at step 6 when the full surface is stable.
  Doc/code can drift silently until the rot guard lands.
- **Scaffold `transcribe` error still pinned.** A shell-side
  sanity test (`whispercpp_scaffold_error_still_pinned`) asserts
  the "deferred to Voice V1 step 4 (transcribe_utterance)" marker
  survives. Real STT inference is a separate whisper adapter
  slice — step 5 UI will continue to see the loud error when the
  user tries to capture, which is the correct UX until inference
  is wired.
- **Observer preset now denies MediaMic.** The Observer preset
  overlay (`with_preset_overlay`) flips every non-`FilesRead`
  capability to Deny. Adding `MediaMic` to `wave3_default` means
  Observer mode now blocks voice the same way it blocks camera/
  screen — correct by design, flagged in case any existing
  Observer-preset test needed updating (none did, all green).
- **Cross-feature test coverage.** `apps/desktop/src-tauri`
  tests run with all three provider features on. If a future CI
  config splits features, the
  `whispercpp_scaffold_error_still_pinned` test is `cfg`-gated to
  `speech-whispercpp` so other subsets stay green.

## 7. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `94ba5c4`, 22 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 stable and rot-guarded.
- Voice V1 steps 1–4 complete: mic permission surface,
  SpeechProvider + whisper.cpp scaffold, VoiceRegistry +
  voice_provider.json, transcribe_utterance + validators +
  telemetry + L5 audit at capture time.
- Presence V1 step 0 complete.
- Memory V2 step 0 complete.

Mandatory first steps:
1. Read `HANDOFF_2026-05-13_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read
   `VOICE_V1_STEP4_TRANSCRIBE_UTTERANCE_EXECUTION_REPORT_2026-05-12.md`.
4. Read `docs/VOICE-V1-ARCHITECTURE.md` §1 (flow), §7 (UI), and
   the mirrored vision files:
   - `apps/desktop/src/components/VisionBadge.tsx`
   - `apps/desktop/src/components/ActiveVisionRoute.tsx`
   - `apps/desktop/src/lib/visionProviders.ts`
5. Skim the already-wired voice backend:
   - `apps/desktop/src-tauri/src/commands.rs::transcribe_utterance`
   - `apps/desktop/src-tauri/src/voice_registry.rs`
   - `apps/desktop/src/lib/voiceTurns.ts`

Session focus: Voice V1 step 5 — VoicePanel UI + browser audio
capture + transcript origin chips + Trust drawer voice rows +
voice badge + active-voice-route surface.

Scope (mirror vision step 5):
- `VoicePanel.tsx` with push-to-talk capture. Capture 16 kHz mono
  WAV via getUserMedia; base64-encode as data:audio/wav;base64,...;
  call the `transcribe_utterance` command. Visible mic-active
  state, clear error copy, no streaming/continuous listening.
- New Tauri commands mirroring the vision surface: `voice_status`,
  `list_voice_providers`, `list_speech_models`,
  `refresh_speech_models`, `set_active_speech_provider`,
  `set_active_speech_model`. Drop `#[allow(dead_code)]` as each
  AppState accessor is consumed.
- `src/lib/speechProviders.ts` id ↔ short-label table.
- `VoiceBadge` + `ActiveVoiceRoute` components.
- Transcript `origin: "voice"` chip + MessageMeta rendering.
- Trust drawer voice rows (provider/model/latency).
- Tests: VoicePanel (mocked invoke), SpeechProviders parity,
  TrustDrawer voice-row snapshots.

Out of scope (step 6):
- `tools/lint-voice-doc/` rot guard.
- Flipping `docs/VOICE-V1-ARCHITECTURE.md` from design-only to
  current.

Hard constraints (still in force):
- No push.
- No release / signing.
- No remote vision / remote speech.
- No streaming / continuous listening / VAD / wake word / TTS.
- No `AuditRecordEvent` shape changes.
- No new heavy dependencies (prefer native Web APIs for audio
  capture; if a tiny WAV encoder helper is needed, either write
  it inline or reuse an already-pinned dep — do NOT add a new
  pnpm dep without flagging).
- No changes to the scaffold whispercpp `transcribe` error. Real
  STT inference is a separate slice; step 5 UI will continue to
  see the loud "deferred to Voice V1 step 4" error when the user
  records, and that's the correct UX.
- No violation of "no raw media persistence". Audio bytes live
  only inside the IPC frame; never written to disk, audit, or
  memory.
- No VAD preflight, no duration check on the shell (the design
  doc locks this — zero-duration WAVs are accepted and the
  provider returns empty).

Process:
1. Add the six new voice Tauri commands + register in main.rs.
2. Wire `src/lib/speechProviders.ts` mirror of visionProviders.
3. Build VoiceBadge + ActiveVoiceRoute.
4. Build VoicePanel with push-to-talk capture + WAV encoding.
5. Wire transcript origin chip rendering + Trust drawer voice
   rows.
6. Full check matrix (fmt, check, workspace tests, l4-router
   features, shell features, layer lint, vision doc lint,
   typecheck, build, pnpm test).
7. Fix all failures.
8. Commit in scoped slices.
9. Write execution report + fresh handoff.

Stay strictly on step 5. Step 6 (rot guard + doc flip) is the
next session.
```

---

(end of handoff)
