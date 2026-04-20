# L3.1 Execution Report — Presence State Machine

**Date:** 2026-04-19
**Branch:** dev
**Status:** Complete, tests green, boundary lint clean, not pushed.

---

## 1. States and transition model

Five macro states, session-scoped, caller-driven transitions:

| State | Meaning |
|---|---|
| `Quiet` | At rest. Between turns. |
| `Listening` | Receiving / parsing user input. |
| `Thinking` | Evaluating policy, routing, generating. |
| `AwaitingApproval` | A `Decision::Ask` ticket is open; waiting on user resolution. |
| `Responding` | Emitting the assistant response. |

The controller does **not** police ordering: any state can follow any other. This is deliberate so future async paths (barge-in, streaming tokens, background tasks, unsolicited outputs) fit without reshaping the core API. The current CLI drives two canonical sequences:

- **Allow turn:** `Listening → Thinking → Responding → Quiet`.
- **Ask turn (approve):** `Listening → Thinking → AwaitingApproval → Responding → Quiet`.
- **Ask turn (reject):** `Listening → Thinking → AwaitingApproval → Quiet`.

## 2. Core API added — `packages/l3-presence/src/controller.rs`

```rust
pub enum PresenceState { Quiet, Listening, Thinking, AwaitingApproval, Responding }
impl PresenceState { pub fn label(self) -> &'static str }

pub struct PresenceSnapshot {
    pub session_id: String,
    pub state: PresenceState,
    pub updated_at_ms: u64,
    pub detail: Option<String>,
}

pub trait PresenceController: Send + Sync {
    fn set_state(&self, session_id: &str, state: PresenceState,
                 updated_at_ms: u64, detail: Option<String>)
        -> Result<PresenceSnapshot, L3Error>;
    fn current(&self, session_id: &str) -> Result<PresenceSnapshot, L3Error>;
    fn recent_transitions(&self, session_id: &str) -> Result<Vec<PresenceSnapshot>, L3Error>;
    fn clear_session(&self, session_id: &str) -> Result<(), L3Error>;
}

pub struct InMemoryPresenceController;    // Mutex<HashMap<session, SessionState>>
pub const TRANSITION_LOG_CAP: usize = 32; // bounded per-session transition log
pub fn render_presence(&PresenceSnapshot) -> String;
```

All new types re-exported from `aether_l3_presence` crate root. Deliberately orthogonal to the existing Wave-4 `engine` module (`BehaviorClass`, `BehaviorFrame`, `PresenceEngine`, `RenderingSurface`): that is frame-rate avatar animation; this is macro session status.

### Design choices

- **Caller-supplied timestamps** (`updated_at_ms: u64`) — the controller stays pure; no implicit clock dependency; tests are deterministic.
- **Unknown session reads as `Quiet`** — no error path for a trivial case; mirrors the L2.1 precedent.
- **Bounded transition log** — front-evicts at `TRANSITION_LOG_CAP`; enough to drive a debug view or a recent-history UI without turning into telemetry.
- **`detail` is free-form** — the CLI uses it to carry the ticket id into `AwaitingApproval`; future consumers can attach short error contexts or task ids.
- **No policy / routing / persona logic** — L3.1 only tracks status, exactly what the brief asked for.

## 3. Where presence is integrated

### `apps/l1-cli/src/main.rs`

- New `aether-l3-presence` dependency.
- A shared `Arc<dyn PresenceController>` constructed at startup; initial transition to `Quiet` announced on boot.
- New helper `announce_presence(&presence, state, ts, detail)` that calls `set_state` and prints one `[presence] <label>` line.
- Turn-loop phases fire transitions:
  - user input received → `Listening` (before request build),
  - request built → `Thinking` (before `handle_turn`),
  - `Decision::Ask` detected → `AwaitingApproval` with ticket id in `detail`,
  - approval resolved (allow or reject) → `Responding`,
  - after print / memory append → `Quiet`,
  - on engine or approval error → `Quiet` (so the next prompt has a clean state).

### `apps/l1-cli/src/presence.rs` (new, `#[cfg(test)]`)

Encapsulates the same transition sequence as test helpers so the CLI pattern is covered end-to-end without driving real stdin:

- `drive_allow_turn_presence(&controller, session, base_ts)` — records the Allow-path sequence, returns the observed `Vec<PresenceState>`.
- `drive_ask_turn_presence(&controller, session, base_ts, &ask_result, approved)` — records the Ask-path sequence (branching on approval), asserts ticket id flows through `detail`.

