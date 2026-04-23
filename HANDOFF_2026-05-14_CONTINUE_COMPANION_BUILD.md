# Handoff — Continue the companion build (2026-05-14)

**Written:** 2026-05-13.
**Branch state:** `dev` at `209fca1` with **6 unpushed commits**
ahead of `origin/dev`.
**Push status:** **Not authorized for this session.**
**Next session mode:** Presence V1 step 2 (controller + OS-idle
probe + event emission) and/or real whisper.cpp inference wiring,
at the user's direction.

---

## 0. Morning status

1. `dev` is `209fca1`, 6 commits ahead of `origin/dev`.
2. Working tree clean.
3. Full check matrix run 2026-05-13 after Voice V1 steps 5 & 6
   and Presence V1 step 1 — all green:
   - `cargo fmt --all -- --check` — clean
   - `cargo check --workspace` — clean
   - `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
   - `cargo test --workspace` — **133 / 133**
   - `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
   - `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **154 / 154** (was 145; +9 presence_config)
   - `python tools/lint-layer-boundaries/check.py` — 0 violations
   - `python tools/lint-vision-doc/check.py` — OK, 51 anchors
   - `python tools/lint-voice-doc/check.py` — **OK, 48 anchors** (new)
   - `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — **145 / 145** (was 105; +40)

### Known flaky test

`state::tests::yaml_persona_pack_merges_into_catalog` can
intermittently fail under parallel shell test runs because
multiple tests set `AETHER_PERSONAS_DIR`. Retry passes, isolated
run passes. Not related to this session's changes.

## 1. What landed in this run

| SHA | Subject |
| --- | --- |
| `41c7f4e` | feat(apps/desktop): voice Tauri commands + vision origin symmetry (Voice V1 step 5) |
| `923a3a0` | feat(apps/desktop/src/lib): speech provider registry + WAV encoder + voice API wrappers |
| `bce66dc` | feat(apps/desktop/src/components): VoicePanel UI + voice Trust rows + origin chip (Voice V1 step 5) |
| `8ceb250` | feat(tools): lint-voice-doc rot guard + flip VOICE-V1 doc to current (Voice V1 step 6) |
| `209fca1` | feat(presence): presence.json + Settings toggles (Presence V1 step 1) |

Reports:

