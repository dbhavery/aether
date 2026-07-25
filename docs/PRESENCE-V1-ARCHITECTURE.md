# Presence v1 — architecture reference

> **Status:** Current as of 2026-04-29.
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
modalities share a shape. It describes the present implementation
of Presence V1. Future / V2 material is explicitly labelled in
each section.

The rot-guard manifest at `tools/lint-presence-doc/check.py` holds
this doc honest against the code — renames or deletes of the
symbols and strings this doc claims exist will fail the linter.

---

## 0. What "presence" means in Companion

Presence is the assistant's model of **is the user here right now,
and how much should the assistant presume to do on its own**. It is
deliberately a *local* and *coarse* signal — not continuous
surveillance, not affective inference, not a replacement for the
user's explicit commands.

Presence V1 separates the concern onto **two orthogonal axes**.
(The glossary records this as "assistant posture" and "user
attention" being distinct L3 siblings, not a single monolithic
"presence state".)

| Axis | Values | Source | Status |
| ---- | ------ | ------ | ------ |
| **Assistant posture** | `Quiet` / `Listening` / `Thinking` / `Speaking` / `Paused` | L1 turn-state machine | Implemented |
| **User attention** | `Active` / `Idle` / `Away` | OS idle timer | Implemented |
| **Session lifecycle** | `Foreground` / `Background` / `Closed` | Tauri window events | **Future / V2** — see §9 |

The two implemented axes drive the UI, transcript, and audit
surfaces. No ML, no heuristics — just direct, explainable signals
the user can audit. Session lifecycle remains a design target for
a future track; the slot is held in §2 so composition shape can
evolve additively without breaking existing consumers.

### Design parity with Vision/Voice

| Aspect | Vision | Voice | Presence |
| ------ | ------ | ----- | -------- |
| Consent model | per-device tri-state (Allow/Ask/Deny) | single tri-state | **always-on, local-only, opt-OUT via Settings toggle** |
| Persistence | transcript + audit (metadata only) | transcript + audit (metadata only) | **transient snapshot + bounded session-lifetime history, no audit writes** |
| Payload | image bytes, transient | audio bytes, transient | **no payload — only coarse state labels** |
| Capability gate | `MediaCamera` / `MediaScreenCapture` | `MediaMic` | **none — presence is observation, not action** |
| L5 audit entries | per capture | per utterance | **none — presence is not a policy-gated action** |
| Telemetry kinds | 5 | 5 | **1 (`presence_state_changed`)** — session kinds deferred |

Presence is the only modality that does **not** go through L5's
capability gate. It's observation of the shell's own window state
and the OS idle timer — nothing sensitive leaves the shell, nothing
is persisted to disk. This is the critical distinction: presence is
a **UX affordance**, not a policy-gated action.

---

## 1. End-to-end flow

```
[OS]                                    [Tauri window]
 │ idle timer (system-provided)           │ (V2 — session lifecycle)
 │ — seconds since last input              │
 │ (no raw input events captured)          │
 │                                         │
 ▼                                         ▼
[idle_probe.rs — WindowsIdleProbe]       [future: session events]
 │ trait IdleProbe + Windows raw-FFI impl
 │ (macOS / Linux stub returns None)
 │
 ▼
[UserAttentionController — packages/l3-presence/src/attention.rs]
 │ pure state machine on (now_ms, idle_seconds)
 │ applies AttentionThresholds (idle_after_s, away_after_s)
 │ returns AttentionEvent on state change ONLY (not on every tick)
 │
 │     (sibling axis — assistant posture)
 │  [PresenceController — packages/l3-presence/src/controller.rs]
 │   tracks Quiet / Listening / Thinking / Speaking / Paused
 │   exposed via Tauri command presence_current
 │
 ▼
[Shell poll loop — apps/desktop/src-tauri/src/main.rs::run_presence_loop]
 │ 1 Hz tokio::interval tick
 │ on transition:
 │   - AppState::push_presence_history (bounded ring)
 │   - app.emit("presence:attention", AttentionEventPayload)
 │ does NOT write an L5 AuditRecordEvent — presence is observation
 │
 ▼
[Tauri commands — apps/desktop/src-tauri/src/commands.rs]
 │ presence_current            — assistant posture snapshot
 │ presence_status             — user-attention snapshot (§2 axis)
 │ presence_recent_history     — bounded ring of recent transitions
 │
 ▼
[UI — apps/desktop/src/components/]
 │ SettingsDrawer: enabled + thresholds + history_in_trust_drawer toggles
 │ TrustDrawer History tab: presence rows interleaved with turn history
 │                           (gated by history_in_trust_drawer)
```

