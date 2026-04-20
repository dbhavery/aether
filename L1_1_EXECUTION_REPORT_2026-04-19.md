# Wave L1.1 — First Turn FSM Slice (Execution Report)

**Date:** 2026-04-19
**Branch:** `dev` (continuing from a93127d; this wave adds commits on top)
**Scope:** L1 only (`packages/l1-interaction/`)
**Goal:** A thin but real vertical slice — accept a request, drive a minimal
turn FSM, call `DefaultPolicyEngine`, dispatch through an L1-local router
trait, return a structured `TurnResult`.

---

## 1. Minimal turn FSM

A small, coherent subset of the 19-state canonical enum:

```
Idle
  │ handle_turn(req)              (utterance supplied up front — no audio path yet)
  ▼
AwaitingPolicyApproval
  │ policy.evaluate(...)
  ├── Allow        → RouterDispatched → Completed
  ├── Ask          → AwaitingPolicyApproval   (terminal for this slice)
  ├── DraftOnly    → Deflected                 (terminal for this slice)
  ├── Deny         → PolicyDenied              (terminal)
  └── NeedsUpgrade → PolicyDenied              (terminal)
```

The full canonical superset (Listening, EndOfUserSpeech, ReflexClassifying,
ReflexAck, DeliberativeThinking, ToolExecuting, Drafting, Speaking, BargeIn,
Repairing, TimedOut, Errored) is intentionally deferred — there is no audio
path, reflex classifier, or deliberative route yet.

Documented in the module-level comment of `packages/l1-interaction/src/turn.rs`
and in the L1 README.

---

## 2. Public APIs added to `l1-interaction`

New module: `packages/l1-interaction/src/turn.rs`.

```rust
pub struct TurnRequest {
    pub session_id: SessionId,
    pub persona: PersonaId,
    pub task_id: Option<TaskId>,
    pub utterance: String,
    pub capability: Capability,
    pub resource: ResourceScope,
    pub emitted_at: MonotonicTimestamp,
}

pub struct RouteOutcome { pub tier: String, pub provider: String, pub response_text: String }

pub enum BlockReason { AwaitingApproval, Denied, NeedsUpgrade, DraftOnly }

pub struct TurnResult {
    pub turn_id: TurnId,
    pub final_state: TurnState,
    pub policy_decision: Decision,
    pub route: Option<RouteOutcome>,
    pub block: Option<BlockReason>,
    pub state_trace: Vec<TurnState>,
}

pub trait TurnRouter: Send + Sync {
    fn dispatch(&self, turn_id: &TurnId, prompt: &str, decision: &Decision)
        -> Result<RouteOutcome, L1Error>;
}

pub struct TurnEngine { /* private */ }
impl TurnEngine {
    pub fn new(policy: Arc<dyn PolicyEngine>, router: Arc<dyn TurnRouter>) -> Self;
    pub fn handle_turn(&self, request: TurnRequest) -> Result<TurnResult, L1Error>;
}

pub struct EchoStubRouter;       // trivial test / dev-harness router
impl TurnRouter for EchoStubRouter { ... }
```

All of these are re-exported from `aether_l1_interaction`'s root. Existing
stub surfaces (`InteractionEngine`, adapter traits, `InteractionEvent`) are
unchanged.

---

## 3. How L1 calls L5 and L4, and boundary compliance

**L5 (policy):**
- L1 depends on `aether-l5-policy` (allowed by `tools/lint-layer-boundaries`).
- `handle_turn` builds an `aether_l5_policy::policy_engine::ActionRequest`
  from the `TurnRequest`, calls `PolicyEngine::evaluate`, and matches on
  the returned `Decision` to pick the next transition. The engine holds
  `Arc<dyn PolicyEngine>`, so callers can inject either `DefaultPolicyEngine`
  with in-memory backends or with `DurableBackends` (sqlite).

**L4 (router):**
- L1 does **not** depend on `aether-l4-router` — a sibling-to-sibling edge
  would violate `CLAUDE.md` §1.4 and the boundary linter's allowlist.
- Instead, L1 defines its own narrow trait `TurnRouter` (one method,
  returns an L1-local `RouteOutcome`) and the caller supplies an impl. An
  `EchoStubRouter` is shipped for tests and future dev harnesses. A real
  L4 adapter belongs in a future crate outside `packages/l1-interaction`
  (e.g. an `apps/` binary or a dedicated wiring crate) that depends on
  both `aether-l1-interaction` and `aether-l4-router`.

The boundary linter run (`python tools/lint-layer-boundaries/check.py`)
reports 0 violations after this wave.

---

## 4. Tests added

