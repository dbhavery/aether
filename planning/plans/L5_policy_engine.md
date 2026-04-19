# L5 — Policy & Authorization Engine

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.1, §1.5; core trust moat alongside L2)
**Depends on:** L6 persona compiler (supplies persona-scoped approval defaults), L2 memory kernel (provenance-aware reads), L4 model router (routes tool plans only after policy allow), L7 trust UX (renders approval surfaces), event bus (append-only audit log).
**Blocked by:** capability taxonomy lock, audit-log storage format (append-only + integrity), event bus contract for `action_request` / `policy_decision`.

---

## Purpose

Own every authorization decision in the product. Policy is the single gate through which every tool call, file I/O, browser navigation, email action, clipboard touch, memory write, and system action must pass. Nothing bypasses it. The engine evaluates capability-based, resource-scoped, approval-aware, time-bounded grants against the full five-layer model (feature / action / resource / approval / duration) and emits a signed decision on the audit log for every attempt — allowed, asked, denied, or escalated.

## Why must-own

Close-enough SaaS permission frameworks (OS-level sandboxes, OAuth scopes, cloud IAM) are coarse-grained, not resource-scoped to user folders / domains / inboxes, and cannot express the "ask once per task" or "draft-only" approval patterns the UX requires. Trust is the product's moat; if policy is borrowed, the vendor sets the trust ceiling. Red-team defensibility (`13_trust_security_redteam.md` §5 permission bypass, §7 audit completeness) demands a non-bypassable, event-sourced engine we control end-to-end.

## Boundaries

**Owns:**
- Capability taxonomy (Files / Browser / Email / System / Memory / Media / Integrations) with sub-capabilities.
- Five-layer permission evaluator (feature, action scope, resource scope, approval mode, grant duration).
- Four risk classes (Low / Medium / High / Critical) with default approval mapping.
- Five autonomy presets (Observer / Assistant / Operator / Power User / Custom) compiled into capability matrices.
- Approval workflow state machine (auto-allow / ask / draft-only / deny / needs-upgrade).
- Session-grant ledger (active temporary grants with TTL + revocation).
- Append-only audit log with cryptographic integrity (hash-chain, per-record HMAC).
- Non-negotiable hardcoded blocks (finance / healthcare / password-manager domains, unrestricted disk, silent upload).
- Policy decision events on the bus: `action_request`, `policy_decision`, `approval_pending`, `grant_issued`, `grant_revoked`, `audit_record`.
- Emergency-revoke-all primitive.

**Does not own:**
- The UI that renders approval prompts (L7).
- Tool execution itself (engines emit `action_request`; executors run only after allow).
- Memory content or retrieval (L2).
- Routing which model answers (L4).
- Persona-specific approval tuning values (L6 compiles, L5 consumes).
- OS-level sandboxing of the host process (Tauri / platform concern).

## Dependencies

- **L6 persona compiler** — compiles persona onboarding choices into a capability matrix + approval-mode defaults consumed at policy-engine init and on persona hot-swap.
- **L2 memory kernel** — memory writes and reads are policy-gated; L5 reads provenance tags to detect untrusted-context-tainted action requests.
- **L4 model router** — routes tool plans only after a policy `allow`; receives `needs_upgrade` to surface capability-unlock UI.
- **L7 trust UX** — subscribes to `approval_pending` events, renders prompts, posts `approval_response`.
- **Event bus** — append-only, typed, Rust-side.
- **Secure local store** — for grant ledger + audit log, OS-keychain-wrapped keys.

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Capability evaluator core | **Custom (Rust).** The five-layer evaluator is the trust surface; non-negotiable. |
| Preset → matrix compiler | **Custom.** Tightly coupled with persona compiler + UX contract. |
| Audit log storage | **Borrow** SQLite with WAL + custom append-only table + HMAC chain; schema + integrity layer custom. |
| Cryptographic primitives | **Borrow** `ring` / `rustls` for HMAC + signing; never hand-roll crypto. |
| Domain allowlist / denylist data | **Borrow** Public Suffix List + curated category lists (finance / health / password-mgr). Lookup logic custom. |
| Session-grant ledger | **Custom.** TTL semantics + revocation must be exact. |
| Approval UI | **Not this layer** — L7 owns render; L5 owns contract. |
| Policy-as-code DSL | **Defer** (rejected for P0–P2). Preset + custom matrix covers the near term; revisit P4+ if enterprise pressure emerges. |
| Observability / traces | **Borrow** OpenTelemetry Rust SDK; exporters local-only by default (`aether_cross_systems_spec.md`). |

## Key risks

