# Voice V1 Step 5 — VoicePanel UI + runtime swap + transcript origin — execution report (2026-05-13)

**Status:** Shipped locally on `dev` (commits `41c7f4e`, `923a3a0`, `bce66dc`). Push not authorized.

## Goal

Ship the user-facing voice surface end to end. Browser audio
capture, WAV encoding, `transcribe_utterance` wiring, route
visibility (VoiceBadge / ActiveVoiceRoute), Trust drawer voice
filter + row rendering, and a modality chip (`voice` / `vision`)
on transcript meta.

## Surfaces touched

### Backend — voice Tauri commands + vision origin symmetry

- **`apps/desktop/src-tauri/src/commands.rs`**:
  - `VoiceStatus` struct mirroring `VisionStatus` (no text-only
    fallback language — voice has none).
  - `SpeechModelList` mirroring `VisionModelList`.
  - Six Tauri commands: `voice_status`, `list_speech_providers`,
    `list_speech_models`, `refresh_speech_models`,
    `set_active_speech_provider`, `set_active_speech_model`. Share
    a `collect_speech_models` helper; no TTL cache yet since the
    whisper.cpp scaffold returns an empty list.
  - `analyze_frame` now stamps `MessageMeta.origin = "vision"` for
    symmetry with `transcribe_utterance`'s existing
    `origin = "voice"` stamp.
- **`apps/desktop/src-tauri/src/main.rs`**: registers the six new
  voice commands.

### Frontend — registry + encoder + api wrappers

- **`apps/desktop/src/lib/speechProviders.ts`** (new, mirror of
  `visionProviders.ts`):
  - `SPEECH_PROVIDER_REGISTRY` (currently `whispercpp-speech`),
    `SPEECH_PROVIDER_IDS`, `isSpeechProvider`,
    `speechProviderShortLabel`, `speechRouteSummary`.
  - 14 tests — parity with the Rust trait id, disjointness from
    vision ids, fallback behavior for unknown providers.
- **`apps/desktop/src/lib/wavEncoder.ts`** (new):
  - Pure-TS 16-bit PCM WAV encoder (`encodeWav`), chunked base64
    helper (`bytesToBase64`), convenience wrapper
    (`pcmToWavDataUrl`). Zero runtime dependencies.
  - 8 tests — header shape, sample clipping at [-1, 1], bad-arg
    rejection, base64 correctness on bytes with the high bit set,
    data URL output size satisfying the shell's
    `MIN_UTTERANCE_BODY_LEN = 64` floor.
- **`apps/desktop/src/lib/api.ts`** + **`types.ts`**:
  - `transcribeUtterance`, `voiceStatus`, `listSpeechModels`,
    `refreshSpeechModels`, `setActiveSpeechProvider`,
    `setActiveSpeechModel` wrappers.
  - Types: `UtteranceOutcome`, `TranscribeUtteranceRequest`,
    `SpeechProviderInfo`, `VoiceStatus`, `SpeechModelList`.
  - `MessageMeta` gains `origin?: "voice" | "vision"`.

### Frontend — UI components

- **`VoiceBadge.tsx`** (new): status badge + runtime-swap dropdown
  + model strip. Voice-specific wording for the disabled state
  ("Voice disabled" vs "Text-only fallback") — voice has no
  silent fallback.
- **`ActiveVoiceRoute.tsx`** (new): compact "→ provider · model"
  hint above the Record button. In the disabled state renders in
  `text-aether-warn` so the user knows the next record will
  error, not quietly disappear.
