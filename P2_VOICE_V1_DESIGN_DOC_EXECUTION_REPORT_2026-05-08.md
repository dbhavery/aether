# P2 — Voice V1 architecture doc (design-only) — execution report (2026-05-08)

**Status:** Shipped locally on `dev`. Push not authorized.
**Scope:** Documentation only. No code changes.

## Goal

Define the next capability track at a design/architecture level so
future sessions can implement it with the same discipline used for
Vision v1. The 2026-05-08 handoff (Option B) and the Vision v1 arch
doc (§9) both explicitly name voice as the next mirror, with the
pattern already half-designed in the deferred-tracks section.

## Why voice (and not L3 presence or L2 memory maturation)

Three candidates from the session prompt; voice chosen because:

1. **Clearest pattern parity with Vision v1.** Permission tri-state,
   capability gate, transient payload, local-first provider
   abstraction, transcript + Trust drawer surfaces — all map 1:1.
2. **Vision-v1 doc already pre-designed the mirror.** §9 names the
   `mic_invalid` / `mic_permission_denied` / `mic_permission_ask`
   telemetry kinds. Completing the design is mostly expanding what
   is already implied.
3. **L3 presence is larger and depends on the Media engine.**
   Scoping it now would over-reach.
4. **L2 memory maturation is already mid-flight.** Durable wiring
   landed 2026-04-23 and retention policy 2026-04-24; the next
   step is refinement, not a new slice, so an architecture doc is
   premature.

Voice v1 is also the right **discipline-preserving** choice: it is
small enough that a single session can build a real implementation
sequence from this design.

## Surfaces touched

- `docs/VOICE-V1-ARCHITECTURE.md` — new, ~340 lines, mirrors
  `docs/VISION-V1-ARCHITECTURE.md` section by section so future
  readers can reason about both modalities against a shared shape.

## Design decisions captured in the doc

### Scope (non-negotiable v1 boundaries)

- **Single utterance only.** Push-to-talk or explicit Start/Stop.
  No wake word, no VAD-driven auto-capture, no continuous
  listening.
- **Local-only provider.** First adapter is a whisper.cpp candidate
  (`WhisperCppSpeechProvider`, feature `speech-whispercpp`). A
  remote adapter is its own track and triggers privacy-posture
  work.
- **Input only.** TTS is out of scope for v1; when it scopes, it
  becomes **Voice Output v1** with its own doc. Do not coalesce
  the two capabilities.
- **Audio bytes transient.** The **transcribed text** becomes a
  user turn and is persistable; the audio source is not.
- **No silent STT fallback.** If transcription fails, surface a
  clear error. Never swallow a user's utterance.

### Contracts lifted from Vision v1 verbatim

- Permission tri-state (Allow / Ask / Deny) with its own
  `mic_permissions.json` (additive, default-safe on read, unknown
  fields tolerated / dropped on rewrite).
- `voice_provider.json` with the same additive-default-safe contract
  as `vision_provider.json`.
- Model-list TTL cache design (60s default, bounded [5, 3600],
  `AETHER_VOICE_MODEL_TTL_SECS` env override, manual refresh).
- Provider trait mirrors `VisionProvider` (id, label, transcribe,
  set_model, current_model, healthcheck, list_models).
- Provider config errors intentionally NOT unified across adapters.
- L5 `AuditRecordEvent` carries capability + scope only, never
  provider/model.
- TrustDrawer + transcript surface provider · model consistently;
  long ids middle-truncate via the shared `truncateMiddleForDisplay`
  helper.

### Explicit divergences from Vision v1 (called out in the doc)

- **No text-only fallback on provider failure.** Losing a user's
  utterance silently would be worse UX than a visible error.
- **New user-turn origin chip (`origin: voice`).** The transcribed
  text enters the transcript as a *user* turn, so the provenance
  badge matters more than in vision (where the turn is system-
  authored).
- **No duration / VAD preflight in v1.** A zero-duration or
  silence-only WAV is accepted at the shell and rejected (or
  returns empty) by the provider.

### Telemetry kinds proposed

Five kinds — same cardinality and same early-exit-carries-no-fields
restraint as vision:

- `utterance_transcribed` (yes, in audit as a turn)
- `utterance_blocked` (yes, in audit as a turn)
- `utterance_invalid` (no audit row)
- `mic_permission_denied` (no audit row)
- `mic_permission_ask` (no audit row)

The 2026-05-07 `MediaKind::from_wire` decision is explicitly
inherited: a future `SpeechKind::from_wire` Err (if a kind taxonomy
exists) is an IPC contract violation, not a user-attempted
utterance, and does not emit telemetry.

### Implementation sequencing recommended

Six sessions:

1. Permission surface (`mic_permissions.json`, Settings UI, audit
   on state change).
2. `SpeechProvider` trait + WhisperCpp scaffold (feature-gated, no
   commands).
3. `VoiceRegistry` + `voice_provider.json` contract with
   additive-default-safe tests.
4. `transcribe_utterance` command + validators + early-exit
   telemetry (no UI).
5. UI (VoicePanel push-to-talk, VoiceBadge, ActiveVoiceRoute,
   transcript/TrustDrawer threading).
6. Rot guard (`tools/lint-voice-doc/` mirroring the vision lint),
   flip doc status from "design-only" to "current".

Each step is sized to match a Vision-v1 session slice — none wider
than what already shipped.

## Hard-constraint compliance

- No code change.
- No new commands.
- No new providers (no `WhisperCppSpeechProvider` implementation —
  only named as the candidate).
- No mic / voice / STT / TTS runtime behavior.
- No streaming or continuous capture.
- No changes to Vision v1's contract.
- No new test dependencies.
- No release / distribution / signing work.
- No `AuditRecordEvent` change.
- `vision_provider.json` contract untouched.
- `LlamaCppConfigError` / `OllamaConfigError` untouched.

## Tests

Docs-only. Focused checks:

- `cargo fmt --all -- --check` — clean
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK, 51 anchors
- `apps/desktop && pnpm typecheck` — clean

## What happens next

Nothing automated. The next session that picks up this doc should
either:

- start step 1 of the implementation sequencing (mic permission
  surface), or
- review the design for gaps before starting (with Don), or
- explicitly pivot to a different track (L3 presence / L2 memory
  maturation) after reading this doc.

## What was deliberately left out

- **Code scaffolds.** The session prompt forbids it. The doc names
  files and symbols the way Vision v1's doc does; the scaffolds
  land in step 1+ of the sequencing.
- **Sequence diagrams.** Same rationale as Vision v1 — ASCII flow
  is sufficient for the audience.
- **UI mockups.** Design comes with the frontend work.
- **Performance SLOs.** No data to set them against; Vision v1 has
  no perf SLO either.
- **whisper.cpp operational details** (model download, GGUF naming,
  FFI vs HTTP choice). Those are implementation-time questions the
  scaffold PR answers. The doc names the candidate and the env
  knobs without pinning the transport.