No payload anywhere. The telemetry carries timestamps and coarse
state enums only.

---

## 2. State shapes

Two controllers, two snapshot types. The glossary treats them as
distinct so future composition (session lifecycle, avatar wiring)
can be added additively.

### Assistant posture — `PresenceController` / `PresenceSnapshot`

`packages/l3-presence/src/controller.rs`:

```rust
pub enum PresenceState {
    Quiet, Listening, Thinking, Speaking, Paused,
}

pub struct PresenceSnapshot {
    pub state: PresenceState,
    pub as_of_ms: u64,
    pub since_ms: u64,
}

pub trait PresenceController: Send + Sync { ... }
pub struct InMemoryPresenceController { ... }
pub const TRANSITION_LOG_CAP: usize = 32;
```

Exposed to the UI via the `presence_current` Tauri command.

### User attention — `UserAttentionController` / `AttentionSnapshot`

`packages/l3-presence/src/attention.rs`:

```rust
pub enum UserAttention { Active, Idle, Away }

pub struct AttentionThresholds {
    pub idle_after_s: u32,  // default 120
    pub away_after_s: u32,  // default 600; coerced to idle_after_s + 1 if invalid
}

pub struct AttentionSnapshot {
    pub state: UserAttention,
    pub as_of_ms: u64,
    pub since_ms: u64,
    pub enabled: bool,
}

pub struct AttentionEvent {
    pub from: UserAttention,
    pub to: UserAttention,
    pub as_of_ms: u64,
}

pub struct UserAttentionController { ... }
```

Exposed to the UI via the `presence_status` Tauri command (see §1
for why it is named `_status`, not `_current` — the two commands
cover different axes and coexist).

### Shell-side ring — `PresenceHistoryEntry`

`apps/desktop/src-tauri/src/state.rs`:

```rust
pub struct PresenceHistoryEntry {
    pub kind: String,         // "presence_state_changed" today
    pub from: String,         // UserAttention.label()
    pub to: String,
    pub as_of_ms: u64,
}

impl PresenceHistoryEntry {
    pub fn from_event(ev: AttentionEvent) -> Self { ... }
}
```

Held behind `AppState.presence_history: Mutex<VecDeque<_>>` with a
bounded `PRESENCE_HISTORY_CAPACITY` cap (see `state.rs`). Mirrors
the shape returned by the `presence_recent_history` command.

### Thresholds

Defaults, all configurable via `presence.json` (§3):

- `idle_after_s = 120` — seconds of OS idle before `Active → Idle`.
- `away_after_s = 600` — seconds of OS idle before `Idle → Away`.
- Poll rate: 1 Hz (set in `main.rs` as `PRESENCE_POLL_MS = 1_000`;
  a single `GetLastInputInfo` call per tick on Windows, a no-op
  elsewhere).

### Future / V2 — session lifecycle axis

`Foreground / Background / Closed` is reserved space in this doc.
Not implemented. A future slice can add a sibling controller that
wires Tauri window-focus events into a new
`SessionLifecycleController`, emitting `session_opened` /
`session_closed` telemetry kinds on transitions. Shape parity with
the other two axes is deliberate: the UI and Trust drawer will
read from a composed snapshot without reshaping.

---

## 3. `presence.json` contract