- **`VoicePanel.tsx`** (new): push-to-talk single-utterance
  capture. Flow:
  - Checks `getMicPermission` on open; Ask surfaces a
    one-click Allow, Deny short-circuits.
  - `navigator.mediaDevices.getUserMedia({ audio: { sampleRate:
    16000, channelCount: 1 } })` → WebAudio
    `MediaStreamAudioSourceNode` → `ScriptProcessorNode` captures
    Float32 buffers into a ref array.
  - On release: concatenates the buffers, encodes via
    `pcmToWavDataUrl` with the context's actual sample rate (some
    platforms only give 44.1 / 48 kHz regardless of the
    constraint — the WAV header writes the honest value), calls
    `transcribeUtterance`, tears down the stream immediately.
  - Surfaces every `UtteranceOutcome.kind` honestly (Deny, Ask,
    Invalid via rejected promise, Blocked, Transcribed).
  - Visible mic-active state (pulsing red dot + "Live capture —
    audio bytes are transient" note).
  - No continuous listening, no wake word, no VAD.
- **`Transcript.tsx`**: new `originChipForFooter` helper prepends
  a `voice` / `vision` chip to the assistant-message footer when
  `meta.origin` is set. Pure, unit-tested.
- **`TrustDrawer.tsx`**:
  - History filter gains a `voice` option alongside `all` / `media`.
    Counts are live; the voice and media kind sets are disjoint
    (locked by the parameterized TS test).
  - Per-row route badge now picks between speech and vision route
    summaries — speech takes priority when its provider id set
    matches. New `speechRouteTitle` helper mirrors
    `visionRouteTitle` for hover copy.
- **`Header.tsx`**: new Voice button between Screen and Settings.
- **`App.tsx`**: wires the VoicePanel drawer alongside the
  Camera / Screen ones.
- **`VoiceBadge.test.tsx`** (5 tests), **`ActiveVoiceRoute.test.tsx`**
  (8 tests), **`Transcript.test.tsx`** gains 5 new origin-chip
  tests.

## Full check matrix — all green

- `cargo fmt --all -- --check` — clean
- `cargo check --workspace` — clean (pre-existing warnings only)
- `cargo check -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — clean
- `cargo test --workspace` — **133 / 133**
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` — **86 / 86**
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp,speech-whispercpp` — **145 / 145** (no change vs step 4; voice command tests ride on the existing registry suite)
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `apps/desktop && pnpm typecheck` — clean
- `apps/desktop && pnpm build` — clean
- `apps/desktop && pnpm test` — **145 / 145** (was 105; +40 from
  speechProviders, wavEncoder, VoiceBadge, ActiveVoiceRoute,
  Transcript origin-chip additions)

### Flaky test note

`state::tests::yaml_persona_pack_merges_into_catalog` fails
intermittently when the full shell test suite runs in parallel
(env-var contamination between tests that set
`AETHER_PERSONAS_DIR`). Passes in isolation and on retry. Not a
step 5 regression — pre-existing and unrelated to Voice work.

## Hard-constraint compliance

- **No push.** ✅
- **No release / signing.** ✅
- **No remote speech providers.** ✅ `whispercpp-speech` only.
- **No continuous listening / wake word / VAD / TTS.** ✅
  Push-to-talk, single utterance per explicit user action,
  stream torn down on release.
- **No durable raw audio.** ✅ Audio lives in the IPC frame and
  the provider HTTP body only. VoicePanel holds Float32 buffers
  in a ref, flushed and discarded on release.
- **No AuditRecordEvent shape changes.** ✅ `MediaMic` was already
  added in step 4's preparatory slice.
- **No new heavy dependencies.** ✅ WAV encoder is pure TS,
  WebAudio/getUserMedia are native browser APIs.
- **No cross-provider config error unification.** ✅
- **No weakening of tests or rot guards.** ✅ TS test count went
  up; Rust suite unchanged beyond the shell-already-wired
  coverage.
- **Vision origin symmetry landed.** ✅ `analyze_frame` stamps
  `origin: "vision"` now that the chip render path exists.

## Design decisions worth noting

1. **WAV sample rate is context-honest.** The capture constraint
   requests 16 kHz, but some platforms (Windows WASAPI, macOS
   Core Audio) only expose 44.1 / 48 kHz regardless of what we
   ask for. The WAV header writes the actual
   `AudioContext.sampleRate` value so whisper.cpp sees a truthful
   rate and can resample itself if it needs to.
2. **ScriptProcessorNode over AudioWorklet.** Deprecated but
   widely supported and synchronous — simpler than AudioWorklet
   for a push-to-talk slice. A future refactor can swap to
   AudioWorklet if the deprecation accelerates; the API surface
   is trivial to rewrite.
3. **No TTL cache for speech models yet.** `list_speech_models`
   and `refresh_speech_models` both call the collector directly
   because the whisper.cpp scaffold returns an empty list today.
   When a real STT backend exposes discovery, mirror
   `vision_cache.rs::ModelListCache` into a `speech_cache.rs`.
4. **Voice disabled is a LOUD state.** Unlike vision's text-only
   fallback (muted grey), `Voice disabled` renders in warn color
   and the ActiveVoiceRoute hint reads "Voice disabled —
   configure a speech provider" to match the backend's
   no-silent-fallback contract.
5. **Cue field unused by the UI.** `TranscribeUtteranceRequest.cue`
   is hard-coded to `null` from the panel. Kept in the wire
   contract for future hotkey-pinned prompts; a session-long
   "force this cue" toggle is possible without shape churn.
6. **Vision `origin: "vision"` symmetry.** Cheap — one line in
   `analyze_frame`. The transcript footer and future Trust
   filters benefit from both modalities labeling themselves.

## Divergences from the handoff

None worth calling out — the handoff's P5 ("provider-switch
commands if needed") explicitly allowed adding them when they
make the UI coherent. All six commands landed.

## What is deliberately NOT in this slice

- Voice rot guard — step 6.
- Flipping the voice doc status — step 6.
- Real whisper.cpp inference wiring — separate slice.
- Trust drawer audit-side voice treatment (Audit tab stays purely
  capability + scope; provider/model intentionally absent per
  design §7).
- Threshold editing for Presence V1 (separate track).

## Next step

Voice V1 step 6 — rot guard + doc status flip. (Landed in a
separate execution report below / same session.)
