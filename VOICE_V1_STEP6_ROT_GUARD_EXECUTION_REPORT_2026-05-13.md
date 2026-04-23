# Voice V1 Step 6 — rot guard + doc flip — execution report (2026-05-13)

**Status:** Shipped locally on `dev` (commit `8ceb250`). Push not authorized.

## Goal

Close Voice V1 as a subsystem. Mirror the vision rot guard so
silent drift between `docs/VOICE-V1-ARCHITECTURE.md` and the code
becomes a fast test-time failure; flip the doc status from
"design-only" to "current"; fix the one divergence the rot guard
immediately caught.

## Surfaces touched

### New rot guard

- **`tools/lint-voice-doc/check.py`** — mirror of
  `tools/lint-vision-doc/check.py`. Carries a 48-anchor manifest
  covering:
  - §1 command entry points + helpers (`transcribe_utterance`,
    `maybe_apply_voice`, `validate_utterance_data_url`,
    `record_utterance_early_exit_telemetry`,
    `MIN_UTTERANCE_BODY_LEN`).
  - §1 permission gate (`mic_permissions.rs`, `MicPermission`,
    `permission_path_for`, `mic_permissions.json`).
  - §2 providers (`packages/l4-router/src/speech.rs`,
    `SpeechProvider`/`SpeechRequest`/`SpeechResponse`,
    `split_audio_data_url`, `WhisperCppSpeechProvider`,
    `WhisperCppSpeechConfig`, `whispercpp-speech` id, all three
    env knobs).
  - §3-4 registry + persistence (`voice_registry.rs`,
    `VoicePersistedState`, `voice_persistence_path_for`,
    `auto_select_first_if_unset`, `seed_missing_models_from_adapters`,
    `voice_seed_missing_models` on AppState,
    `voice_provider.json` filename).
  - §6 telemetry kinds on both Rust and TS sides (five kinds
    present in both `commands.rs` and `voiceTurns.ts`, plus
    `VOICE_TURN_KINDS`).
  - §7 UI surfaces: `speechProviders.ts`,
    `SPEECH_PROVIDER_REGISTRY`, and the four components
    (`VoiceBadge`, `ActiveVoiceRoute`, `VoicePanel`,
    `TrustDrawer.kindClass`).
- **`tools/lint-voice-doc/README.md`** — mirrors the vision lint
  README.

### Doc status flip

- **`docs/VOICE-V1-ARCHITECTURE.md`**:
  - Header flipped from `Design-only as of 2026-05-08` →
    `Current as of 2026-05-13`.
  - Doc intro updated to reference the new `tools/lint-voice-doc/`
    rot guard instead of the deferred-future language.
  - Capability table corrected: `Microphone` → `MediaMic` (the
    canonical L5 variant). The rot guard would have caught this
    on the first run if the doc had been flipped without the fix.
  - Flow diagram line updated: "invoke turn engine with capability
    MediaMic".

## Lint output

```
voice-doc rot-guard: OK
  doc: docs/VOICE-V1-ARCHITECTURE.md (Status: Current as of 2026-05-13)
  checked 48 anchors across 12 files.
```

## Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — 51 anchors
- `python tools/lint-voice-doc/check.py` — **48 anchors** (new)
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` — 145 / 145

## Hard-constraint compliance

- **No push.** ✅
- **No code changes outside the anchor-fix noted above.** ✅ Only
  the doc was edited; the `MediaMic` / `Microphone` divergence
  was already correct in the code per step 4.
- **No new heavy dependencies.** ✅ Python standard library only.

## Design decisions worth noting

1. **48 anchors vs vision's 51.** The voice surface has no
   model-list TTL cache today (whisper.cpp scaffold returns
   empty), so the three `vision_cache.rs` anchors don't have
   voice equivalents. When a real speech cache lands, add three
   anchors.
2. **README deliberately thin.** The vision README has the full
   rationale; the voice README points at it and keeps the PR
   diff small. Saves maintenance if we ever revise the rot-guard
   policy — one README to update.
3. **The guard caught the "Microphone" → "MediaMic" divergence
   on its first run.** The step 4 execution report called this
   out as a decision for review; landing the guard forced the
   fix instead of letting it sit.

## Next step

Voice V1 subsystem is now closed. Next modality or step:

- Presence V1 step 1 — `presence.json` + Settings toggles
  (if the session has room).
- Real whisper.cpp inference wiring is a separate slice, unlocked
  whenever the user wants to prioritize it.
