# Presence v1 — architecture reference (design only)

> **Status:** Design-only as of 2026-05-11.
> **Scope:** Local, single-user desktop presence — signals about the
> user's attention state and the assistant's responsiveness posture,
> captured only while the app is foregrounded and the user is
> actively using the companion.
> **Out of scope for v1:** always-on monitoring, remote telemetry,
> camera-based gaze / face tracking, audio-level monitoring outside
> push-to-talk, cross-device presence, biometric signals of any
> kind, persistent presence history beyond the current session.

This doc mirrors `docs/VISION-V1-ARCHITECTURE.md` and
`docs/VOICE-V1-ARCHITECTURE.md` section by section so all three
modalities share a shape. When Presence v1 ships, this doc moves
from "design-only" to "current" and a rot-guard manifest is added
under `tools/lint-presence-doc/`.

---

## 0. What "presence" means in Aether

Presence is the assistant's model of **is the user here right now,
and how much should the assistant presume to do on its own**. It is
deliberately a *local* and *coarse* signal — not continuous
surveillance, not affective inference, not a replacement for the
user's explicit commands.

Three orthogonal axes:

| Axis | Values | Source |
| ---- | ------ | ------ |
| **User attention** | `Active` / `Idle` / `Away` | OS idle timer + window focus |
| **Assistant posture** | `Listening` / `Working` / `Idle` / `Speaking` | L1 turn-state machine |
| **Session lifecycle** | `Foreground` / `Background` / `Closed` | Tauri window events |

The three axes combine into a small, stable snapshot shape that the
UI, audit, and transcript surfaces can read. No ML, no heuristics —
just direct, explainable signals the user can audit.

### Design parity with Vision/Voice

| Aspect | Vision | Voice | Presence |
| ------ | ------ | ----- | -------- |
| Consent model | per-device tri-state (Allow/Ask/Deny) | single tri-state | **always-on, local-only, opt-OUT via Settings toggle** |
| Persistence | transcript + audit (metadata only) | transcript + audit (metadata only) | **transient snapshot + bounded session-lifetime history, no audit writes** |
| Payload | image bytes, transient | audio bytes, transient | **no payload — only coarse state labels** |
| Capability gate | `MediaCamera` / `MediaScreenCapture` | `Microphone` | **none — presence is observation, not action** |
| L5 audit entries | per capture | per utterance | **none — presence is not a policy-gated action** |
| Telemetry kinds | 5 | 5 (planned) | **3 (state_changed, session_opened, session_closed)** |

Presence is the only modality that does **not** go through L5's
capability gate. It's observation of the shell's own window state
and the OS idle timer — nothing sensitive leaves the shell, nothing
is persisted to disk. This is the critical distinction: presence is
a **UX affordance**, not a policy-gated action.

---

## 1. End-to-end flow

```
[OS]                                    [Tauri window]
 │ idle timer (system-provided)           │ focus change event
 │ — seconds since last input              │ — focused / blurred
 │ (no raw input events captured)          │
 │                                         │
 ▼                                         ▼
[PresenceController — packages/l3-presence/src/controller.rs]
 │ polls OS idle + subscribes to window events
 │ applies thresholds (idle_after_s, away_after_s)
 │ emits PresenceEvent on state change ONLY (not on every poll)
 │
 ▼
[PresenceEngine — packages/l3-presence/src/engine.rs]
 │ composes user attention + assistant posture into PresenceSnapshot
 │ buffers last N transitions in-memory (bounded ring, default 32)
 │ notifies subscribers via event-bus (L5 gateway + shell)
 │
 ▼
[Shell (apps/desktop/src-tauri)]
 │ records telemetry entry (kind = "presence_state_changed")
 │ exposes presence_current / presence_recent Tauri commands
 │ does NOT write an L5 AuditRecordEvent — presence is observation
 │
 ▼
[UI — apps/desktop/src/components/]
 │ PresenceIndicator (header dot)
 │ Trust drawer History tab: presence rows alongside turn history
 │ optional Settings toggle: "Track presence in History"
```

No payload anywhere. The snapshot carries timestamps, coarse state
enums, and nothing else.

---

## 2. State shapes

### `PresenceSnapshot`

```
pub struct PresenceSnapshot {
    pub user_attention: UserAttention,   // Active | Idle | Away
    pub assistant_posture: Posture,      // Listening | Working | Idle | Speaking
    pub session_lifecycle: Session,      // Foreground | Background | Closed
    pub as_of_ms: u64,                   // AppState::next_ts stamp
    pub since_ms: u64,                   // when this combined state began
}
```

`PresenceSnapshot` is Copy + Serialize, cheap to clone across IPC,
and contains no free-form strings, file paths, or payloads.

### `PresenceEvent`

