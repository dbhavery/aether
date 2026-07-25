# Voice v1 — architecture reference

> **Status:** Current as of 2026-05-13.
> **Scope:** Short-turn voice input — a local-first,
> push-to-talk-style single-utterance speech-to-text adapter. The
> captured text becomes a user turn in the existing transcript /
> memory / policy pipeline.
> **Out of scope for v1:** streaming transcription, continuous
> listening, voice-activity detection, wake words, text-to-speech,
> remote STT providers, multimodal interleaving of audio + video
> frames inside a single turn.

This doc mirrors `docs/VISION-V1-ARCHITECTURE.md` section by section
so future readers can reason about both modalities against a shared
shape. A rot-guard manifest at `tools/lint-voice-doc/check.py`
enforces that the file paths, symbols, and string constants this
doc references still exist in code — when the guard fails, either
restore the code or update the doc and the manifest in the same PR.

---

## 0. Design parity with Vision v1

The vision track has already proven the pattern. Voice v1 reuses it
deliberately so that the code that gates the camera also gates the
microphone, and the UI surfaces a user learns for vision are
recognizable when they meet voice.

Shared contract:

| Aspect                    | Vision v1                              | Voice v1                                      |
| ------------------------- | -------------------------------------- | --------------------------------------------- |
| Capture model             | single frame (camera or screen)        | single utterance (push-to-talk)               |
| Permission storage        | `<app_data>/media_permissions.json`    | `<app_data>/mic_permissions.json`             |
| Permission tri-state      | Allow / Ask / Deny                     | Allow / Ask / Deny                            |
| Capability                | `MediaCamera` / `MediaScreenCapture`   | `MediaMic`                                    |
| Payload                   | `data:image/...;base64,<body>`         | PCM WAV bytes, base64 in IPC                  |
| Payload persistence       | transient                              | transient                                     |
| Provider trait            | `VisionProvider`                       | `SpeechProvider`                              |
| Default local adapter     | Ollama, llama.cpp                      | whisper.cpp (candidate)                       |
| Persistence file          | `vision_provider.json`                 | `voice_provider.json`                         |
| Trust drawer              | provider · model · kind                | provider · model · kind                       |
| Audit                     | capability + scope only                | capability + scope only                       |
| Telemetry kinds           | 5 (frame_*, permission_*)              | 5 (utterance_*, mic_permission_*)             |

Everything not in this table should have a specific reason for
diverging. Divergences are called out explicitly where they appear.

---

## 1. End-to-end flow

```
[user]
  │ enables Microphone permission in Settings (tri-state)
  │
[VoicePanel — apps/desktop/src/components/VoicePanel.tsx (TBD)]
  │ push-to-talk: user holds a button or presses a hotkey
  │ captures PCM 16kHz mono WAV as data:audio/wav;base64,<body>
  │ invokes `transcribe_utterance` over Tauri IPC
  │
[transcribe_utterance — apps/desktop/src-tauri/src/commands.rs (TBD)]
  │ 1. evaluate mic permission gate (Allow|Ask|Deny)
  │    - Deny / Ask → telemetry("mic_permission_denied"|"mic_permission_ask"),
  │      memory record (Deny only), short-circuit
  │ 2. validate_utterance_data_url(payload)
  │    - Err → telemetry("utterance_invalid"), short-circuit
  │ 3. record system-role memory: "[voice capture] {duration}s"
  │    (no raw audio, no transcript yet — that happens after STT)
  │ 4. invoke turn engine with capability MediaMic
  │    (resource scope none)
  │
[TurnEngine — packages/* through L5/L6]
  │ runs the persona prompt + L5 policy. No provider info enters L5.
  │
[maybe_apply_voice — apps/desktop/src-tauri/src/commands.rs (TBD)]
  │ a. require an active speech provider; else return Err
  │    (unlike vision, there is no "fall back to text" — if voice
  │    fails, the user's utterance is lost; surface a clear error)
  │ b. mirror validate_utterance_data_url (defense in depth)
  │ c. split_data_url → (mime, base64 body)
  │ d. provider.transcribe(SpeechRequest { audio_b64, mime,
  │       sample_rate, channels })
  │    - Ok → returns SpeechResponse { text, confidence, latency_ms,
  │             tokens_in, tokens_out? }
  │    - Err → WARN + user-facing error. No silent fallback.
  │
[provider — packages/l4-router/src/providers/whispercpp_speech.rs (TBD)]
  │ HTTP call to local whisper.cpp server OR in-process FFI.
  │ Reports current_model() back through SpeechStatus.
  │
[result assembly — back in transcribe_utterance]
  │ build USER TranscriptMessage (the transcribed text)
  │ attach MessageMeta { tier, provider, model, latency_ms, tokens,
  │                      origin: "voice" }
  │ record telemetry kind="utterance_transcribed" | "utterance_blocked"
  │ then feed the transcript into the normal turn engine so the
  │ assistant responds as if the user had typed the text.
  │ emit to UI via Tauri event
  │
[Transcript / TrustDrawer — apps/desktop/src/components/]
  │ user turn renders with a "voice" provenance badge
  │ footer: provider · model · latency · tokens
  │ Trust drawer History tab annotates with provider · model
  │ long ids middle-truncate, full id in title tooltip
```