- [VOICE_V1_STEP5_UI_EXECUTION_REPORT_2026-05-13.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP5_UI_EXECUTION_REPORT_2026-05-13.md)
- [VOICE_V1_STEP6_ROT_GUARD_EXECUTION_REPORT_2026-05-13.md](file:///C:/Users/dbhav/Projects/aether/VOICE_V1_STEP6_ROT_GUARD_EXECUTION_REPORT_2026-05-13.md)
- [PRESENCE_V1_STEP1_CONFIG_EXECUTION_REPORT_2026-05-13.md](file:///C:/Users/dbhav/Projects/aether/PRESENCE_V1_STEP1_CONFIG_EXECUTION_REPORT_2026-05-13.md)

## 2. Track status

### Track V — Vision V1: **DONE (maintenance only)**

No changes this round beyond the cheap
`origin: "vision"` symmetry stamp on `analyze_frame`.

### Track VOICE — Voice V1: **COMPLETE** 🎉

- Step 1 — Mic permission surface ✅
- Step 2 — SpeechProvider + whisper.cpp scaffold ✅
- Step 3 — VoiceRegistry + voice_provider.json ✅
- Step 4 — transcribe_utterance + validators + telemetry + audit ✅
- **Step 5 — VoicePanel UI + browser capture + Trust drawer rows
  + origin chip ✅ (this run)**
- **Step 6 — Voice doc rot guard + doc flip to "current" ✅ (this
  run)**

The voice subsystem is now shipped as a coherent user-facing
surface. `transcribe` still uses the whisper.cpp scaffold error
(real inference is a separate slice) but the entire capture,
permission, registry, UI, audit, and rot-guard path is live.

### Track PRESENCE — Presence V1: **Step 1 COMPLETE**

- Step 0 — Architecture doc ✅
- **Step 1 — presence.json + Settings toggles ✅ (this run)**
- Step 2 — Presence controller + OS-idle probe + event emission:
  pending.
- Step 3 — Trust drawer presence-history rendering: pending.
- Step 4 — Presence rot guard: pending.

### Track MEMORY — Memory V2: **Step 0 COMPLETE** (unchanged)

## 3. Current Voice V1 + Presence V1 surface

### Voice (post-step-6)

- `<app_data>/mic_permissions.json` — tri-state mic consent.
- `<app_data>/voice_provider.json` — active speech provider +
  per-provider model map, additive-default-safe.
- L4 `SpeechProvider` trait; `WhisperCppSpeechProvider` scaffold
  (real transcribe pinned to the "deferred" error marker).
- `transcribe_utterance` Tauri command with MediaMic L5 audit,
  five telemetry kinds, no silent fallback.
- Six runtime-swap commands: `voice_status`,
  `list_speech_providers`, `list_speech_models`,
  `refresh_speech_models`, `set_active_speech_provider`,
  `set_active_speech_model`.
- UI: VoicePanel (push-to-talk), VoiceBadge,
  ActiveVoiceRoute, Trust drawer voice filter + row rendering,
  transcript origin chip (`voice`/`vision`).
- Rot guard: `tools/lint-voice-doc/check.py` (48 anchors).

### Presence (post-step-1)

- `<app_data>/presence.json` — enabled toggle, idle/away
  thresholds, history_in_trust_drawer toggle. Additive-default-
  safe.
- `get_presence_config` / `set_presence_config` Tauri commands.
- Settings drawer Presence section with two toggles + read-only
  threshold line.
- No L5 gate, no audit rows (per design §4).
- No controller / event capture yet (step 2).

## 4. What to build next

Two tracks can reasonably come next; the user picks.

### Option A — Presence V1 step 2

Presence controller + OS-idle probe + event emission:

- `PresenceController` trait + in-memory impl (state machine:
  `Active ↔ Idle ↔ Away`, poll loop at `poll_hz` ~2 Hz,
  transitions driven by idle + focus + turn-state per design §2).
- OS-idle probe (`user32.dll::GetLastInputInfo` on Windows,
  `CGEventSourceSecondsSinceLastEventType` on macOS, `XScreenSaver`
  on Linux — Windows-only is fine for v1 as long as the abstraction
  isn't Windows-specific).
- `presence_status` Tauri command (current state +
  updated_at_ms, mirrors the existing `presence_current`
  interaction-presence contract — decide whether to alias or
  split).
- Transition ring buffer + bounded cap per design §2.
- Settings: threshold editing controls (replace the read-only
  line with editable number fields).
- Tests: state-machine transitions, disabled-path no-op, idle
  probe boundary behavior (mock the OS probe), config reload
  after `set_presence_config`.

### Option B — Real whisper.cpp inference

Swap the scaffold `transcribe` for a real HTTP-server call:

- Pick a transport (whisper-server HTTP `/inference` endpoint is
  the obvious choice) and implement the actual multipart / JSON
  request.
- Preserve the scaffold error marker as a fallback for
  unreachable servers so the step-4 test stays meaningful.
- Add integration tests behind a `speech-whispercpp-live` feature
  flag so CI without a running server stays green.

### Option C — Memory V2 step 1

L5 capability additions (`MemoryWrite`, `MemoryRead`, etc.) as
additive-only enum variants, with L5-only tests first. This is
the gating slice before any Memory V2 plumbing.

## 5. Decisions for Don's review

Carried over + new:

1–15. (Carried from 2026-05-13 handoff.) No changes this run.
16. **`MediaMic` vs "Microphone" — resolved.** Step 6 rot guard
    flip corrected the doc to match the L5 variant. Decision 13
    from the previous handoff is closed.
17. **`MessageMeta.origin = "vision"` for vision turns.** Landed
    cheaply in step 5. Text turns still carry no origin; no
    reason to change that.
18. **Voice `cue` field unused by the UI.** VoicePanel passes
    `cue: null`. Kept for future hotkey-pinned prompts. If still
    unused when step 6 of some future voice refinement round
    lands, consider removing.
19. **No TTL cache for speech models yet.** Single-code-path
    collector for `list_speech_models` + `refresh_speech_models`.
    Revisit when a real STT backend exposes model discovery.
20. **WAV encoder writes the AudioContext's actual sample rate,
    not the requested 16 kHz.** Honest header; whisper.cpp
    resamples as needed.
21. **Presence threshold editing deferred to step 2.** Settings
    shows a read-only line; edit controls land with the
    controller so the user doesn't have sliders that steer a
    no-op controller.

## 6. Risks / things to review first

- **6 unpushed commits.** All local to `dev`; push remains NOT
  authorized unless the user says otherwise.
- **Voice rot guard newly blocking.** Any future refactor that
  renames `transcribe_utterance`, `MIN_UTTERANCE_BODY_LEN`, one
  of the five telemetry kinds, `VOICE_TURN_KINDS`,
  `SPEECH_PROVIDER_REGISTRY`, or any of the four component files
  will fail `tools/lint-voice-doc/check.py`. Update the manifest
  + doc in the same PR.
- **Flaky persona pack test.** See §0 known flaky; not a
  regression; a future cleanup should migrate the env-var seams
  to a per-test `TempDir`.
- **VoicePanel relies on `ScriptProcessorNode`** — deprecated
  but still widely supported. If the browser runtime stops
  providing it, swap to AudioWorklet; the API surface is small.
- **Presence controller is NOT yet running.** The
  `enabled = true` toggle is cosmetic until step 2 lands. Don't
  build features that assume live presence events are flowing
  yet.

## 7. Recommended next prompt (copy-paste)

```md
You are Claude Code, continuing work on Aether.

Repo root:
C:/Users/dbhav/Projects/aether/

Branch:
dev

Current state (treat repo as source of truth if anything differs):
- `dev` is at `209fca1`, 6 commits ahead of `origin/dev`.
- Working tree clean.
- Push is NOT pre-authorized.
- Vision V1 stable and rot-guarded.
- Voice V1 COMPLETE through step 6 (UI + rot guard + doc flip).
  `transcribe` still uses the scaffold error — real whisper.cpp
  inference is a separate slice.
- Presence V1 step 1 complete: presence.json + Settings toggles.
- Memory V2 step 0 complete (design doc only).

Mandatory first steps:
1. Read `HANDOFF_2026-05-14_CONTINUE_COMPANION_BUILD.md` end to end.
2. `git status` and `git log --oneline -30`.
3. Read the three 2026-05-13 execution reports referenced in the
   handoff.

Session focus: pick ONE of
  (A) Presence V1 step 2 — presence controller + OS-idle probe
      + event emission + threshold editing UI.
  (B) Real whisper.cpp inference wiring (unlocks push-to-talk
      for real).
  (C) Memory V2 step 1 — L5 capability additions (additive-only,
      L5-tests-first).

Scope for Option A (recommended default):
- Read `docs/PRESENCE-V1-ARCHITECTURE.md` §1-5 end to end.
- Add a PresenceController trait + in-memory impl with the
  Active / Idle / Away state machine and a poll loop at `poll_hz`.
- OS-idle probe — pick Windows-first via `GetLastInputInfo`,
  keep the trait abstraction multi-platform.
- `presence_status` Tauri command mirroring the existing
  interaction-presence contract.
- Ring buffer of transitions per design §2.
- Threshold editing controls in Settings (replace the read-only
  line from step 1).
- Tests: state transitions, disabled-path no-op, threshold edge
  cases, config reload hot-swap.

Hard constraints (still in force):
- No push.
- No release / signing.
- No L5 capability gate or audit rows for presence (design §4).
- No continuous audio / video capture; Presence tracks OS idle
  + focus + turn-state only.
- No new heavy dependencies; prefer platform-native idle probes
  or a small crate (`user-idle` or equivalent is acceptable if
  pure-Rust and small — flag in the execution report).
- Do not destabilise the voice rot guard (48 anchors) or the
  vision rot guard (51 anchors).

Process:
1. PresenceController trait + in-memory impl + state machine.
2. OS-idle probe behind a small trait for testability.
3. Poll loop (tokio or std::thread — pick based on existing
   presence patterns in the shell).
4. Tauri command + TS wrappers + UI threshold controls.
5. Tests.
6. Full check matrix.
7. Fix all failures.
8. Commit in scoped slices.
9. Execution report + fresh handoff.
```

---

(end of handoff)