Emitted on **state change only**. The controller polls at a low rate
(default 2 Hz) but only produces an event when one of the three axes
crosses a threshold.

```
pub enum PresenceEvent {
    AttentionChanged { from: UserAttention, to: UserAttention, as_of_ms: u64 },
    PostureChanged { from: Posture, to: Posture, as_of_ms: u64 },
    SessionChanged { from: Session, to: Session, as_of_ms: u64 },
}
```

### Thresholds

Defaults, all configurable via `presence.json` (§3):

- `idle_after_s = 120` — seconds of OS idle before `Active → Idle`.
- `away_after_s = 600` — seconds of OS idle before `Idle → Away`.
- `poll_hz = 2.0` — controller poll rate.
- `transition_log_cap = 32` — bounded in-memory ring buffer.

---

## 3. `presence.json` contract

Path: `<app_data>/presence.json`, alongside the existing permission
files.

Shape:

```json
{
  "enabled": true,
  "idle_after_s": 120,
  "away_after_s": 600,
  "history_in_trust_drawer": true
}
```

Contract (identical to every other config in the project):

- **Additive** — new fields may be added by future builds.
- **Default-safe on read** — every field has a `#[serde(default)]`
  producing the value above.
- **Unknown fields silently ignored on read** — no
  `#[serde(deny_unknown_fields)]`.
- **Unknown fields dropped on rewrite** — documented limitation.
- **Malformed JSON → default + WARN naming the path.**
- **Single-writer through `PresenceRegistry` (or equivalent).**
- **Atomic writes** — write-to-temp + rename.

### `enabled = false`

When the user disables presence, the controller stops polling and
stops emitting events; `presence_current` returns a `Disabled`
sentinel. The UI collapses the presence indicator to a small
"paused" glyph. No state is persisted or emitted until the user
flips it back.

---

## 4. Permission and consent posture

Presence does **not** live behind a tri-state capability gate
because there's nothing policy-gated to do — the shell is reading
its own window events and the OS idle timer, both of which the
application is already inherently entitled to see while it runs.

What the user controls:

1. **Settings toggle** — "Track presence in History". Default ON.
   When OFF: controller still runs (the assistant still knows when
   the user is away so it can defer notifications), but transitions
   are not written to the History tab. Telemetry still fires so the
   in-session UI indicator works, but the Trust drawer History
   stays empty of presence rows.
2. **Master off switch** — "Presence: Disabled" toggle.
   Controller stops polling; `presence_current` returns `Disabled`.
3. **OS-level sandbox** — the user can of course deny the app
   access to the OS idle timer through standard OS controls.

Rationale: presence v1 is a local, transient, explainable signal.
Treating it as a tri-state capability would imply it's doing
something sensitive; treating it as a free-for-all would miss that
users sometimes want their History tab to be pure chat. One toggle
for each concern is the right resolution.

---

## 5. Telemetry kinds (presence-related)

Presence emits exactly **three** kinds. All live under the same
`TelemetryEntry` type used by vision and voice; the TS allow-list
(future: `apps/desktop/src/lib/presenceTurns.ts`) mirrors the list
and is unit-tested for parity.

| kind                      | when                                                                 | in audit? |
| ------------------------- | -------------------------------------------------------------------- | --------- |
| `presence_state_changed`  | `PresenceEvent` on any of the three axes crosses a threshold         | **no**    |
| `session_opened`          | Tauri window shown for the first time this session                   | **no**    |
| `session_closed`          | Tauri window closed, app backgrounded-for-shutdown, or app exiting   | **no**    |

Rationale for **no audit rows**: presence is not a policy-gated
action. `AuditRecordEvent` is for "the assistant decided to do X
with capability Y on behalf of the user" — presence is "the user is
idle". Those are different ledgers. Conflating them would pollute
the audit surface with signals users don't expect to see there.

The telemetry entries carry no user content, no audio, no image
bytes — just state labels and timestamps.

### TrustDrawer rendering

- `presence_state_changed` → neutral tier (`text-aether-muted`).
- `session_opened` / `session_closed` → same neutral tier with a
  dedicated left-glyph so sessions read as "chapters" in the
  History scroll.

---

## 6. UI surfaces

All read from a future source-of-truth
(`apps/desktop/src/lib/presence.ts::presenceLabelFor`).

| Surface                             | What it shows                                                       |
| ----------------------------------- | ------------------------------------------------------------------- |
| `PresenceIndicator` (header)        | compact dot + tooltip: "You: Active · Aether: Listening"           |
| `Transcript` timeline dividers      | dim horizontal rule when a significant presence transition occurs  |
| `TrustDrawer` History tab           | presence rows interleaved with turn history (muted tier)           |
| `Settings` (new row)                | "Track presence in History" toggle + "Presence: Disabled" toggle   |

