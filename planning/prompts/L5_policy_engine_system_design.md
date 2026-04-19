# L5 Policy / Authorization Engine — System Design Prompt

> **Mode:** System design (implementation-oriented). This is **not** a doctrine pass, not a planning pass, and not a code-writing pass. You are producing the engineering blueprint that an implementer (human or agent) could read and begin turning into Rust crates, TS bindings, and SQLite migrations without further planning.
>
> **Working directory:** `file:///C:/Users/dbhav/Projects/aether-planning/`
> **You write to:** `plans/L5_policy_engine_system_design.md` (new file). Do NOT modify doctrine, `OPEN_QUESTIONS.md`, the orchestration map, other layer plans, or the existing `plans/L5_policy_engine.md` (your upstream).
> **You may read anything in the repo.** Don is the coordinator.

---

## Why L5, why now

Every must-own layer that writes, calls tools, touches files, escalates to remote, or mutates memory is gated by L5. L1 reflex plans, L2 memory writes, L4 tool routes, L7 approvals — none ship correctly until L5's contracts are pinned. L5 is the chokepoint. Designing it first unblocks all other layers to stub against a known, typed interface. L5 is also where the trust moat lives; close-enough SaaS permission frameworks cannot express this product's approval patterns. (See `01_product_doctrine.md` §"Must-own layers" #5.)

---

## Required reading (in order)

1. `plans/L5_policy_engine.md` — upstream plan; authoritative scope.
2. `prompts/L5_policy_engine.md` — execution-agent briefing; mirrors scope and non-negotiables.
3. `01_product_doctrine.md` — especially §"Must-own layers" #5, §"Desktop framework doctrine".
4. `12_permissions_autonomy.md` — capability groups, 4 risk classes, 5 autonomy presets, 5-layer permission model.
5. `13_trust_security_redteam.md` — red-team readiness, trust center, audit completeness.
6. `08_system_architecture.md` — six engines, event bus.
7. `plans/00_ORCHESTRATION_MAP.md` — §5 ownership, §6 dependency DAG, §7 dependency table, §10 conflict-escalation.
8. `plans/X3_tauri_architecture.md` — G1 **APPROVED 2026-04-18**; §2.2 command surface for L5 is your target shape; §7 filesystem scopes bracket the resource scopes you must evaluate.
9. `planning/monorepo_plan_draft.md` — status: working; §2 places L5 at `packages/l5-policy/` (Rust core) + `packages/l5-policy-ts/` (typed bindings).
10. `plans/03_content_lock_v1_port.md` §4 — BYOK hard-cap enforcement is yours.
11. `OPEN_QUESTIONS.md` — current decision log; G1 approval and monorepo-baseline entries are relevant.

---

## Goal of this session

Produce a **system-design document** at `plans/L5_policy_engine_system_design.md` that an implementer can read and start building from. It must stand alone — no "see the plan" hand-waves for the parts that design covers. The plan tells us *what*; this document tells us *how*.

### Required sections (minimum)

1. **Scope recap + non-goals.** One page max. Explicitly list what L5 does and does not own (mirror `plans/L5_policy_engine.md` "Boundaries"; do not redefine).

2. **Capability taxonomy — concrete.**
   - Enumerate every capability and sub-capability from `12_permissions_autonomy.md §9.4` as typed identifiers (`files.read`, `files.write`, `browser.submit`, `email.send`, `system.shell`, `memory.write.durable`, etc.).
   - For each: default risk class, default approval mode per autonomy preset, default grant duration, resource-scope shape (path glob / URL pattern / mailbox folder / memory scope), and which executor layer claims it (L2 / L4 / media engine / L7 / shell).
   - Include the hardcoded non-negotiable blocks (`13` §5; finance/healthcare/password-manager domains, unrestricted disk, silent upload) with rationale.
   - Deliverable format: a table plus a Rust-leaning pseudotype block (`enum Capability { ... }`).

3. **Five-layer permission evaluator — state machine + pseudocode.**
   - Inputs: `ActionRequest { capability, resource, actor_persona, active_grants, session_context, provenance_tags }`.
   - Evaluator layers in order: feature enabled → action in scope → resource in scope → approval mode → grant duration/TTL.
   - Outputs: `Decision { Allow | Ask(ApprovalTicket) | DraftOnly | Deny(Reason) | NeedsUpgrade(CapabilityPath) }`.
   - Show the state machine (Graphviz/Mermaid-style ASCII is fine) and the evaluator pseudocode in one pass. Cover the edge cases: persona hot-swap mid-evaluation, expired grant, revoked-during-ask, tainted provenance (from L2), tier-downgrade stripping a capability.

4. **Event contracts — typed.**
   - For each event (`action_request`, `policy_decision`, `approval_pending`, `approval_response`, `grant_issued`, `grant_revoked`, `audit_record`, `emergency_revoke_all`, `cost_threshold_hit`): field list with Rust types, emitter, subscribers, idempotency rule, and ordering guarantee.
   - Mark which events cross the Tauri IPC bridge to the webview (per `X3` §3.2 projection rules) and which are Rust-internal only.
   - Include `ChangeId` / `seq` / `source_layer` conventions from X3 §3.2.

5. **Tauri IPC command surface for L5.**
   - Flesh out X3 §2.2 "L5 — policy" commands into full request/response types (`policy.evaluate`, `policy.request_approval`, `policy.set_preset`, `policy.list_grants`, plus any you propose: `policy.revoke`, `policy.list_capabilities`, `policy.get_preset`, `policy.explain_decision`).
   - Every command lists: request type, response type, failure vocabulary (typed `thiserror` enum), L5-internal side effects (audit record? event emitted?), UI semantics (blocking? optimistic? returns `ChangeId`?).
   - Flag which commands are themselves capability-gated (e.g. `set_preset` requires re-auth per `X3` §2.2).

6. **Autonomy presets — compiled matrix.**
   - For each of the 5 presets (Observer / Assistant / Operator / Power User / Custom), produce the full capability × (risk class → approval mode) matrix as a table.
   - Show which preset is default for which persona class (see `17_persona_pack_schema.md` if helpful) and how L6's persona-scoped approval defaults overlay the preset (order of precedence: hardcoded-blocks > user-override > persona-default > preset-default > system-default).

7. **Grant ledger — data model.**
   - Fields: `grant_id`, `capability`, `resource_scope`, `approval_mode`, `duration (TTL | session | once | task)`, `issued_at`, `expires_at`, `issued_by (preset | explicit-prompt | persona-default)`, `audit_ref`, `revoked_at`, `revoked_reason`.
   - Indexes, queries, and revocation semantics (single grant / by capability / by persona / emergency revoke all).
   - Storage: SQLite table DDL; relationship to the audit log (grants reference audit records, not the reverse).

8. **Audit log — append-only, tamper-evident.**
   - Record schema: `audit_id`, `timestamp` (monotonic), `actor`, `capability`, `resource`, `decision`, `reason`, `change_id`, `prev_hash`, `record_hmac`.
   - Hash chain rules; HMAC key handling (OS keyring, rotation story at a high level — detailed signing plan deferred to X3 G3).
   - Replay semantics: given the log and initial state, the system reconstructs the current grant ledger deterministically.
   - Export policy: local-canonical; never leaves the machine without an explicit export command (which itself is policy-gated).
   - SQLite table DDL + an explicit note that audit log migrations are coordinated with the updater (X3 §6.2).

9. **BYOK hard-cap — enforcement path.**
   - L4 emits `cost_event` with (provider, tokens, dollars, request_id); L5 maintains per-provider rolling counters; on threshold, emit `policy_decision { Deny(reason=hard_cap) }` for the next `action_request` touching that provider and `cost_threshold_hit` for the trust center.
   - Design the threshold data model (daily / monthly / per-provider / per-persona), the grace behavior (deny immediately vs finish current turn), and how the user re-arms the cap.

10. **Privacy-posture gate.**
    - Inputs: persona privacy posture (from L6 compiled output), provenance tags on memory hits (from L2), intended route (from L4).
    - Rule: any `private`-tagged context in the prompt payload blocks a remote-route `action_request` unless the user has an explicit `allow_remote_with_private` grant. Spec the exact evaluation order relative to the 5-layer evaluator.

11. **Failure and degraded-mode behavior.**
    - Audit-log write failure → deny-all and surface; never allow silently when we can't record.
    - Grant ledger corruption → safe-mode: only hardcoded-allow capabilities (read-only config) until Don clears.
    - Clock skew → monotonic timestamps; TTL evaluation uses monotonic + wall-clock cross-check.
    - L6 persona compile failure → fall back to a baked-in "minimum-trust" persona, deny every non-trivial capability.

12. **Interfaces for stubs (unblock L1 / L2 / L4 / L7).**
    - Minimal shims each consumer can code against before L5 is real: the exact Rust trait, typed error vocabulary, and event subscription shape. Goal: L1 / L2 / L4 / L7 can start their own system-design work against a frozen L5 contract.

13. **Testing strategy (scoped to design-level, not test code).**
    - Red-team attack surfaces to simulate (per `13` §10.3).
    - Property-based tests to run against the evaluator (monotonicity under preset upgrades, revocation idempotency, audit-chain integrity).
    - Replay tests: reconstruct state from log-only.

14. **Open questions surfaced by design.**
    - List every concrete question this design raised that Don needs to lock. Format: question, why it matters, proposed default, impact if defaulted silently.

---

## Constraints

- **Plan, don't code.** No Rust source files, no SQL migrations land in this session. DDL and pseudotypes in the doc are expected; actual `.rs` / `.sql` files are not.
- **Don't modify doctrine.** `01_product_doctrine.md`, `MASTER_OUTLINE_TREE.md`, and `OPEN_QUESTIONS.md` are coordinator-owned. If you find a conflict, flag it in §14 "Open questions" — do not resolve it.
- **Tauri is the long-term shell** (doctrine locked 2026-04-18). Design for Tauri IPC; OSS-Preview pywebview is a shell-adapter concern (X3 §9.3), not a policy-engine concern.
- **7-layer model is canonical.** Reflex lives in L1; do not mention it as a separate layer.
- **Windows paths** in the doc: `file:///C:/Users/dbhav/...` forward slashes, no backticks wrapping URLs, no markdown `[label](url)` wrapping (per global CLAUDE.md).
- **No backwards compatibility.** v1.0 had no real policy engine. Clean sheet.
- **Security defaults:** deny-unknown, fail-closed, never silent-allow when we can't record.
- **Audit log is append-only.** Never allow retro-editing, even in design (no "edit" command on the surface).

---

## Deliverables

1. New file: `plans/L5_policy_engine_system_design.md` with sections 1–14 above.
2. A closing self-review checklist at the end of the doc:
   - [ ] Every capability in `12_permissions_autonomy.md §9.4` appears in §2's table.
   - [ ] Every event in `plans/L5_policy_engine.md` "Owns" bullet appears in §4 with typed fields.
   - [ ] Every command in `plans/X3_tauri_architecture.md` §2.2 "L5" appears in §5 with typed request/response.
   - [ ] Every non-negotiable block from `13_trust_security_redteam.md` §10.3 is either addressed or listed in §14.
   - [ ] §12 gives L1 / L2 / L4 / L7 enough to stub against.
   - [ ] Open questions in §14 do not silently resolve doctrine conflicts.

3. A short final message to Don:
   - File written (with `file:///C:/...` link).
   - Which of the 14 sections are high-confidence vs which surface significant open questions.
   - Top 3 questions that need Don's decision before implementation can begin.

---

## Out of scope

- Actually implementing the engine (Rust crates, SQL migrations, test code).
- Designing L1 / L2 / L4 / L7 — only their stub interfaces against L5.
- Deciding rendering surface, sync transport, mobile stack, or hosted-LLM acceptable-use rules — Don's gates.
- Resolving the BYOK cert-class / HSM question (X3 G3).
- Writing the trust-center UI.

---

## Reporting format

End the session with:
- **What changed** — new file path + LOC.
- **Which sections landed cleanly** vs which flagged conflicts.
- **Top open questions** (max 5) that block implementation.
- **What's next** — the immediately adjacent layer to design (likely L6 persona compiler, since L5 consumes its output; or L1 reflex, since L1 is the first consumer of policy decisions in the turn loop).