Audio bytes are **transient** at every layer: they exist only inside
the IPC frame, the `SpeechRequest`, and the provider HTTP body.
Nothing persists them to disk, the audit log, durable memory, or
structured telemetry. The **transcript text** is persisted because
it becomes a user turn — same as if the user had typed.

### Divergence from vision: no text-only fallback

In vision, if the provider fails, `maybe_apply_vision` falls back
to a text-only response built from the cue string. Voice has no
equivalent "silent fallback" — if STT fails, the utterance is
lost. The user sees a clear error ("Transcription failed. Try
speaking again.") and can retry or switch to typing. Silently
swallowing a user's utterance would be a worse UX than a visible
error.

---

## 2. Providers

v1 ships **one local adapter** (candidate: whisper.cpp). A second
adapter is its own track. A remote adapter is its own track and
triggers the privacy-posture work covered in §9.

### whisper.cpp candidate (`WhisperCppSpeechProvider`)

- `id() = "whispercpp-speech"`
- Crate: `aether-l4-router`, gated by feature `speech-whispercpp`.
- Config via env (`WhisperCppSpeechConfig::from_env`):
  - `AETHER_WHISPERCPP_SPEECH_BASE_URL` (default
    `http://127.0.0.1:8081` if using the HTTP server wrapper,
    or process-local if using the C FFI path — pick one in
    implementation and document)
  - `AETHER_WHISPERCPP_SPEECH_MODEL` (e.g. `ggml-base.en.bin`)
  - `AETHER_WHISPERCPP_SPEECH_LANGUAGE` (default `auto`)
  - timeouts follow the rest of the family.
- Boot WARN includes the base URL (HTTP mode) or model path (FFI
  mode) when the healthcheck fails.
- Model discovery: filesystem scan of the models directory for
  `.bin` files matching the whisper.cpp naming convention.

All adapters would implement `SpeechProvider` (mirrors
`VisionProvider`):

```
pub trait SpeechProvider: Send + Sync {
    fn id(&self) -> &'static str;
    fn label(&self) -> String;
    fn transcribe(&self, request: SpeechRequest)
        -> Result<SpeechResponse, L4Error>;
    fn set_model(&self, id: &str) -> Result<(), L4Error>;
    fn current_model(&self) -> Option<String>;
    fn healthcheck(&self) -> Result<(), L4Error>;
    fn list_models(&self) -> Result<Vec<String>, L4Error>;
}
```

Request / response shapes:

```
pub struct SpeechRequest {
    pub audio_b64:   String,  // base64-encoded PCM WAV body
    pub mime:        String,  // "audio/wav"
    pub sample_rate: u32,     // expected 16000
    pub channels:    u16,     // expected 1 (mono)
    pub language:    Option<String>,
}

pub struct SpeechResponse {
    pub text:       String,
    pub confidence: Option<f32>,  // whisper provides avg logprob
    pub latency_ms: u64,
    pub tokens_in:  Option<u64>,
    pub tokens_out: Option<u64>,
}
```

Provider config errors (e.g. `WhisperCppConfigError`) are **not**
unified with `OllamaConfigError` / `LlamaCppConfigError`. Each
adapter owns its own taxonomy — same constraint as vision.

---

## 3. `voice_provider.json` contract

Path: `<app_data>/voice_provider.json` (alongside
`media_permissions.json`, `mic_permissions.json`, and
`vision_provider.json`).

Proposed shape:

```json
{
  "active": "whispercpp-speech",
  "model_per_provider": {
    "whispercpp-speech": "ggml-base.en.bin"
  }
}
```

Contract (same rules as `vision_provider.json`):

- **Additive** — new fields may be added by future builds.
- **Default-safe on read** — `model_per_provider` gets a `serde`
  default; `active` is `Option<String>`.
- **Unknown fields silently ignored on read.**
- **Unknown fields dropped on rewrite.** Documented limitation;
  should be locked by test
  (`voice_registry::tests::unknown_fields_are_dropped_on_rewrite`)
  in implementation.
- **Malformed JSON falls back to default state with a WARN that
  names the file path.**
- **Persistence is single-writer through `VoiceRegistry`.**

A `voice_persistence_path_for(app_data_dir)` helper would give
tests a deterministic path under `TempDir`.

---

## 4. Provider / model selection rules

Mirrors `VisionRegistry`. Implemented in `VoiceRegistry`
(`apps/desktop/src-tauri/src/voice_registry.rs` — TBD).

### Active provider

- Persisted `active` id wins on boot.
- Unknown persisted id → fall back to first registered provider
  (insertion order).
- Explicit `None` → respected (voice disabled).
- `set_active(None)` clears the selection and persists.
- `auto_select_first_if_unset()` runs once at boot when no active
  id has been chosen and at least one provider is registered.

### Per-provider model

- `model_per_provider` survives provider swaps.
- `set_active_model(id)` writes through both the in-memory map and
  the active adapter (`provider.set_model(id)`), then persists.
- Persisted entries for unregistered provider ids are retained but
  not applied.
- First-launch seeding: when an adapter is registered but its id
  has no entry in `model_per_provider`, the adapter's
  `current_model()` is written through. Idempotent on subsequent
  boots.

### Model-list TTL cache

Same design as `ModelListCache`:

- Default TTL: 60 seconds.
- Env override: `AETHER_VOICE_MODEL_TTL_SECS`.
- Bounded `[5, 3600]` seconds.
- TTL read once at boot.
- Boot log line is unconditional INFO.
- UI exposes a manual refresh that bypasses the TTL.

---

## 5. Utterance validation

Two enforcement points; same rules.

### Shell side — `validate_utterance_data_url`

Returns `Result<&str, String>` (the `Ok` is the body slice).

Rules in order:

1. URL must start with `data:audio/wav` (v1 pins to WAV; future
   versions may widen to other uncompressed PCM containers).
2. URL must contain a comma (the base64 body separator).
3. The substring after the comma, once trimmed, must be non-empty.
4. The trimmed body must be at least `MIN_UTTERANCE_BODY_LEN` chars
   (propose: 64, i.e. ~48 bytes of raw audio — smaller is
   definitely a broken capture).

On `Err`, `transcribe_utterance` returns
`{detail}. Try recording again.` to the UI **and** records an
`utterance_invalid` telemetry entry.

### Vision side → voice-analog — `maybe_apply_voice`

Mirrors `validate_utterance_data_url` before delegating to the
provider. On `Err`:

- Logs at **debug**, not WARN (the shell-side gate already owned
  this case in production).
- Returns an error — not `None` — because unlike vision, there is
  no text fallback path.

### Divergence: no duration / VAD check

v1 does not inspect the audio to check duration, clipping, or
speech presence. A zero-duration or silence-only WAV will be
accepted at the shell layer and rejected (or return an empty
transcript) by the provider. This keeps the shell pure and the
provider honest; adding a preflight VAD is a future track.

---

## 6. Telemetry kinds (voice-related)

The `transcribe_utterance` path would emit exactly **five** kinds.
The TS allow-list (future:
`apps/desktop/src/lib/voiceTurns.ts::VOICE_TURN_KINDS`) mirrors the
list and is unit-tested for parity.

| kind                     | when                                                                          | in audit? |
| ------------------------ | ----------------------------------------------------------------------------- | --------- |
| `utterance_transcribed`  | provider returned a transcript                                                | yes (turn)|
| `utterance_blocked`      | L5 policy blocked the turn after the permission gate passed                   | yes (turn)|
| `utterance_invalid`      | `validate_utterance_data_url` rejected the payload                            | **no**    |
| `mic_permission_denied`  | mic permission set to Deny                                                    | **no**    |
| `mic_permission_ask`     | mic permission still on Ask                                                   | **no**    |

Same restraint as vision: the three early-exit kinds carry no
provider/model/tier/latency/tokens — only persona id and timestamp.

Mirrors the `MediaKind::from_wire` decision locked 2026-05-07 for
vision: a future `SpeechKind::from_wire` Err (if we add a kind
taxonomy) would be an IPC contract violation, not a user-attempted
utterance, and would not emit telemetry. Same rationale.

TrustDrawer `kindClass` colors:

- `utterance_transcribed` as `text-aether-ok`,
- `utterance_blocked`, `utterance_invalid`, `mic_permission_denied`
  as `text-aether-err`,
- `mic_permission_ask` as `text-aether-warn`.

---

## 7. UI surfaces

All read from a future source-of-truth registry
(`apps/desktop/src/lib/speechProviders.ts::SPEECH_PROVIDER_REGISTRY`).

| Surface                             | What it shows                                                       |
| ----------------------------------- | ------------------------------------------------------------------- |
| `VoiceBadge`                        | dot + provider + model + status                                     |
| `ActiveVoiceRoute` (on Voice panel) | "→ provider · model" hint above the Record button                   |
| `Transcript` user turn footer       | provider · model · latency · tokens · `origin: voice` chip          |
| `TrustDrawer` History tab           | per-turn annotation; long model ids middle-truncate via shared helper |
| `TrustDrawer` Audit tab             | capability + scope; provider/model intentionally absent             |

Long model id rendering reuses `truncateMiddleForDisplay(s, 28, 8)`
from `displayString.ts` — the helper is already generalized.

---

## 8. Hard constraints (operative for every Voice-v1 PR)

1. **Local-only providers.** No remote speech adapter exists; adding
   one is its own track and triggers the privacy-posture work
   (see §9).
2. **Audio bytes stay transient.** No persistence to durable memory,
   no inclusion in audit, no leak into telemetry. The **transcript
   text** is persistable because it becomes a user turn; the audio
   source is not.
3. **No continuous listening.** Single utterance per user action.
   Push-to-talk or explicit Start/Stop. No wake word, no VAD-driven
   auto-capture.
4. **No TTS in v1.** This doc covers input only.
5. **Additive config evolution.** `voice_provider.json` fields must
   be default-safe on read AND tolerate being absent from a
   freshly-rewritten file.
6. **No provider info in L5 audit.** `AuditRecordEvent` does not
   carry provider/model — capability + scope is the audit contract.
7. **Provider config errors are not unified across adapters.**
8. **No raw-payload telemetry.** Only structured metadata.
9. **No silent STT fallback.** If the provider fails, surface an
   error. Never swallow a user utterance.

---

## 9. Open questions (to answer when the track activates)

### Remote speech adapter

If/when a remote adapter is scoped, the same seven questions from
vision §9 apply, plus:

- Does the existing `mic_permissions.json` cover network egress, or
  do remote adapters require their own opt-in?
- Host allowlist storage + edit UX (shared with remote vision?).
- "Calls out to the internet" badge on voice surfaces.
- Audio-on-the-wire retention guarantees from the vendor.

### Text-to-speech (outgoing)

Out of scope for Voice v1. When scoped, it becomes **Voice
Output v1** with its own doc. It will have its own permission,
capability, and audit semantics because the user experience is
fundamentally different (hearing Companion vs. speaking to Companion).
Do not coalesce input and output capabilities.

### Wake word / continuous listening

Out of scope. Would require continuous audio capture — a privacy
posture escalation that needs its own design round.

### Multimodal turns (audio + video in one cue)

Out of scope. v1 voice is a user turn equivalent to a text turn.
Combining it with a camera/screen frame in a single `analyze_*`
call is a design question for after both tracks are stable.

### Rust↔TS provider-id codegen

Same defer condition as vision: until a third adapter or until TS
registry consumers exceed ~7–8.

---

## 10. Implementation sequencing (recommended)

When Voice v1 moves from design to build, land in this order.
Each step is a session worth of work; none wider than the existing
Vision v1 slices.

1. **Permission surface.** `mic_permissions.json`, tri-state gate,
   Settings UI, audit on state change. No capture yet.
2. **SpeechProvider trait + WhisperCppSpeechProvider scaffold.**
   Feature-gated. No commands yet.
3. **VoiceRegistry + voice_provider.json contract.**
   Mirror `VisionRegistry` test-for-test. Additive-default-safe
   contract locked.
4. **`transcribe_utterance` command + `validate_utterance_data_url`
   + `maybe_apply_voice`.** Early-exit telemetry, no UI yet.
5. **UI: VoicePanel with push-to-talk, VoiceBadge, ActiveVoiceRoute.**
   Transcript + TrustDrawer threading.
6. **Rot guard.** Add `tools/lint-voice-doc/` mirroring
   `tools/lint-vision-doc/`, seed the anchor manifest from this
   doc's committed content, and flip this doc's status from
   "design-only" to "current".

---

## 11. How this doc stays honest

This is a **design** doc — nothing in it is enforced by the code
until Voice v1 actually ships. Until then, treat it as a coherent
proposal, not a contract. When step 6 of the sequencing above lands,
add a rot-guard manifest under `tools/lint-voice-doc/` following
the vision pattern, and wire the guard into the session check set.

When this doc diverges from code after Voice v1 ships, the rot
guard is what catches silent drift — same contract as Vision v1.

---

## 12. Reference

- `docs/VISION-V1-ARCHITECTURE.md` — the pattern this doc mirrors.
- `tools/lint-vision-doc/check.py` — the rot-guard shape to copy.
- `P1_MEDIAKIND_FROM_WIRE_TELEMETRY_DECISION_EXECUTION_REPORT_2026-05-07.md`
  — the "IPC contract violation vs user-attempted action" distinction
  that applies to Voice v1 the same way.
- `P1_VISION_DOC_ROT_GUARD_EXECUTION_REPORT_2026-05-08.md` — the
  rot-guard rollout.
