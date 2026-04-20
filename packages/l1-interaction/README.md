# @aether/l1-interaction

**Status:** Wave 4 stub. Traits + key enums only.

L1 owns interaction timing, the turn state machine, and reflex routing.

## References

- `planning/plans/L1_interaction_timing_system_design.md`
- `planning/plans/implementation_prep/L1_interface_pack.md`

## Wave 4 contents

- `TurnId`, `TurnState` (19 variants), `ReflexClass`, `TimingBudgets`.
- `InteractionEngine` trait with 5 method signatures.
- 5 adapter traits: `ReflexClassifier`, `Stt`, `Tts`, `ModelRouterClient`, `PresenceClient`.
- `InteractionEvent` + `InteractionEventKind`.
- `L1Error`.

## Wave L1.1 — first turn FSM slice

A real, testable vertical slice now lives in `src/turn.rs`.

**Minimal FSM (subset of the 19-state canonical enum):**

```
Idle
  │ handle_turn(req)
  ▼
AwaitingPolicyApproval
  │ policy.evaluate(...)
  ├── Allow        → RouterDispatched → Completed
  ├── Ask          → AwaitingPolicyApproval  (terminal for this slice)
  ├── DraftOnly    → Deflected                (terminal for this slice)
  ├── Deny         → PolicyDenied             (terminal)
  └── NeedsUpgrade → PolicyDenied             (terminal)
```

**Public API:** `TurnEngine::new(policy, router)` + `handle_turn(TurnRequest) -> Result<TurnResult, L1Error>`.

- `policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine>`
- `router: Arc<dyn TurnRouter>` — L1-local narrow trait; L1 does NOT depend on `aether-l4-router` (sibling-engine rule). An `EchoStubRouter` ships for tests / dev harnesses; real L4 adapters live outside L1.

**Tests:** `tests/turn_slice.rs` covers allow / deny / ask / needs-upgrade against `DefaultPolicyEngine` with in-memory backends. `tests/turn_slice_sqlite.rs` (feature `sqlite-backend`) runs the same allow path against `DurableBackends` and asserts the grant is persisted to SQLite.

## Next wave

- L1.2 — audio-path states (Listening, EndOfUserSpeech, ReflexClassifying, ReflexAck) + reflex classifier stub.
- Approval loop — re-enter the FSM after `respond_approval` to continue an `Ask`-blocked turn.
- Real L4 adapter — a crate outside `packages/l1-interaction` implements `TurnRouter` on top of `aether_l4_router::ModelRouter`.
