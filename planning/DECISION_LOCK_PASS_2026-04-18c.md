---
status: working
date: 2026-04-18
session: decision-lock pass 2026-04-18c
owner: Don (coordinator) — coordinator-recommended locks subject to Don ratification
role: final pre-implementation decision resolution for 5 control-plane items; unblocks X1 Wave 0
---

# Decision Lock Pass — 2026-04-18c

Resolves the top 5 remaining control-plane decisions identified at the end of the implementation-prep session. Each entry below follows: options → impacted layers/files → recommendation → tradeoffs → status.

Where a status is `[DECIDED 2026-04-18]`, the decision is coordinator-locked pending Don's ratification and logged in `OPEN_QUESTIONS.md`. Where status is `[OPEN]`, the decision remains in Don's queue.

This pass does **not** weaken Tauri doctrine, the 7-layer model, or the monorepo baseline. No code. No scaffolding. No git.

---

## Decision 1 — `Decision::NeedsUpgrade` encoding

### Options
- **A. Top-level variant.** `enum Decision { Allow, Ask(ApprovalTicket), DraftOnly, Deny(DenyReason), NeedsUpgrade(CapabilityPath), … }`. The `NeedsUpgrade` case is peer-level with `Deny`.
- **B. Deny-reason variant.** `Decision::Deny { reason: DenyReason::NeedsUpgrade(CapabilityPath) }`. Reuses the `Deny` branch and threads the upgrade target via the reason enum.

### Impacted layers / files
- `plans/L5_policy_engine_system_design.md` §4.2 (`Decision` enum)
- `plans/implementation_prep/L5_interface_pack.md` §6
- `plans/implementation_prep/L1_interface_pack.md` §7 (handler branch table)
- `plans/implementation_prep/L7_interface_pack.md` §3 (upgrade-UX rendering)
- `plans/implementation_prep/event_contracts_master.md` (payload draft for `policy_decision`)

### Recommendation
**Option A — top-level `Decision::NeedsUpgrade(CapabilityPath)`.**

### Tradeoffs
- **Pro (A):** L1's reflex-handler branch table is flat: `Allow` / `Ask` / `DraftOnly` / `Deny(safety-deflect)` / `NeedsUpgrade(upgrade-UX)`. L7 can pattern-match without unpacking nested reason enums. Audit records and trust-center views distinguish "denied for a reason" from "denied but upgradable" at a glance.
- **Pro (B):** Fewer top-level variants; one fewer branch for consumers that collapse both into a "refused" bucket.
- **Con (A):** One more top-level variant to maintain.
- **Con (B):** `Deny` carries two semantically different outcomes; L7 must inspect `DenyReason` to decide whether to show "you can't do this" vs "upgrade to do this". Easier to mis-render in multi-language/UI variants.

Upgrade-UX is a first-class L7 surface (per L7 §3) and is also a first-class L5 audit event consumer. Giving it its own variant matches how it flows through the system.

### Status
**[DECIDED 2026-04-18]** — coordinator-recommended lock; Option A.

---

## Decision 2 — `Decision::AllowDraft` vs `DraftOnly`

### Options
- **A. Keep existing `Decision::DraftOnly`; add `UserChoice::DeferToDraft` in L7.** L5 emits `DraftOnly` in two source cases: (1) system-initiated (policy says "this capability is draft-only in this posture"), (2) user-initiated via approval where the user picked "Draft only" and L7 sends `approval_response.user_choice = DeferToDraft`, which L5 resolves to `Decision::DraftOnly { source: UserChoice }`. One variant, discriminated by an inner `source` field.
- **B. Add a distinct `Decision::AllowDraft { side_effects_inhibited: true }` variant.** Two top-level variants (`DraftOnly` for system-initiated, `AllowDraft` for user-chosen).
- **C. Remove the UI option.** L7 drops the "Draft only" button; user must either Allow or Deny.

### Impacted layers / files
- `plans/L5_policy_engine_system_design.md` §4.2 (`Decision` + `ApprovalResponse`)
- `plans/implementation_prep/L5_interface_pack.md` §4 (outbound PolicyDecision) + §3 (inbound ApprovalResponse)
- `plans/implementation_prep/L7_interface_pack.md` §3 (approval prompt actions) + §4 (approval_response payload)
- `plans/implementation_prep/L4_interface_pack.md` §7 (ToolResult handling of DraftOnly — side-effect inhibition)
- `plans/implementation_prep/event_contracts_master.md` (payload for `policy_decision` + `approval_response`)