Path: `<app_data>/presence.json`, alongside the existing permission
files. Owned by `apps/desktop/src-tauri/src/presence_config.rs`
(struct `PresenceConfig`).

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
- **Single-writer** via `AppState::set_presence_config` + the
  `set_presence_config` Tauri command; both validate thresholds
  (`10 ≤ idle_after_s ≤ 86_400`, `away > idle`) and hot-swap the
  controller atomically.
- **Atomic writes** — write-to-temp + rename.
- **Boot wiring** — `AppState::attach_presence_config_file` seeds
  the attention controller on app startup.

### `enabled = false`

When the user disables presence, the controller stops producing
transitions; `presence_status` reports `enabled = false`. The
poll loop still ticks but is a cheap no-op. Flipping back to
enabled resets `since_ms` to the current tick so the user does
not get a spurious "you've been Away for 10 minutes" event.

---

## 4. Permission and consent posture

Presence does **not** live behind a tri-state capability gate
because there's nothing policy-gated to do — the shell is reading
its own window events and the OS idle timer, both of which the
application is already inherently entitled to see while it runs.

What the user controls:

1. **Settings `enabled` toggle** — master on/off. When off, the
   controller is silent; `presence_status` reports
   `enabled = false`.
2. **Settings `history_in_trust_drawer` toggle** — when off,
   transitions are still computed (so a future V2 sibling that
   suppresses notifications when `Away` can work) but they are
   not rendered in the Trust drawer History tab.
3. **Settings threshold editor** — the user can tune
   `idle_after_s` and `away_after_s` at runtime; the shell
   validates and hot-swaps the controller.
4. **OS-level sandbox** — the user can deny the app access to the
   OS idle timer through standard OS controls; the shell's
   `UnsupportedIdleProbe` returns `None` and the controller
   remains at `Active`.

Rationale: presence v1 is a local, transient, explainable signal.
Treating it as a tri-state capability would imply it's doing
something sensitive; treating it as a free-for-all would miss that
users sometimes want their History tab to be pure chat. One toggle
per concern is the right resolution.

---

## 5. Telemetry kinds (presence-related)

Presence emits **one** telemetry kind in V1. The TS allow-list
for this is intentionally unshipped — presence telemetry lives
on the existing `TelemetryEntry`/`PresenceHistoryEntry` wire
without a dedicated classifier helper. When the Memory tab or
richer filtering lands, a `presenceTurns.ts` mirror may join the
voice / memory ones.

| kind                      | when                                                                 | in audit? | status |
| ------------------------- | -------------------------------------------------------------------- | --------- | ------ |
| `presence_state_changed`  | `AttentionEvent` on the user-attention axis crosses a threshold      | **no**    | **Implemented** |
| `session_opened`          | Tauri window shown for the first time this session                   | **no**    | Future / V2 |
| `session_closed`          | Tauri window closed, app backgrounded-for-shutdown, or app exiting   | **no**    | Future / V2 |

Rationale for **no audit rows**: presence is not a policy-gated
action. `AuditRecordEvent` is for "the assistant decided to do X
with capability Y on behalf of the user" — presence is "the user is
idle". Those are different ledgers. Conflating them would pollute
the audit surface with signals users don't expect to see there.

The telemetry entries carry no user content, no audio, no image
bytes — just state labels and timestamps.

### Event bus channel

`presence:attention` — emitted from `run_presence_loop` on every
`AttentionEvent` the controller produces. The webview subscribes
to this channel to update the Trust drawer in real time.

### TrustDrawer rendering

- `presence_state_changed` rows render in a muted tier
  (`text-aether-muted` equivalent) when the
  `history_in_trust_drawer` toggle is ON. Coalescing suppresses
  A → B → A blips within 5 s so the History surface does not
  read as a debug log.

---

## 6. UI surfaces

V1 implements two UI surfaces against presence; the header
`PresenceIndicator` remains a future polish.

| Surface                         | What it shows                                                                  | Status |
| ------------------------------- | ------------------------------------------------------------------------------ | ------ |
| `SettingsDrawer`                | Enabled toggle + idle/away threshold editor + history toggle                   | Implemented |
| `TrustDrawer` History tab       | Presence rows interleaved with turn history, gated by `history_in_trust_drawer` | Implemented |
| Header `PresenceIndicator` dot  | Compact dot + tooltip summarising both axes                                    | Future / V2 |
| `Transcript` timeline dividers  | Dim rule when a significant presence transition occurs                         | Future / V2 |