Kept test-only so the production binary doesn't carry unused helpers.

### Layer hygiene

- L1 unchanged.
- L5 unchanged.
- L7 unchanged.
- L3 grew a narrow macro-presence surface parallel to the existing frame-scheduler surface.
- Only `apps/l1-cli` — already the stitch crate — depends on L3. Boundary linter: **0 violations**.

## 4. Tests and checks

### 4.1 Tests added

**`packages/l3-presence/src/controller.rs` (7 unit tests):**

- `unknown_session_reads_as_quiet`
- `set_state_updates_current_and_logs`
- `transition_log_is_bounded` (asserts `TRANSITION_LOG_CAP`)
- `sessions_are_isolated`
- `clear_session_removes_only_one`
- `render_presence_plain_and_with_detail`
- `labels_are_stable`

**`apps/l1-cli/src/presence.rs` (3 integration-style tests):**

- `allow_turn_sequence_matches_expected_states` — asserts `[Listening, Thinking, Responding, Quiet]`.
- `ask_approved_sequence_includes_awaiting_then_responding` — asserts `[Listening, Thinking, AwaitingApproval, Responding, Quiet]` and confirms `detail == Some("tk-1")` on the `AwaitingApproval` snapshot.
- `ask_rejected_sequence_skips_responding` — asserts `[Listening, Thinking, AwaitingApproval, Quiet]`.

### 4.2 Check results

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (pre-existing warnings only) |
| `cargo test --workspace` | all green, 0 FAILED |
| `cargo test -p aether-l3-presence` | **7 unit + 2 smoke passed** |
| `cargo test -p aether-l1-cli` | **20 / 20 passed** (17 prior + 3 new) |
| `python tools/lint-layer-boundaries/check.py` | `OK (0 violations)` |

## 5. Limitations and future work

- **No timers.** The controller does not auto-transition to `Quiet` after idle; a future wave can add an `IdleTimer` that calls `set_state(..., Quiet, ...)` after N ms without input.
- **Coarse `Responding`.** One state for the whole output phase. A real speaking avatar will want `Typing` vs `Speaking`, plus barge-in / repair states.
- **No streaming hooks.** The current integration fires `Responding` once; a streaming router would benefit from per-chunk `Responding` pings (or a dedicated `StreamingResponse` variant with a progress field).
- **CLI is the only consumer.** The `engine.rs` frame-rate surface is still a Wave-4 stub; nothing yet bridges macro presence to avatar frames. That bridge (likely: `PresenceState::Thinking` → `BehaviorClass::Thinking`) belongs to the first real avatar wave.
- **No cross-layer event.** Presence transitions print locally but don't publish to `aether-event-bus`; a future desktop shell will want an event stream to subscribe to instead of polling `current`.
- **Detail is a free-form string.** Adequate for a ticket id, not for structured payloads. When the UX needs richer context (progress %, reason code, retry count) this becomes a typed variant.
- **Shares the single demo session id.** Inherits L2.1's one-session CLI constraint.
- **Error recovery is silent.** On `handle_turn` error we transition to `Quiet` so the REPL recovers — no distinct `Errored` state yet.

## 6. Recommended next session

**L4.1 — real provider adapter (llama.cpp / Ollama behind a flag).**

Rationale: the companion has memory (L2.1), approvals (L7.1), and presence (L3.1), but every response is still `[reflex] heard you: <prompt>`. Wiring a real local model behind a feature flag is the last missing piece before the demo stops feeling like a harness. The existing `ModelRouter` trait and the `MemoryAwareRouter` wrapper already feed a rendered transcript into the prompt — a real adapter plugs in at that exact seam without touching L1, L5, or the presence loop.

Scope suggestion for L4.1: one new `ModelRouter` impl (probably Ollama HTTP against `localhost:11434`) behind a `--provider=ollama` CLI flag, kept off by default so the existing zero-dependency demo path continues to work. Keep it behind a cargo feature if it pulls new deps.

Caveat: if running the CLI with the full memory + approval + presence stack reveals a coordination issue (e.g. presence flicker, memory note pollution, transcript overflow), triage that first — L4.1 is pure addition and will only amplify any underlying instability.

---

**Commits (local, unpushed):** none yet on top of the existing L2.1 + L7.1 work. Suggested split — one commit for the L3 `controller` module + tests, one commit for the demo-side wiring (`main.rs`, `presence.rs`, README).