### Recommendation
**Option A — single `Decision::DraftOnly { source: System | UserChoice }` + `UserChoice::DeferToDraft` on the L7 approval-response payload.**

### Tradeoffs
- **Pro (A):** Single downstream handling path for L4 (side-effect inhibition) regardless of who initiated it. Audit log still tells the whole story via the `source` field and the underlying approval-response record. Minimal surface growth.
- **Pro (B):** Clearer split if system-initiated draft-only has materially different audit/telemetry handling. (Not currently indicated.)
- **Pro (C):** Simplest; removes an edge case.
- **Con (A):** Requires L5 to tag `source` on emission; L4 must honor "inhibit side effects" identically for both sources (which is in fact the design intent, so this isn't a real cost).
- **Con (B):** Two variants that behave identically in L4; handler-code duplication.
- **Con (C):** Loses a common user-requested UX: "show me what you'd do without actually doing it." Valued for Operator and Power-User presets. Rejecting this capability is a product regression.

### Status
**[DECIDED 2026-04-18]** — coordinator-recommended lock; Option A. L5 adds a `source: DraftSource { System, UserChoice }` discriminant to the `DraftOnly` variant; L7 adds `UserChoice::DeferToDraft` to the approval-response payload. L4 side-effect-inhibition path is a single branch regardless of source.

---

## Decision 3 — Missing L5 IPC commands

Three commands referenced by L7 but not yet in the canonical L5 §5 surface.

### Commands to add
1. **`policy.export_audit(filter: AuditFilter, format: AuditExportFormat) -> Uri`**
   - Returns a local file URI to a signed export bundle (JSON-lines or CSV, per `format`).
   - Capability: new `Capability::System.ExportAudit` (risk class: High).
   - Default approval mode: `Ask` (every export is a conscious user action).
   - Re-auth required before invocation (fresh approval modal).
   - Emits an `audit_record` for the export itself.
2. **`policy.set_cost_cap(provider: ProviderId, window: CostWindow, cap: CostCap) -> ChangeId`**
   - Sets or raises a per-provider, per-window (daily/monthly) cap.
   - Capability: new `Capability::System.CostCapAdmin` (risk class: High).
   - Default approval mode: `Ask` with re-auth.
   - Emits `cost_cap_rearmed` (newly proposed event — locked below) and an `audit_record`.
   - Enforces hard floor: cannot set cap below a non-negotiable safety minimum (Don-tunable per installation).
3. **`policy.reset_cost_counter(provider: ProviderId, window: CostWindow) -> ChangeId`**
   - Resets the rolling counter (typically after window rollover, or at explicit user request post-audit-review).
   - Capability: `Capability::System.CostCapAdmin` (same as set_cost_cap).
   - Default approval mode: `Ask` with re-auth.
   - Emits `cost_cap_rearmed` and an `audit_record`.

### Impacted layers / files
- `plans/L5_policy_engine_system_design.md` §2 (capability taxonomy — add two new capabilities), §5 (IPC commands), §4 (event catalog — confirm `cost_cap_rearmed` outbound).
- `plans/implementation_prep/L5_interface_pack.md` §4 + §6 + §7 (PolicyIpcError additions).
- `plans/implementation_prep/L7_interface_pack.md` §4 (IPC commands consumed).
- `plans/implementation_prep/event_contracts_master.md` — `cost_cap_rearmed` moves from "newly proposed" to confirmed; author = L5.
- `plans/implementation_prep/sqlite_schema_pack.md` — no schema change; existing `cost_counters` table already supports cap fields; `policy_audit_log` absorbs export events.

### Recommendation
**Add all three commands.** All are clearly required by L7; no commands currently exist that serve these use cases; no cheaper alternative (piping through existing `policy.evaluate` would be a worse contract).

### Tradeoffs
- **Pro:** Unblocks trust-center export, cap-hit-raise flow, and counter-reset. Closes three named BLOCKS items from the prior pass.
- **Pro:** Adds only two new capabilities (`System.ExportAudit`, `System.CostCapAdmin`); both are administratively scoped and default-Ask with re-auth, consistent with the existing hardcoded-blocks + risk-class model.
- **Con:** Widens the L5 command surface from 13 to 16 (14 commands + 2 we collapse into one capability family). Net complexity modest; all three share the "admin-class capability + re-auth" pattern.
- **Con:** `cost_cap_rearmed` becomes a confirmed event; schema lock bumps minor version on L5's event catalog.

### Status
**[DECIDED 2026-04-18]** — coordinator-recommended lock. All three commands added. Two new capabilities declared. `cost_cap_rearmed` promoted from proposed to confirmed event (L5 emitter).

---

## Decision 4 — Per-step policy re-evaluation rule for multi-step tool plans

### Options
- **A. Initial grant covers subsequent steps within declared scope.** A `grant_issued` covers `(capability, resource_pattern, persona, session | TTL)`. L4 does **not** re-evaluate for subsequent steps whose `(capability, resource, persona)` fall inside the grant's declared scope. L4 **must** re-evaluate when a step crosses any of: different capability; resource outside the pattern; persona change; remote escalation triggering privacy-posture gate; cost-threshold crossing; provenance class elevation (e.g., private-tagged content entering the prompt payload).
- **B. Full re-evaluation every step.** L4 round-trips `policy.evaluate` for every step, regardless of whether the grant would cover it.
- **C. Always re-evaluate on any remote call; never re-evaluate within local-only steps.** Hybrid.

### Impacted layers / files
- `plans/L5_policy_engine_system_design.md` §3 (evaluator), §7 (grant ledger semantics).
- `plans/implementation_prep/L4_interface_pack.md` §7 (tool protocol, multi-step orchestration), §8 (dependency expectations).
- `plans/implementation_prep/L5_interface_pack.md` §3 (inbound ActionRequest semantics) + §4 (GrantIssued scope semantics).
- `plans/L1_L4_L5_L7_integration_notes.md` §10 Q1.
- `plans/implementation_prep/event_contracts_master.md` — ordering/idempotency notes on `action_request` + `grant_issued`.

### Recommendation
**Option A with an explicit list of re-eval triggers.**

Canonical rule (to be cross-referenced from L4 §7 and L5 §3):

> A `GrantIssued` authorizes `(capability, resource_pattern, persona, duration)`. L4 **skips** re-evaluation for subsequent tool-plan steps whose `(capability, resource, persona)` fall inside that grant and whose execution does not cross any of the re-eval triggers below. L4 **must** emit a fresh `ActionRequest` and await a new `PolicyDecision` when any of the following holds:
> 1. Capability differs from the grant's capability (including sub-capability).
> 2. Resource is outside the grant's declared `resource_pattern`.
> 3. Persona has changed (`persona_swap_commit` occurred since grant issued).
> 4. Step triggers a remote-tier escalation that was not covered at grant time (privacy-posture gate must re-fire).
> 5. Provenance class has elevated (e.g., a private-tagged memory item now enters the prompt payload).
> 6. A `cost_threshold_hit` has fired between the grant issuance and this step.
> 7. A `GrantRevoked` or `EmergencyRevokeAll` event has landed since the grant was issued.
> 8. Grant's TTL has expired (if time-bounded).

### Tradeoffs
- **Pro (A):** Avoids approval fatigue for Operator+ presets running multi-step tasks (the intended UX). Preserves safety via the explicit re-eval triggers. Audit trail remains complete (initial `GrantIssued` + any re-eval events + a `tool_call_completed` per step).
- **Con (A):** Requires L4 to track grant coverage per in-flight plan and detect all 8 re-eval triggers. Gate-bypass risk if triggers are implemented incompletely.
- **Pro (B):** Maximally safe; every step is policy-checked. Never silent-passes a widened capability.
- **Con (B):** Approval fatigue. Operator preset tasks with 4-step plans would trigger 4 approval prompts even when the initial "allow for this task" grant logically covers the whole plan. This degrades UX and pushes users toward "Allow forever" (worse security outcome).
- **Con (C):** Hybrid is the worst of both — still approval-heavy for local plans, but still complex to implement. Rejected.

### Status
**[DECIDED 2026-04-18]** — coordinator-recommended lock; Option A. The 8-trigger list is canonical. L4 §7 and L5 §3 both reference this rule.

---

## Decision 5 — BYOK cost-cap re-arm UX flow

### Options
- **A. Explicit user-initiated re-arm with re-auth; parked plans not auto-resumed.**
  - Cap hit → L5 emits `cost_threshold_hit` → L4 denies further requests for that provider → L1 enters repair/deflection for any in-flight step → L7 shows cap-hit modal with options:
    - **Raise cap** — invokes `policy.set_cost_cap(provider, window, new_cap)`, re-auth required.
    - **Reset counter** — invokes `policy.reset_cost_counter(provider, window)`, re-auth required.
    - **Switch to local tier** — invokes `router.set_tier_override(Local)` for the remainder of the session.
    - **Wait until reset** — dismiss modal; L4 continues to deny the provider until window rollover.
  - On cap raise or counter reset: L5 emits `cost_cap_rearmed`. L4 unblocks subsequent requests.
  - **Parked plans are NOT auto-resumed.** User must explicitly re-initiate the task. Rationale: the user saw the cap hit; they may have chosen to pause deliberately; auto-resume would surprise them.
  - All three command invocations, plus the original deny events, are recorded in the audit log.
- **B. Implicit auto-resume after re-arm.** Same as A but L4 resumes parked plans automatically once `cost_cap_rearmed` lands.
- **C. Silent cap raise without re-auth.** Same as A but no re-auth required to raise cap. (Rejected outright — violates trust posture for an administrative-class capability.)

### Impacted layers / files
- `plans/L5_policy_engine_system_design.md` §9 (BYOK hard-cap), §10 (privacy-posture gate is adjacent).
- `plans/implementation_prep/L5_interface_pack.md` §4 (outbound `cost_cap_rearmed`) + §5 (sync/async boundaries — re-auth is sync-blocking).
- `plans/implementation_prep/L4_interface_pack.md` §9 (BYOK wallet), §14 (failure modes — cap-hit path).
- `plans/implementation_prep/L7_interface_pack.md` §7 (cost-visibility UX — cap-hit modal actions), §10 (event subscription).
- `plans/implementation_prep/event_contracts_master.md` — `cost_threshold_hit` (existing) + `cost_cap_rearmed` (confirmed per Decision 3).

### Recommendation
**Option A — explicit user-initiated re-arm with re-auth; parked plans not auto-resumed.**

### Tradeoffs
- **Pro (A):** Preserves trust: the user explicitly consented to the new cap. No surprise resumes after a deliberate pause. Audit trail is clean and complete. Re-auth gate matches the administrative-class capability per Decision 3.
- **Con (A):** Slightly more friction — user must re-initiate a task after raising the cap. Mitigated by L7 surfacing "the task that hit the cap was: …" in the modal so resumption is one click.
- **Pro (B):** Lower friction; faster perceived UX.
- **Con (B):** Auto-resume after a cap hit is exactly the class of behavior that leads to unexpected spend. Violates the user's implicit "I saw the cap; let me think" pause.
- **Con (C):** Silent raise defeats the purpose of the cap; rejected.

### Status
**[DECIDED 2026-04-18]** — coordinator-recommended lock; Option A. L7 cap-hit modal surfaces four actions (Raise cap, Reset counter, Switch to local, Wait). `cost_cap_rearmed` is the shared signal. Parked plans are not auto-resumed.

---

## Summary of locks

| # | Decision | Option | Status |
|---|---|---|---|
| 1 | `Decision::NeedsUpgrade` encoding | Top-level variant | [DECIDED 2026-04-18] |
| 2 | `DraftOnly` vs `AllowDraft` | Unify into `DraftOnly { source }` + `UserChoice::DeferToDraft` | [DECIDED 2026-04-18] |
| 3 | Missing L5 commands | Add `export_audit`, `set_cost_cap`, `reset_cost_counter` + two capabilities | [DECIDED 2026-04-18] |
| 4 | Per-step re-eval rule | Grant-scope with 8-trigger re-eval list | [DECIDED 2026-04-18] |
| 5 | BYOK cap re-arm UX | Explicit re-auth; no auto-resume | [DECIDED 2026-04-18] |

All 5 are coordinator-locked. None remain `[OPEN]` after this pass.

Downstream files that will need a small follow-up edit (out of scope for this session — logged in OPEN_QUESTIONS as FOLLOW-UP):
- `plans/L5_policy_engine_system_design.md` §2, §3, §4, §5, §7, §9 — reflect locks 1–5.
- `plans/implementation_prep/L5_interface_pack.md` — reflect lock 1, 2, 3, 4, 5.
- `plans/implementation_prep/L4_interface_pack.md` — reflect lock 4, 5.
- `plans/implementation_prep/L7_interface_pack.md` — reflect lock 2, 5.
- `plans/implementation_prep/event_contracts_master.md` — promote `cost_cap_rearmed` from proposed to confirmed (lock 3); update payload drafts to reflect lock 1 + lock 2 discriminant.

These are mechanical edits, not design work. They can happen in a cleanup pass or as the first sub-step of the L5 implementation session.

---

## X1 Wave 0 readiness checklist

Goal: create the monorepo shell at `file:///C:/Users/dbhav/Projects/aether/`, move `aether-planning/` contents into `planning/`, land workspace configs + root docs.

Ready:
- [x] Monorepo layout locked as working baseline (`planning/monorepo_plan_draft.md`, status: working).
- [x] 7-layer-to-package mapping locked (monorepo §2).
- [x] Shared-infra packages enumerated (`event-bus`, `types`, `ui-kit`, `media-engine`, `storage`, `telemetry`).
- [x] Guardrail tooling identified (`cargo-deny`, `lint-policy-bypass`, `lint-layer-boundaries`, `lint-private-asset-leak`, `CODEOWNERS`).
- [x] Tauri long-term doctrine locked; G1 approved.
- [x] Planning corpus defined as repo-resident (under `planning/`).
- [x] 5 control-plane decisions locked this pass.

Still open but **not blocking Wave 0**:
- [ ] Canonical repo name (working name `aether/` is fine for Wave 0; final product name is a marketing decision, independent).
- [ ] Sibling-repo fate (`aether-desktop-voice/`, `aether-frontend-ux/`, `aether-personas/`) — archive after Wave 0; doesn't block creation of the new repo.
- [ ] Isabelle_Kunstig physical location (stays in parallel per phased-migration decision).
- [ ] History-preservation policy — default to `git subtree add` to preserve; can be decided at Wave 0 start.

**Wave 0 readiness: GO.** All blocking items resolved. The four "still open" items have reasonable defaults and are not on the Wave 0 critical path.

---

## Scaffold-readiness checklists

### `packages/event-bus`

Ready:
- [x] 74-event catalog with typed payloads (`plans/implementation_prep/event_contracts_master.md`).
- [x] Versioning rules (SemVer, ts-rs regen) locked.
- [x] Source/change_id/seq conventions per X3 §3.2.
- [x] 14 invariants enumerated.
- [x] Newly-proposed events reconciled: `cost_cap_rearmed` confirmed (Decision 3); `degraded_mode_entered` + `degraded_mode_cleared` + `ingestion_candidate_accepted` still pending author confirmation but non-blocking (emitters default to L5/L1/L4/L2).
- [x] Boundary-enforcement stance: every event crosses through typed bindings; sibling-layer imports forbidden.

Residual (non-blocking):
- [ ] `memory_promoted` still undefined — L2 confirms at its scaffold session, not at event-bus scaffold.
- [ ] `plan_preview_ready` future addition when `policy.preview_plan` lands — non-blocking.

**Scaffold readiness: GO.**

### `packages/storage`

Ready:
- [x] 18 DRAFT SQLite tables (`plans/implementation_prep/sqlite_schema_pack.md`).
- [x] 5 append-only tables with BEFORE UPDATE/DELETE triggers specified.
- [x] Hash-chain + HMAC audit pattern designed.
- [x] Migration runner strategy (schema_versions table, atomic-at-startup).
- [x] Single-writer rule (tauri-plugin-single-instance) ratified.
- [x] WAL mode + foreign-key pragma stance locked.
- [x] Filesystem scope locked (`%APPDATA%/Aether/Pro/data/aether.db` per X3 §7).

Residual (soft-blocking, can defer behind trait):
- [ ] Vector-store vendor (sqlite-vss / lancedb / qdrant-embedded) — `EmbeddingStore` trait abstracts this; vendor choice can happen during L2 scaffold, not storage scaffold.
- [ ] Encryption scheme (SQLCipher whole-DB vs per-column) — recommend whole-DB; Don to confirm. Non-blocking if we scaffold with SQLCipher toggle behind a build flag.
- [ ] Separate audit DB vs single DB — recommend single DB for Wave 1; split at Phase 2 if WAL pressure warrants. Non-blocking.

**Scaffold readiness: GO** (with the three residual items explicitly deferred behind traits/flags).

### `packages/l5-policy`

Ready:
- [x] `PolicyEngine` trait + 6 methods (`plans/implementation_prep/L5_interface_pack.md`).
- [x] `Decision` enum (now with Decision-1 + Decision-2 locks).
- [x] `DenyReason`, `ApprovalMode`, `GrantDuration`, `Capability` enums.
- [x] 9 events (now including `cost_cap_rearmed` as confirmed L5 outbound per Decision 3).
- [x] IPC command surface: 13 existing + 3 new (`policy.export_audit`, `policy.set_cost_cap`, `policy.reset_cost_counter`) = 16 total per Decision 3.
- [x] 2 new capabilities (`System.ExportAudit`, `System.CostCapAdmin`) per Decision 3.
- [x] Grant ledger DDL + append-only audit log DDL + cost_counters DDL (`sqlite_schema_pack.md`).
- [x] Per-step re-eval rule (8 triggers) locked per Decision 4 — L5 evaluator + GrantIssued scope semantics unambiguous.
- [x] BYOK cap re-arm flow locked per Decision 5.
- [x] Degraded modes (SafeMode / AuditBroken / LedgerCorrupt / MinimumTrust) designed.
- [x] Hash-chain + HMAC audit mechanics designed.

Residual (non-blocking):
- [ ] `memory_promoted` event: L5 does not emit; non-blocking for L5 scaffold.
- [ ] HMAC key rotation epoch-transition: implementation-level detail; handled inside L5 scaffold session.
- [ ] Doc-anchor drift on `12_*` and `13_*`: cosmetic; not blocking.

**Scaffold readiness: GO.**

---

## Go / no-go recommendation

**GO for X1 Wave 0 immediately after this session.**

Rationale:
- All 5 control-plane BLOCKS decisions from the prior pass are resolved at coordinator-recommendation level.
- Monorepo baseline is accepted as working (since 2026-04-18 first pass).
- Tauri G1 is approved.
- All 7 layers have implementation-grade system designs.
- Interface packs, event contracts, SQLite schema, and test matrix are in place.
- Downstream follow-up edits to reflect locks 1–5 are mechanical and can happen inside the scaffold sessions rather than gating Wave 0.

The three next-priority packages (`packages/event-bus`, `packages/storage`, `packages/l5-policy`) are all scaffold-ready pending Wave 0 shell creation.

No remaining BLOCKS-severity items. Residual open questions (vector-store vendor, encryption scheme, anti-uncanny on Lite, persona-swap safe-boundary strictness, etc.) are DELAYS or DEFERS per the handoff notes and do not obstruct Wave 0 or the first three package scaffolds.

---

## What the very next implementation session should be

**Session: X1 Wave 0 — Monorepo Genesis.** Coordinator + X1 agent. ~1 session.

Scope:
1. Create repo at `file:///C:/Users/dbhav/Projects/aether/` (working name `aether/`).
2. Initialize `Cargo.toml` workspace, `package.json` + `pnpm-workspace.yaml`, `rust-toolchain.toml`.
3. Create empty `apps/`, `packages/`, `infra/`, `tools/`, `planning/`, `research/`, `docs/`, `personas/` with README stubs.
4. Move `aether-planning/` into `planning/` via `git subtree add` to preserve history.
5. Land root `README.md`, `CLAUDE.md` (AI-agent operating rules), `CODEOWNERS`, `.gitignore`.
6. Freeze: no other work until Don approves Wave 0.

After Wave 0 approval, the immediately next session is **Wave 1 shared-infra scaffolds**: `packages/event-bus` + `packages/types` + `packages/storage` (stubs, typed contracts, migration runner, no business logic). L5 scaffold (`packages/l5-policy`) follows in Wave 2.

---

## References

- file:///C:/Users/dbhav/Projects/aether-planning/OPEN_QUESTIONS.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/IMPLEMENTATION_PREP_INDEX.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L1_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L4_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L7_interface_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/event_contracts_master.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/sqlite_schema_pack.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/implementation_handoff_notes.md
- file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/plans/00_ORCHESTRATION_MAP.md