---

## 7. Interaction with Vision v1 and Voice v1

- **Vision v1 / Voice v1 capture events do not change presence.**
  Presence is observation of the OS idle timer; it does not listen
  to the L1 turn-state machine's per-capture decisions. Exception:
  assistant posture DOES reflect whether L1 is currently mid-turn,
  because that's the whole point of the "Companion is working"
  affordance.
- **Audio capture does not influence attention.** Pressing
  push-to-talk doesn't flip the user from `Active → Away`; mic
  activity is a direct user action, not a presence signal. The
  attention axis reads the OS idle timer only.
- **Vision frames do not influence attention.** V1 explicitly
  forbids camera-based gaze / face tracking as a presence signal.
  Pressing the camera's Analyze button is a direct user action.
- **A presence transition never pre-empts a turn.** If the user
  becomes `Away` mid-turn, the turn completes and the assistant
  posture flips back to `Quiet` normally; the transcript does not
  gain a "user stepped away" annotation mid-message.

---

## 8. Hard constraints (operative for every Presence-v1 PR)

1. **Local-only.** No remote presence signals, no cloud.
2. **No camera-based signals.** No gaze tracking, no face detection,
   no lip-sync-as-presence. Rendering the assistant's mouth is
   different from observing the user's face; v1 does the former only.
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
11. **Transition-only emission.** The poll loop is silent except
    on state changes. Holding steady through a tick must never
    produce an `AttentionEvent`.
12. **L3 contains no `unsafe` code.** OS-specific probes live in
    the shell (`apps/desktop/src-tauri/src/idle_probe.rs`) so the
    `#![deny(unsafe_code)]` at the L3 crate level is unconditional.

These are **hard constraints** — spec-side invariants. Tests and
evals enforce them under specific inputs (that's acceptance
criteria, a separate surface). The rot guard at
`tools/lint-presence-doc/` prevents drift between this list and
the code that implements it; it does not replace the tests.

---

## 9. Open questions for future tracks

### Session lifecycle axis (V2)

The three-axis composition reserved in §2 still needs:

- A `SessionLifecycleController` sibling that consumes Tauri
  window-focus events.
- `session_opened` / `session_closed` telemetry kinds plumbed
  through the shell ring and the TS allow-list.
- A composed three-axis `PresenceSnapshot` that the UI can read
  without reshaping either of today's snapshots. Additive —
  existing consumers of `AttentionSnapshot` and the posture
  `PresenceSnapshot` continue to work.

### Real idle probes for macOS / Linux

Today's `IdleProbe` trait has a Windows implementation
(`GetLastInputInfo`). `UnsupportedIdleProbe` returns `None` on
macOS / Linux — truthful but unusable, and the UI shows "idle
probe unavailable" on those platforms. Replacements (`CGEventSource…`
for macOS, `XScreenSaverQueryInfo` for X11; Wayland is a separate
track) are V2.

### Presence-driven behavior

- Should the assistant defer non-critical notifications when the
  user is `Away`? Likely yes — Presence V2.
- Should the assistant lower model tier when the user is `Idle`
  for cost reasons? Possibly — requires L4 router awareness.

### Presence + voice integration

- Should mic capture be inhibited when `Away`? The design doc's
  "no silent fallback" rule says no: the user pressed PTT, honor
  their action. Revisit if telemetry shows this matters.

### Cross-app presence (remote)

- Out of scope for v1. A future track may let the user surface
  their Companion presence to an MCP peer; that would be a new
  capability with its own consent surface, not a widening of this
  doc.

### L3 avatar rendering

- L3 already contains viseme / behavior rendering code. Presence
  V1 does **not** wire the user-attention axis into the avatar —
  that's an avatar-polish track that also reads from the same
  snapshot.
