# @aether/l5-policy

**Status:** Wave 2 scaffold. Types, traits, and the 16-command IPC surface only. **No evaluator logic. No persistence. No Tauri handler.**

L5 is the single, non-bypassable authorization gate for every autonomous action Aether takes. Nothing executes without `Decision::Allow`.

## Layout

```
packages/l5-policy/
├── Cargo.toml
├── README.md
├── src/
│   ├── lib.rs            — public surface; re-exports per module
│   ├── common.rs         — id newtypes, Cents, MonotonicTimestamp, ActorRef
│   ├── capability.rs     — Capability + Decision-3 additions; ResourceScope; RiskClass; ProvenanceTag
│   ├── decision.rs       — Decision, DenyReason, DraftSource, ReEvalTrigger (8), HardcodedBlockId
│   ├── approval.rs       — ApprovalTicket, ApprovalResponse, UserChoice (+DeferToDraft)
│   ├── grants.rs         — Grant, GrantDuration, ApprovalMode, GrantLedger trait, PersonaCompiledPolicyDefaults
│   ├── audit.rs          — AuditId, AuditRecordEvent, AuditFilter, AuditSummary, StageTrace
│   ├── byok.rs           — CostEvent, CostCap, CostWindow, CostThreshold, ProviderId
│   ├── posture.rs        — PrivacyPosture, PolicyPostureSummary, PostureTrigger, DegradedMode
│   ├── events.rs         — L5Event sum + per-event structs (9 variants)
│   ├── ipc.rs            — PolicyCommands trait (16 commands); PolicyIpcError
│   ├── policy_engine.rs  — PolicyEngine trait + PolicyEngineError; ActionRequest; EventFilter; EventStream
│   └── storage_hooks.rs  — GrantStore, AuditStore, CostCounterStore traits (impls live in aether-storage, Wave 3)
└── tests/
    └── smoke.rs          — shape-only assertions of the locked decisions
```

## Locked decisions reflected in the scaffold

All from `planning/DECISION_LOCK_PASS_2026-04-18c.md` (2026-04-18):

| # | Lock | Where it shows up |
|---|---|---|
| 1 | `Decision::NeedsUpgrade(CapabilityPath)` as a **top-level** variant (not a `DenyReason`) | `decision::Decision::NeedsUpgrade { capability_path, audit_id, suggested_preset }` |
| 2 | `Decision::DraftOnly { source: DraftSource::{System, UserChoice} }` + `UserChoice::DeferToDraft` | `decision::DraftSource`, `Decision::DraftOnly`, `approval::UserChoice::DeferToDraft` |
| 3 | Three new IPC commands + two new capabilities | `ipc::PolicyCommands::{export_audit, set_cost_cap, reset_cost_counter}`; `Capability::{AuditExport, CostCapAdmin}`; `AuditExportFormat` |
| 4 | Grant-scope re-eval with 8 explicit triggers | `decision::ReEvalTrigger` with `ALL` constant of length 8 |
| 5 | BYOK cost-cap re-arm — explicit, re-auth, no auto-resume | `byok` module + `ipc::PolicyCommands::{set_cost_cap, reset_cost_counter}`; UX contract noted in `byok.rs` doc |

## Flagged contradictions (not silently resolved)

Items 6–11 from `L5_interface_pack.md` §10 remain **OPEN**. Each is flagged as a TODO in the code without attempting resolution:

- HMAC key rotation policy (source §14.2) — keyring shape only; rotation policy deferred.
- `AuditExport` capability identifier — now present per Decision 3.
- Plan-preview P1/P2 scope — `preview_plan` returns `PlanPreview { advisory }`; P2 expansion deferred.
- `privileged_profile` mechanics — field present on `PersonaCompiledPolicyDefaults` and `AuditRecordEvent`, flagged as pending ratification.
- Doctrine layer-count drift — consumer concern, not enforced here.

## Dependencies (Wave 2)

- `aether-event-bus` — envelope / source-layer types L5 will publish under.
- `aether-storage` — trait targets live here; real `GrantStore` / `AuditStore` / `CostCounterStore` impls arrive in Wave 3.
- `aether-telemetry` — local-only tracing by default.

## Non-goals of Wave 2

- No 5-layer evaluator.
- No grant ledger implementation.
- No audit hash-chain or HMAC logic.
- No Tauri `invoke` wiring.
- No red-team or property tests beyond enum-shape smoke.
- No `ts-rs` derives (generator not scaffolded yet; `packages/l5-policy-ts/` has hand-written mirror stubs).

## Next wave

Wave 3 — real L5 logic:
1. In-memory `GrantLedger` + tokio broadcast bus integration.
2. 5-layer evaluator (pre-gates → feature → action → resource → mode → duration).
3. Audit chain writer hooked to `aether-storage`.
4. `persona_swap_commit` subscription + `MinimumTrustPersona` fallback.
5. `tools/lint-policy-bypass/` prototype enforced against a first L4 stub.
