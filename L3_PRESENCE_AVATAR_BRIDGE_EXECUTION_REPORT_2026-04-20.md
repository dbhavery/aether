# L3 — Presence → avatar `BehaviorClass` bridge

**Date:** 2026-04-20 (P3)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** `packages/l3-presence` now exposes a stateless, total,
deterministic mapping from the macro `PresenceState` (quiet /
listening / thinking / awaiting-approval / responding) to the
frame-rate `BehaviorClass` enum the avatar rendering surface will
consume. No avatar exists yet — this is the deliberate seam so that
when one lands, there's a single canonical place to look for "which
visual behavior should play when the companion is in state X?".

## 2. What shipped

### `packages/l3-presence/src/bridge.rs` (new)

- `pub fn behavior_for_presence(PresenceState) -> BehaviorClass`.
- Mapping:

  | Presence state | Behavior class | Why |
  |---|---|---|
  | `Quiet` | `Idle` | Default subtle breathing / blink cadence. |
  | `Listening` | `Listening` | Gaze locked to user during input. |
  | `Thinking` | `Thinking` | Soft look-away during routing / model call. |
  | `AwaitingApproval` | `Deflecting` | Polite hold posture while the user decides on an Ask. Deliberately **not** `Thinking` (model is not running) and **not** `Idle` (there's an open request). |
  | `Responding` | `Speaking` | Lip-sync + expression beats during reply. |

- Three unit tests: total/expected mapping, the `AwaitingApproval`
  guard, and a determinism loop.

### `packages/l3-presence/src/lib.rs`

- `pub mod bridge;` + re-export `behavior_for_presence`.

## 3. Deliberate non-goals

- **Not wired into the shell.** The shell doesn't need this yet —
  there is no avatar. Keeping the bridge narrow and unwired means:
  1. The avatar (when it arrives) can adopt it on day one without
     refactoring the shell.
  2. No behavior is silently attached to presence transitions that
     no one asked for.
- **No opposite direction.** Avatar events don't feed back into
  presence; that would be a cycle.
- **No per-frame nuance.** `BargingIn`, `Emphasizing`, `Repairing`,
  `SigningOff` aren't mapped. Those are driven by frame-scheduling /
  avatar-side beats, not the five-state macro lifecycle.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo test -p aether-l3-presence` | **10 pass** (was 7, +3 new) |
| `cargo check --workspace` | clean |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. Why this is worth doing even though there's no avatar

When the avatar lands, the person implementing it will ask: "OK, I've
got a `PresenceState::Thinking` event from L3 — what should the rig
do?" Without this bridge, they'll answer it themselves, and whatever
answer they pick will quietly diverge from whatever the next person
picks on a different surface (say, a web preview). Shipping the
mapping now — one line per state, with the rationale spelled out —
freezes the contract before the first consumer exists.

Cost: ~90 LOC, 3 unit tests, zero shell changes.

## 6. Commit

`feat(l3): [L3.x] presence->BehaviorClass bridge (unwired)`