- **Runtime renderer scaffold (T1.4).** A no-op renderer
  contract lives in `packages/l3-presence/src/runtime.rs`. The
  `Renderer` trait + `LogStubRenderer` no-op default + opaque
  `MotionClipLibraryHandle` / `AudioStreamHandle` /  `MotionClipId`
  marker types reserve the input contract the future avatar
  renderer will consume so renderer work can advance in parallel
  with the GPU asset pipeline. The stub emits
  structured `RendererEvent`s on every L3 state transition and
  retains a bounded `RENDERER_EVENT_LOG_CAP` ring; no playback,
  no I/O, no cross-layer imports. `RenderingPresenceController`
  wraps the existing `InMemoryPresenceController` and forwards
  transitions to the renderer; `with_log_stub()` is the default
  wiring until a real renderer ships.

---

## 10. Implementation sequencing (recap)

Presence V1 shipped in four handoff-scoped steps. Earlier
planning drafts of this doc split the work into six sub-steps;
the four below are the canonical handoff vocabulary (see
`HANDOFF_2026-05-14_CONTINUE_COMPANION_BUILD.md` and
`HANDOFF_2026-05-16_PRESENCE_MEMORY_EVAL.md`).

1. **Step 1** — `presence.json` config surface + Settings
   `enabled` / `history_in_trust_drawer` toggles. Shipped.
2. **Step 2** — `UserAttentionController` + `WindowsIdleProbe` +
   shell poll loop + `presence_status` + `presence_recent_history`
   Tauri commands + threshold-editing Settings UI. Shipped.
3. **Step 3** — Trust drawer History tab renders presence rows
   interleaved with turn telemetry, filtered by
   `history_in_trust_drawer`. Shipped.
4. **Step 4** — rot guard (`tools/lint-presence-doc/check.py`)
   and doc flip from "design-only" to "current" (this PR).

---

## 11. How this doc stays honest

This doc is **current**. The rot guard at
`tools/lint-presence-doc/check.py` verifies that every file path,
symbol name, and string constant this doc claims exists is
actually present in code.

When a Presence V1 PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `tools/lint-presence-doc/check.py`.
2. Update this doc in the same PR.
3. Bump this doc's `**Status:** Current as of YYYY-MM-DD` date.

The rot guard is a doc/code consistency check, not a behavioural
test — behavioural acceptance criteria live in the L3 unit tests
(`cargo test -p aether-l3-presence`) and the shell tests
(`cargo test ... --features sqlite-backend,ollama-provider,
vision-llamacpp,speech-whispercpp`). Per the glossary §6, rot
guards and AC are deliberately distinct surfaces.

---

## 12. Reference

- `docs/VISION-V1-ARCHITECTURE.md` — pattern this doc mirrors.
- `docs/VOICE-V1-ARCHITECTURE.md` — sibling architecture.
- `docs/GLOSSARY.md` §6 — rot guards vs acceptance criteria.
- `packages/l3-presence/src/` — L3 code:
  - `attention.rs` — user attention axis.
  - `controller.rs` — assistant posture axis.
  - `engine.rs`, `bridge.rs` — rendering surfaces (avatar polish
    track, out of scope for Presence V1 rot guarding beyond their
    existence).
  - `runtime.rs` — runtime renderer scaffold (T1.4):
    `Renderer` trait, `LogStubRenderer`, `MotionClipLibraryHandle`,
    `AudioStreamHandle`, `MotionClipId`, `RendererEvent`,
    `RenderingPresenceController`, `RENDERER_EVENT_LOG_CAP`.
- `apps/desktop/src-tauri/src/` — shell wiring:
  - `presence_config.rs` — `presence.json` contract.
  - `idle_probe.rs` — OS idle probe trait + Windows impl.
  - `main.rs::run_presence_loop` — 1 Hz poll + emit.
  - `commands.rs` — `presence_current`, `presence_status`,
    `presence_recent_history`.
  - `state.rs::PresenceHistoryEntry` — shell-side ring row.
- `tools/lint-vision-doc/check.py`, `tools/lint-voice-doc/check.py`
  — rot-guard shape this linter copies.
