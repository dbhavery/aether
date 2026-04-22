# Presence V1 Step 0 — architecture doc (design only) — execution report (2026-05-11)

**Status:** Shipped locally on `dev`. Push not authorized.
**Scope:** Documentation only. No code.

## Goal

Kick off the Presence track with a design-only architecture doc,
mirroring the shape Vision V1 and Voice V1 already use. This is
step 0 of the Presence roadmap — implementation follows in later
sessions after Don reviews the design.

## Surfaces touched

- `docs/PRESENCE-V1-ARCHITECTURE.md` (new, ~280 lines).

## Design decisions captured in the doc

### Scope (non-negotiable v1 boundaries)

- **Local-only, coarse signals.** OS idle timer + window focus +
  L1 turn-state. Nothing else.
- **No camera / face / gaze tracking** — even though L3 already
  contains viseme and avatar rendering code, v1 explicitly forbids
  reading the camera for presence signals. Rendering the assistant's
  mouth is a different concern from observing the user's face.
- **No audio-level monitoring.** Even during push-to-talk.
- **No biometrics.** Heart rate, keystroke cadence, etc. out.
- **No persistence of raw signals.** Only coarse state transitions
  in a bounded in-memory ring; cleared on app close.

### Three orthogonal axes

1. **User attention:** `Active` / `Idle` / `Away` (OS idle timer).
2. **Assistant posture:** `Listening` / `Working` / `Idle` /
   `Speaking` (L1 turn-state).
3. **Session lifecycle:** `Foreground` / `Background` / `Closed`
   (Tauri window events).

Deliberately orthogonal so each axis stays explainable.

### Consent posture — divergence from vision/voice

Presence does NOT live behind a tri-state capability gate. The
shell is reading its own window events and the OS idle timer —
nothing sensitive leaves the shell, nothing is persisted to disk.
Treating it as a capability would imply it's doing something
sensitive; treating it as free-for-all would miss that users
sometimes want a pure chat History.

Resolution: **two Settings toggles**:

- "Track presence in History" (default ON) — controls whether
  transitions write to the Trust drawer History.
- "Presence: Disabled" (default OFF) — master off switch.

### No L5 audit rows for presence

`AuditRecordEvent` is for "the assistant decided to do X with
capability Y on behalf of the user". Presence is "the user is
idle". Those are different ledgers; conflating them would pollute
the audit surface.

Presence emits three telemetry kinds (`presence_state_changed`,
`session_opened`, `session_closed`) — all metadata only, none in
the audit log.

### `presence.json` contract

Same additive/default-safe shape as every other config. Fields:
`enabled`, `idle_after_s` (default 120), `away_after_s` (default
600), `history_in_trust_drawer` (default true).

### Interaction with Vision / Voice

- Vision / voice capture does not change presence axes (except
  assistant posture, via L1).
- PTT doesn't flip the user from Active → Away.
- Presence transitions never pre-empt a turn.

## Six-step implementation sequencing captured in §10

1. `presence.json` config + Settings toggles.
2. `PresenceController` OS idle + window focus integration.
3. `PresenceEngine` snapshot composition + bounded ring.
4. Shell `presence_current` / `presence_recent` Tauri commands +
   telemetry kinds.
5. UI surfaces (header indicator, Trust drawer history rows,
   transcript dividers).
6. Rot guard (`tools/lint-presence-doc/`), flip doc status to
   "current".

## Hard-constraint compliance

- No code change.
- No new commands.
- No new capabilities.
- No L5 `AuditRecordEvent` changes.
- No mic / voice / vision runtime work.
- No new dependencies.

## Tests

Docs-only. Focused checks:

- `cargo fmt --all -- --check` — clean
- `python tools/lint-layer-boundaries/check.py` — 0 violations
- `python tools/lint-vision-doc/check.py` — OK

## Divergences from the voice / vision pattern

Deliberate:

- **No capability gate.** Explained above.
- **No per-event audit row.** Explained above.
- **Only 3 telemetry kinds vs vision/voice's 5.** Presence has a
  smaller error surface because there's nothing to fail — no
  provider, no capture, no IPC boundary that can reject.

Everything else (additive-default-safe config, Trust drawer
history lane, Settings toggle, bounded in-memory snapshot) is
faithful to the sibling patterns.

## What is deliberately NOT in this slice

- No `presence.json` file — step 1.
- No controller implementation — step 2.
- No engine composition — step 3.
- No Tauri commands — step 4.
- No UI surfaces — step 5.
- No rot guard — step 6.

## Open questions parked for later

- Should the assistant defer notifications when Away? (Future
  Presence v2.)
- Should cost-tier drop when Idle? (Requires L4 router
  coordination; out of scope.)
- MCP-peer presence surfacing. (New capability, separate doc.)