The PresenceIndicator is deliberately small — a 10px dot plus a
tooltip. It is not a status bar, not a clock, not a progress meter;
it just communicates "the system is watching itself, and here's the
current coarse state".

---

## 7. Interaction with Vision v1 and Voice v1

- **Vision v1 / Voice v1 capture events do not change presence.**
  Presence is observation of the window + idle; it does not listen
  to the L1 turn-state machine's per-capture decisions. Exception:
  `Posture` DOES reflect whether L1 is currently mid-turn, because
  that's the whole point of the "Aether is working" affordance.
- **Audio capture does not influence attention.** Pressing
  push-to-talk doesn't flip the user from `Active → Away`; mic
  activity is a direct user action, not a presence signal. The
  attention axis reads the OS idle timer only.
- **Vision frames do not influence attention.** v1 explicitly
  forbids camera-based gaze / face tracking as a presence signal.
  Pressing the camera's Analyze button is a direct user action.
- **A presence transition never pre-empts a turn.** If the user
  becomes `Away` mid-turn, the turn completes and the assistant
  posture flips back to `Idle` normally; the transcript does not
  gain a "user stepped away" annotation mid-message.

---

## 8. Hard constraints (operative for every Presence-v1 PR)

1. **Local-only.** No remote presence signals, no cloud.
2. **No camera-based signals.** No gaze tracking, no face detection,
   no lip-sync — even though L3 already holds the avatar / viseme
   code for rendering. Rendering the assistant's mouth is different
   from observing the user's face; v1 does the former only.
3. **No audio-level monitoring.** Even if push-to-talk is in use,
   presence does not read the mic stream.
4. **No biometrics of any kind.** Heart rate, keystroke cadence,
   mouse-movement-shape — all out.
5. **No persistence of raw signal.** Only the coarse enum
   transitions are recorded, in-memory, bounded ring.
6. **No L5 `AuditRecordEvent`s.** Presence is observation, not
   policy-gated action.
7. **No capability gate.** The Settings toggles are the consent
   surface.
8. **Additive config evolution.** `presence.json` changes must be
   default-safe on read AND tolerate being absent from a rewrite.
9. **Bounded in-memory history.** The transition ring has a hard
   cap; presence history is not a durable record.
10. **No cross-session leakage.** When the app closes, the ring
    clears.

---

## 9. Open questions for future tracks

### Presence-driven behavior

- Should the assistant defer non-critical notifications when the
  user is `Away`? Likely yes — but that's **Presence v2**, not v1.
- Should the assistant lower model tier when the user is `Idle`
  for cost reasons? Possibly — requires L4 router awareness, out
  of scope.

### Presence + voice integration

- Should mic capture be inhibited when `Away`? The design doc's
  "no silent fallback" rule says no: the user pressed PTT, honor
  their action. Revisit if telemetry shows this matters.

### Cross-app presence (remote)

- Out of scope for v1. A future track may let the user surface
  their Aether presence to an MCP peer; that would be a new
  capability with its own consent surface, not a widening of this
  doc.

### L3 avatar rendering

- L3 already contains viseme / behavior rendering code. Presence
  v1 does **not** wire the user-attention axis into the avatar —
  that's an avatar-polish track that also reads from the same
  snapshot.

---

## 10. Implementation sequencing (recommended)

When Presence v1 moves from design to build, land in this order.
Each step is one session of work.

1. **`presence.json` config surface + Settings toggles.** No
   controller wiring yet.
2. **`PresenceController` OS idle + window focus integration.**
   The crate already has `PresenceController` as a trait with an
   in-memory stub; wire the real signal sources.
3. **`PresenceEngine` snapshot composition + bounded ring.**
4. **Shell `presence_current` / `presence_recent` Tauri
   commands + telemetry kinds.**
5. **UI surfaces: `PresenceIndicator` in the header, Trust drawer
   History rendering, transcript timeline dividers.**
6. **Rot guard.** Add `tools/lint-presence-doc/` mirroring the
   vision lint pattern, seed the anchor manifest from this doc,
   flip status from "design-only" to "current".

---

## 11. How this doc stays honest

This is a **design** doc — nothing in it is enforced by code until
Presence v1 actually ships. When step 6 lands the rot guard, it
becomes authoritative and must be updated in the same PR as any
divergent behavior change.

---

## 12. Reference

- `docs/VISION-V1-ARCHITECTURE.md` — pattern this doc mirrors.
- `docs/VOICE-V1-ARCHITECTURE.md` — sibling architecture.
- `packages/l3-presence/src/` — existing L3 stubs: `controller.rs`,
  `engine.rs`, `bridge.rs`. The trait shapes there survive largely
  intact; this doc commits to which behaviors are implemented
  when.
- `tools/lint-vision-doc/check.py` — rot-guard shape to copy for
  Presence V1 step 6.