1. **Bypass via unlogged call path.** Any tool invocation that skips `action_request` is a trust break. **Mitigation:** executors expose no public call surface; only the policy engine can signal `execute_approved`. CI static-analysis lint rejects direct executor calls; red-team regression suite asserts every action class emits an `action_request` first.
2. **Audit-log tampering / gaps.** A missing record hides attacker tracks (`13_* §7`). **Mitigation:** append-only SQLite + hash-chain + periodic HMAC checkpoint signed with an OS-keychain key; loader verifies chain at start; corruption surfaces a hard warning.
3. **Approval-prompt fatigue.** Too many asks → users rubber-stamp. **Mitigation:** "ask once per task" default, risk-class-aware bundling, persona-scoped recent-decision memory, and a measurable goal: <1 approval per 5 user-initiated tasks on the Assistant preset.
4. **Session-grant abuse.** A compromised early prompt approves broad scope; later turns exploit it. **Mitigation:** grants are capability + resource + task-id scoped; task boundaries revoke grants; risk-class re-check on every call regardless of prior approval.
5. **Silent capability escalation.** Cognition chains low-risk actions to reach a high-risk outcome. **Mitigation:** risk class evaluated on each call, not on the plan; multi-step plans emit a plan-level `policy_preview` the user sees before execution for Medium+ chains.
6. **Persona hot-swap race.** Old persona's grants applied to new persona's actions. **Mitigation:** persona-swap emits `grant_revoke_all_session`; L5 atomically flushes session ledger before accepting post-swap action requests.
7. **Cross-product drift.** OSS Preview and Pro policy engines diverge, Isabelle overlay bypasses checks. **Mitigation:** single policy crate consumed by all products; Isabelle is a persona profile — additional capabilities gated by the same engine with explicit `privileged_profile` flag logged.
8. **Latency in approval UX.** Slow prompt kills the ack budget. **Mitigation:** `approval_pending` fires synchronously; L1 auto-emits a stall ack if decision pending >800 ms.

## Sequencing

1. **P0 (OSS Preview)** — policy crate with Observer + Assistant presets only; capability coverage for Files (read/draft), Browser (read), Memory, Clipboard, Media; session-scoped audit log viewable in trust center; emergency revoke; hardcoded blocks active. Rust where feasible; a Python shim is acceptable only for the preset-compiler CLI, never on the decision path.
2. **P1 (Pro Phase 0)** — full five-preset ladder, full capability matrix (add Email, Terminal, Integrations), resource-scope editor, temporary grant ladder (action / task / session / persistent), persistent audit log with hash-chain + HMAC integrity.
3. **P2 (Pro Phase 1)** — plan-level `policy_preview` for multi-step chains; risk-class bundling; red-team regression suite integrated into CI; OpenTelemetry spans on every decision.
4. **P3 (Pro Phase 2)** — Custom preset UX fully exposed; per-category emergency revoke; replayable audit history UI contract; Isabelle privileged-profile overlay with explicit `privileged_profile` audit tagging.
5. **P4 (Pro Phase 3+)** — per-capability anomaly detection (ML-optional), exportable audit trails for third-party review, optional policy-as-code DSL if enterprise demand warrants; cross-device grant propagation (sync design from L-sync layer).

## Acceptance criteria

- **Zero-bypass invariant:** 100% of tool / IO / network / memory-write calls in the built product preceded by an `action_request` → `policy_decision` pair in the audit log; CI lint blocks direct executor calls; red-team suite asserts this on every release candidate.
- **Audit-log completeness:** every decision (allow / ask / deny / needs_upgrade) recorded with actor, capability, resource, risk class, preset, persona id, task id, outcome, timestamp, chain-hash.
- **Audit-log integrity:** hash-chain verifies at startup; tampering produces a hard-blocking warning; HMAC key rotated on major version.
- **Approval UX latency:** p95 time from `action_request` emission to `approval_pending` rendered ≤150 ms; p95 auto-decision (no user ask) ≤10 ms.
- **Approval-rate ceiling:** Assistant preset produces ≤1 user-facing approval per 5 user-initiated tasks on a representative task suite (measured, not assumed).
- **Hardcoded-block coverage:** finance / healthcare / password-manager domain families blocked in all presets except explicit Custom override with per-category confirmation; tested per release.
- **Preset-switch correctness:** switching preset revokes session grants incompatible with the new matrix within 100 ms; verified by test.
- **Persona-swap correctness:** swap flushes session ledger atomically before any post-swap action request is evaluated.
- **Emergency revoke:** revoke-all completes ≤500 ms; all in-flight tool calls aborted; event on bus.
- **Red-team suite:** prompt injection, session-grant abuse, bypass-via-chain, and audit-tampering test classes all pass on every release candidate; trust-affecting regressions block release.

## Open decisions for executing agent

- Choice of audit-log storage (SQLite + custom append-only table vs. purpose-built log file with WAL). Recommend SQLite for queryability.
- HMAC key management: single per-install key in OS keychain vs. rotation policy; reconciliation on key loss.
- Whether P0 ships the hash-chain or adds it at P1 (trade-off: P0 scope vs. trust story).
- Whether plan-level `policy_preview` lands at P1 or P2 (UX review dependent).
- Exact TTL defaults for task / session grants (draft: task = until task-end event; session = process lifetime).
- Policy-as-code DSL: confirm deferred to P4+ unless enterprise blocker emerges.

## Reference specs

- file:///C:/Users/dbhav/Projects/aether-planning/12_permissions_autonomy.md
- file:///C:/Users/dbhav/Projects/aether-planning/13_trust_security_redteam.md
- file:///C:/Users/dbhav/Projects/aether-planning/08_system_architecture.md
- file:///C:/Users/dbhav/Projects/aether-planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether-planning/inbox_2026-04-18b/aether_cross_systems_spec.md