`packages/l1-interaction/tests/turn_slice.rs` (default build):

| Test                                                  | Verifies                                                                      |
|-------------------------------------------------------|-------------------------------------------------------------------------------|
| `allow_path_reaches_router_and_completes`             | FilesRead (Auto) → `Decision::Allow` → `EchoStubRouter` fires → `Completed`. Also asserts the full `state_trace`. |
| `deny_path_blocks_before_router`                      | ShellExec (Deny) → `Decision::Deny` → `PolicyDenied`, router never fires.     |
| `ask_path_is_terminal_for_this_slice`                 | FilesCreate (Ask) → `Decision::Ask` → `AwaitingPolicyApproval`, route None.   |
| `unsupported_capability_returns_needs_upgrade_block`  | BrowserOpen (absent from preset) → `Decision::NeedsUpgrade` → `PolicyDenied`. |

`packages/l1-interaction/tests/turn_slice_sqlite.rs` (feature-gated
`sqlite-backend`):

| Test                                       | Verifies                                                                                                            |
|--------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| `allow_path_persists_grant_to_sqlite`      | Same allow flow as above but with `DurableBackends::open(path)`; after `handle_turn`, `SqliteGrantLedger` snapshot contains one active FilesRead grant. |

A new crate feature `sqlite-backend` on `aether-l1-interaction` forwards
to `aether-l5-policy/sqlite-backend` and adds `tempfile` as a dev-dep.
Default builds are unchanged — no new runtime dependencies.

---

## 5. Checks run

| Check                                                                          | Result                         |
|--------------------------------------------------------------------------------|--------------------------------|
| `cargo fmt -p aether-l1-interaction`                                           | clean                          |
| `cargo clippy -p aether-l1-interaction --tests`                                | 0 new warnings (2 pre-existing missing-doc warnings on Wave 4 stub events carried forward) |
| `cargo test -p aether-l1-interaction`                                          | 6 passed (2 smoke + 4 slice)   |
| `cargo test -p aether-l1-interaction --features sqlite-backend`                | 7 passed (adds sqlite test)    |
| `cargo test --workspace`                                                       | all green                      |
| `python tools/lint-layer-boundaries/check.py`                                  | OK, 0 violations               |

---

## 6. TODOs / limitations

- **Audio states** (Listening, EndOfUserSpeech, ReflexClassifying, ReflexAck,
  BargeIn) are untouched. They only become meaningful once STT/TTS adapters
  and the reflex classifier exist.
- **Timing budgets** (`TimingBudgets` exists since Wave 4) are not enforced
  by `TurnEngine` yet — no deadline checks, no `TimedOut` transition.
- **Ask → approval → continue** loop is not implemented. `Ask` is terminal
  for this slice; `respond_approval` must be driven externally today, and
  the follow-on evaluate → dispatch arc is a future wave.
- **Real routing** — `EchoStubRouter` is a placeholder. A genuine L4 adapter
  (crate outside L1) must implement `TurnRouter` by calling
  `aether_l4_router::ModelRouter`. Tier selection, cost-event emission, and
  Decision-4 per-step re-eval live there, not in L1.
- **No CLI harness** was added. The test surface gave the same observability
  at lower cost; a CLI is deferred to the community-demo wave.
- **Presence / persona wiring** — `PresenceClient` adapter trait already
  exists in `engine.rs` but is not called from `TurnEngine`. Emitting
  `on_turn_state` after each transition is the natural next extension.
- **Tracing** — `state_trace` lives on `TurnResult`; no `tracing` spans are
  emitted yet. Structured-log integration is a cheap follow-up.

---

## 7. Recommended next session

**Community demo slice** built on top of this vertical path. Add a tiny
`apps/l1-cli/` (or `examples/`) crate that:

1. depends on `aether-l1-interaction` and `aether-l4-router`,
2. implements `TurnRouter` by calling a minimal `ModelRouter` stub from
   L4 (or a reflex-tier string adapter),
3. reads a prompt from stdin, constructs a `TurnRequest`, runs
   `handle_turn`, pretty-prints `TurnResult` (state trace, decision,
   route / block).

That exercise pressure-tests:

- whether `TurnRouter ↔ ModelRouter` bridges cleanly,
- whether the `RouteOutcome` shape is rich enough for a real tier,
- and gives the first runnable "hello aether" path a human can drive.

If that expands, peel back to a test-only bridge crate instead.

Alternative second choice: deeper audit-chain work (HMAC + prev_hash
linking in `write_audit`), which becomes easier to verify now that we
have a real caller that produces audit rows end-to-end.

---

**Status:** L1.1 complete. Working tree ready for commit.
