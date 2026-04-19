# Wave 3 — First L5 Policy Logic Slice — Execution Report

**Date:** 2026-04-19
**Mode:** Narrow, real implementation. In-memory backends. Sync evaluator.
**Prerequisites:** Waves 0, 1, 2 (all scaffolded, additive).

---

## 1. Files / directories created or modified

### New — storage

- `packages/storage/migrations/0001_init.sql` — real DDL for L5 policy tables (`policy_grants`, `policy_audit_log` with append-only triggers, `policy_audit_checkpoints`, `cost_counters`) plus `schema_migrations` bookkeeping.
- `packages/storage/src/migrations.rs` — `Migration` struct + `const MIGRATIONS: &[Migration]` populated via `include_str!`. Driver wire-up deferred (see §2).

### Modified — storage

- `packages/storage/src/lib.rs` — `pub mod migrations;` + re-exports (`Migration`, `MIGRATIONS`, `expected_head_id`).

### New — L5

- `packages/l5-policy/src/ledger.rs` — `InMemoryGrantLedger` implementing `GrantLedger` + Wave-3-only helpers (`active_len`, `expire_ttl`, `revoke_all`, `revoke_persona`).
- `packages/l5-policy/src/audit_store.rs` — `InMemoryAuditStore` implementing `AuditStore` + test helpers (`len`, `all`, `count_kind`).
- `packages/l5-policy/src/sink.rs` — `L5EventSink` trait, `InMemorySink` (collecting), `NullSink` (no-op).
- `packages/l5-policy/src/engine.rs` — `DefaultPolicyEngine`, `EngineConfig`, `CapabilityPolicy`, `EngineConfig::wave3_default(...)`.
- `packages/l5-policy/tests/engine_slice.rs` — 10 integration tests mapped to the test matrix (§5).

### Modified — L5

- `packages/l5-policy/src/lib.rs` — added modules and live re-exports (`InMemoryGrantLedger`, `InMemoryAuditStore`, `DefaultPolicyEngine`, `EngineConfig`, `CapabilityPolicy`, `InMemorySink`, `L5EventSink`, `NullSink`).

### Not modified

- `packages/event-bus/` — untouched this wave. Rationale in §2.
- `packages/l5-policy-ts/` — untouched; the Wave 2 hand-written mirror still reflects the stable types.
- Any TS workspace package.
- Any planning doc.
- Any Wave 0/1/2 governance artifact.
- Any legacy Python tree.

---

## 2. Storage driver and bus primitive choices

### 2.1 Storage driver — **rusqlite + bundled** (decision locked, wire-up deferred)

**Decision:** `rusqlite` with the `bundled` feature is the adopted SQLite driver for L5 + L2 persistence. Rationale:
- Single-writer local store matches the Aether model perfectly; sync driver avoids unnecessary async ceremony.
- `bundled` vendors SQLite, eliminating cross-platform native-dep drift (Windows especially).
- `r2d2` / `r2d2_sqlite` is the default connection pool, adequate for a single-process Tauri app.
- `sqlx` remains the alternative; moving to `sqlx` later is a `Store` trait swap.

**Wire-up status:** **deferred to Wave 3.5**. The dev machine has no `rustup` / `cargo` installed (confirmed this session). Adding a native-dep crate without the ability to run `cargo check` would be irresponsible — a single compile-error slip could block every future wave. Instead this wave ships:
- `packages/storage/migrations/0001_init.sql` — real, ready-to-execute SQL.
- `packages/storage/src/migrations.rs` — `Migration` record + `MIGRATIONS` slice populated at compile time via `include_str!`.
- `packages/storage/Cargo.toml` — driver deps intentionally absent. A follow-up of ~15 lines plus a `Store` impl wires rusqlite when `cargo` is available.

When Wave 3.5 runs: add `rusqlite = { workspace = true, features = ["bundled"] }` and `r2d2`, then implement a `SqliteStore` that executes `MIGRATIONS[i].sql` sequentially. The `AuditStore` / `GrantStore` traits in `packages/l5-policy/src/storage_hooks.rs` remain the integration point.

### 2.2 Event bus — `L5EventSink` trait now; tokio broadcast later

**Decision:** L5 publishes through a synchronous `L5EventSink` trait (defined in `l5-policy::sink`). The broadcast-channel-based `aether-event-bus` primitive stays Wave 2-level (envelope types only) until a real asynchronous consumer (Tauri bridge, L7 trust center stream) lands.

**Rationale:**
- L5 `evaluate` is synchronous (L5 interface pack §5).
- The audit-write-before-Allow-returns invariant is trivially preserved by a sync sink; a broadcast channel buys nothing here and adds tokio dependency surface to a synchronous gate.
- Test ergonomics: `InMemorySink::count_where(...)` lets tests assert exact event-family coverage without a runtime.
- When Wave 5/6 introduces the first async consumer, an adapter `BroadcastSink(tokio::sync::broadcast::Sender<L5Event>)` implementing `L5EventSink` adds zero friction.

---

## 3. Evaluator slice

### 3.1 Preset (`EngineConfig::wave3_default`)

Five capabilities exercised, one per decision branch:

| Capability | Mode | Risk | Exercises |
|---|---|---|---|
| `FilesRead` | `Auto` | Low | Allow fast-path; auto-issued session grant |
| `FilesCreate` | `Ask` | Medium | Ask ticket → approval round-trip |
| `FilesEdit` | `Ask` | Medium | same Ask path (covers cross-capability differentiation) |
| `FilesDelete` | `Ask` | High | Ask ticket; used in revoke + DeferToDraft tests |
| `ShellExec` | `Deny` | Critical | `Decision::Deny { reason: ModeDeny }` |

Every other capability (e.g. `BrowserOpen`, `EmailSend`, `RouterEscalateRemote`) falls through to the Decision-1-locked `Decision::NeedsUpgrade { capability_path, suggested_preset: "wave3.operator" }`.

### 3.2 5-stage evaluator (implemented)

Order each `evaluate` call executes:

1. **Re-eval trigger 8 (TTL expiry).** `ledger.expire_ttl(req.emitted_at)` runs before anything else — any grant past its `expires_at` flips to revoked **before** the cover check.
2. **Action-request event emitted.** `L5Event::ActionRequest` published with change-id + seq.
3. **Stage 1 — pre-gates.** If the engine is in a `DegradedMode`, return `PolicyEngineError::Degraded(mode)` immediately. No audit row.
4. **Stage 2 — feature.** Preset lookup. Capability missing → `Decision::NeedsUpgrade(CapabilityPath, suggested_preset)` (Decision 1 top-level variant), audit row, decision event.
5. **Stage 5 (mode fast paths).**
   - `ApprovalMode::Deny` → `Decision::Deny { reason: ModeDeny }` + audit.
   - `ApprovalMode::DraftOnly` → `Decision::DraftOnly { source: DraftSource::System }` + audit (Decision 2).
6. **Stages 3+4 — action / resource / grant cover.** `ledger.covers(cap, resource, persona)` returns `Some(grant_id)` → `Decision::Allow { grant_ref, audit_id }` + audit.
7. **No covering grant, by mode:**
   - `Auto` → write audit, issue a **fresh** session-scoped grant, emit `GrantIssued`, return `Decision::Allow`.
   - `Ask` / `TaskScoped` → create pending ticket, store in engine state, emit `ApprovalPending`, return `Decision::Ask`.

### 3.3 Approval round-trip (`respond_approval`)

- `UserChoice::Allow / AllowScope / AllowTask / AllowSession` → pick the right `GrantDuration`, issue a grant, emit `GrantIssued`, emit `PolicyDecision` with `DecisionKind::Allow`.
- `UserChoice::Deny` → `Decision::Deny { ModeDeny }` + audit (no grant).
- `UserChoice::DeferToDraft` → `Decision::DraftOnly { source: DraftSource::UserChoice }` + audit (Decision 2 locked path).

### 3.4 Emergency revoke

`PolicyEngine::emergency_revoke(EmergencyScope::{All, Category(_), Persona(_)})`:
- `All` / `Category(_)` → `ledger.revoke_all(RevokeReason::EmergencyRevoke)` (Wave 3 simplification — per-category filtering lands Wave 4).
- `Persona(p)` → `ledger.revoke_persona(p, RevokeReason::EmergencyRevoke)`.
- Always emits `L5Event::EmergencyRevokeAll` with a live revoke count.

### 3.5 In-memory grant ledger

`InMemoryGrantLedger` stores `HashMap<GrantId, GrantRow { grant, revoked: Option<RevokeReason> }>` behind a `std::sync::Mutex`. Implements the Wave-2 `GrantLedger` trait plus three inherent helpers:

- `active_len()` — count for test assertions.
- `expire_ttl(now)` — re-eval trigger 8; mutates revoke flag in place.
- `revoke_all(reason)` / `revoke_persona(persona, reason)` — emergency paths.

`covers(...)` semantics (scope matching):
- `ResourceScope::None` pattern ⇒ blanket match.
- `Path` / `Url` ⇒ prefix match.
- `Mailbox` / `Integration` / `CostScope` ⇒ exact equality.
- Kind mismatch ⇒ no match.

### 3.6 In-memory audit store

`InMemoryAuditStore` wraps `Mutex<Vec<AuditRecordEvent>>`. Implements the Wave-2 `AuditStore` trait:
- `append` pushes and returns the id. **This is the only mutation path**, which trivially preserves append-only semantics.
- `query` supports `since` / `until` / `decisions` filters + limit.
- `verify_chain` returns `Ok(())` — hash-chain + HMAC arrive in Wave 4 with the real SQLite writer.

---

## 4. Audit + re-eval behavior

### 4.1 Audit invariant upheld

`DefaultPolicyEngine::write_audit(...)` is called **before** any `Decision::Allow` is constructed or returned. The test `audit_row_is_committed_before_allow_returns` asserts that `audit.len() == 1` at the point the `evaluate` call returns, proving the sync-commit path.

On `AuditStore::append` failure, `write_audit` returns `PolicyEngineError::Internal` and `evaluate` surfaces it — no `Decision::Allow` is ever constructed in that branch. (The specific `DenyReason::AuditWriteFailed` + audit-broken-degraded-mode wire-up lands in Wave 4 when the real SQLite writer can actually fail in realistic ways.)

### 4.2 Re-eval triggers active

- **Trigger 7 — grant revoked / emergency revoke.** `ledger.revoke(...)` marks the row revoked; `ledger.covers` skips revoked rows. Subsequent `evaluate` for the same cap / resource / persona re-enters the Ask path (for Ask-mode caps) or re-issues a fresh grant (for Auto-mode caps). Test: `revoked_grant_is_not_reused`.
- **Trigger 8 — TTL expiry.** `ledger.expire_ttl(now)` runs at the very top of `evaluate`, flipping expired grants to `Revoked(TtlExpired)`. Test: `ttl_expiry_drops_grant_before_next_evaluate`.

Triggers 1–6 (capability differs, resource outside pattern, persona swap, remote escalation, provenance elevation, cost threshold) are **not yet** active in the evaluator — they are Wave 4+ work. The enum `ReEvalTrigger::ALL` still asserts all 8 are declared.

---

## 5. Tests added

File: `packages/l5-policy/tests/engine_slice.rs` (10 tests, ~460 lines).

| Test | Matrix mapping | What it asserts |
|---|---|---|
| `safe_capability_allows_and_issues_session_grant` | complement of L5-T01 | Auto-mode Allow; `GrantIssued` + `AuditRecord` + `PolicyDecision` emitted; one active grant in ledger |
| `second_evaluate_reuses_existing_grant_and_does_not_issue_new` | — | Cover-path short-circuit; no second `GrantIssued` |
| `ask_mode_without_grant_emits_ask_ticket` | **L5-T01** | Ask decision; `ApprovalPending` emitted; audit `Ask` row written |
| `defer_to_draft_resolves_to_draft_only_user_choice` | Decision 2 | `UserChoice::DeferToDraft` → `Decision::DraftOnly { source: UserChoice }`; audit row kind is `DraftOnlyUserChoice` |
| `allow_approval_issues_grant_that_covers_future_evaluates` | — | Full approval round-trip; subsequent evaluate returns Allow via grant |
| `revoked_grant_is_not_reused` | **L5-T02** (slice) | Grant revoke causes next evaluate to re-Ask (Decision 4 trigger 7) |
| `ttl_expiry_drops_grant_before_next_evaluate` | Decision 4 trigger 8 | Pre-seeded expired grant is revoked at the top of `evaluate`; decision is Ask, not Allow |
| `emergency_revoke_clears_all_grants` | **L5-T05** | Two active grants → `emergency_revoke(All)` → `active_len == 0`; `EmergencyRevokeAll` event emitted |
| `capability_outside_preset_returns_needs_upgrade` | Decision 1 | Capability absent from preset → `NeedsUpgrade(CapabilityPath)` top-level; audit row kind is `NeedsUpgrade` |
| `shell_exec_is_mode_denied` | — | Preset-denied capability produces `Decision::Deny { ModeDeny }` + audit |
| `audit_row_is_committed_before_allow_returns` | L5 §5 invariant | `audit.len() == 1` immediately after `evaluate` returns Allow |

Matrix entries **not** yet covered (scoped to later waves): L5-T03 (audit-chain tamper — requires hash chain, Wave 4), L5-T04 (cost threshold — requires BYOK evaluator Stage 0, Wave 4), L5-T06 (persona-scoped precedence — requires L6 integration, Wave 5), L5-T07 (in-place mutation rejected — requires SQLite triggers, Wave 3.5), L5-T08 (10k-grant P99 latency — requires `criterion` bench + real persistence).

### Test runner status

- `cargo test -p aether-l5-policy` — **not run** this session. No `rustup` / `cargo` on the dev machine. The tests compile logically against the types re-exported from `aether_l5_policy`, which match the Rust source of truth. First `cargo check` post-rustup install will be the confirmation gate.
- `pnpm -r --if-present typecheck` — **PASS**. All 3 TS packages still clean. Wave 3 introduced no TS changes.
- Manifest syntax (TOML + JSON + YAML) — **PASS** on all new / modified files.

---

## 6. Planning doc changes

**None.** The locked decisions (1–5) all fit the Rust types exactly as declared in Wave 2. The evaluator slice preset is a concrete choice that sits entirely inside the planning freedom — no doctrine edits required.

Two items were **flagged but not silently resolved** in code comments:
- `DenyReason::AuditWriteFailed` deserves an audit-broken degraded-mode write in Wave 4 (the L5 interface pack names it; today Wave 3 surfaces it via `PolicyEngineError::Internal` on append failure).
- `EmergencyScope::Category(_)` / `Persona(_)` are Wave 4 work; Wave 3 treats them as `All` for safety and documents the simplification in `engine.rs`.

---

## 7. What remains for L5 "v1 complete"

Blocking items for an L5 that can ship behind `apps/desktop/`:

1. **Persistence.** Replace `InMemoryGrantLedger` + `InMemoryAuditStore` with `SqliteStore`-backed impls using the Wave-3 migration. (Wave 3.5 once rustup is installed.)
2. **Audit hash-chain + HMAC.** Write `prev_hash` + `record_hmac` + `key_id`; implement `verify_chain`; wire the OS keyring for the per-install HMAC key. (Wave 4.)
3. **BYOK cost-cap Stage 0.** `CostEvent` → counter update → `cost_threshold_hit` → deny-until-re-arm path with the three Decision-3 admin commands. (Wave 4.)
4. **Privacy-posture gate.** Private-tagged provenance + remote route → `Deny(PrivacyPostureViolation)` unless waiver. (Wave 4.)
5. **Pre-evaluator hardcoded blocks.** `ShellExec` with `rm -rf /` → `Deny(HardcodedBlock)` before preset lookup. (Wave 4.)
6. **Per-category / per-persona emergency revoke.** Drop Wave 3's "treat as All" simplification. (Wave 4.)
7. **Real Tauri IPC handler.** `#[tauri::command]` wrappers in `apps/desktop/src-tauri/`. (Wave 5 together with `apps/desktop/` shell.)
8. **Remaining 6 re-eval triggers.** Capability differs / resource outside pattern / persona swap / remote escalation / provenance elevation / cost threshold — each plugs into `ActionRequest` field checks in Stage 3. (Wave 4.)
9. **`subscribe()` returning a real broadcast stream.** Wire `tokio::sync::broadcast` once a consumer exists. (Wave 5.)
10. **`ts-rs` regen for `packages/l5-policy-ts/`.** Replaces the hand-written mirror. (Wave 5.)
11. **L5 property + red-team tests.** Monotonicity / revocation idempotency / audit-chain integrity / ledger-replay equivalence / deny-all-under-audit-failure. (Wave 4 alongside persistence.)
12. **Perf gate** against L5-T08 (P99 ≤ 200 ms with 10k grants). Needs `criterion` bench. (Wave 4.)

---

## 8. Recommended next session

**Run both in parallel:**

- **Wave 4a (Engine stubs, load-bearing surfaces) — this session already continues into it.** Scaffold `packages/l1-interaction`, `packages/l2-memory`, `packages/l3-presence`, `packages/l4-router`, `packages/l6-persona`, `packages/l7-trust`. Each gets a workspace-integrated Rust crate with traits, core enums, error vocabulary, event-surface references, storage-hook traits where relevant, and smoke tests. No engine logic. This unblocks every layer agent.
- **Wave 3.5 (persistence wire-up) — ~half-day once `rustup` is installed.** Add `rusqlite + bundled` + `r2d2` to `packages/storage`; ship a `SqliteStore` that runs `MIGRATIONS`; swap L5's in-memory backends behind a feature flag (`sqlite` default off for tests, on for integration). Followed immediately by `cargo check --workspace` to validate everything compiles end to end.

**Preferred order:** complete **Wave 4a** (engine stubs) first — all other layer agents can start their first-logic waves in parallel as soon as those crates exist. **Wave 3.5** then runs once you have rustup and can validate the Rust workspace with real tooling.

---

## 9. Commit strategy

This wave is a single logical change set. Recommended:

```bash
cd C:/Users/dbhav/Projects/aether
git add packages/l5-policy/ packages/storage/ WAVE3_EXECUTION_REPORT_2026-04-19.md
git commit -m "feat(l5): [WAVE3] implement first policy logic slice"
git push origin dev
```

No `planning/` edits to stage. `packages/event-bus/` untouched. No TS changes.

---

## 10. Roadmap graphic

```text
AETHER ROADMAP STATUS — AFTER WAVE 3 (2026-04-19)

FOUNDATION / DOCTRINE
[██████████] 100%  Doctrine locked (01_product_doctrine.md)
[██████████] 100%  7-layer model aligned (orchestration map)
[██████████] 100%  5 control-plane decisions locked (DECISION_LOCK_PASS_2026-04-18c)

DESIGN / PREP
[██████████] 100%  L1–L7 system designs
[██████████] 100%  L1–L7 interface packs
[██████████] 100%  Event contracts master
[██████████] 100%  SQLite schema pack (DDL drafted)
[██████████] 100%  Test matrix master
[██████████] 100%  Implementation handoff notes

REPO / INFRA
[██████████] 100%  Wave 0 — monorepo assimilation
[██████████] 100%  Wave 1 — workspace + shared infra + governance
[██████████] 100%  Wave 2 — L5 scaffold (types, traits, 16-command IPC surface)

L5 — POLICY ENGINE
[██████████] 100%  Wave 2 scaffold
[████████░░]  80%  Wave 3 first logic slice  ← you are here
                   - InMemoryGrantLedger + InMemoryAuditStore wired
                   - 5-stage evaluator (narrow capability set)
                   - Decisions 1–5 honored (NeedsUpgrade, DraftOnly source,
                     3 admin commands shaped, 8 re-eval triggers declared,
                     BYOK re-arm shape)
                   - Re-eval triggers 7 (revoke) + 8 (TTL) active
                   - 10 integration tests mapped to test matrix
[░░░░░░░░░░]   0%  Wave 3.5 — SQLite driver wire-up (rusqlite+bundled)
[░░░░░░░░░░]   0%  Wave 4 — audit hash-chain + HMAC + keyring
[░░░░░░░░░░]   0%  Wave 4 — BYOK cost-cap Stage 0
[░░░░░░░░░░]   0%  Wave 4 — remaining 6 re-eval triggers
[░░░░░░░░░░]   0%  Wave 5 — Tauri IPC handler wire-up

OTHER ENGINES
[░░░░░░░░░░]   0%  L1 interaction / timing (stub wave pending)
[░░░░░░░░░░]   0%  L2 memory kernel
[░░░░░░░░░░]   0%  L3 presence scheduler
[░░░░░░░░░░]   0%  L4 model router
[░░░░░░░░░░]   0%  L6 persona compiler
[░░░░░░░░░░]   0%  L7 trust UX backend

PRODUCT INTEGRATION
[░░░░░░░░░░]   0%  apps/desktop (Tauri shell, OSS Preview + Pro flags)
[░░░░░░░░░░]   0%  apps/guest (Cloudflare Worker + Groq endpoint)
[░░░░░░░░░░]   0%  apps/docs-site
[░░░░░░░░░░]   0%  End-to-end onboarding → first-turn flow

TOOLING / LINTS
[████░░░░░░]  40%  tools/lint-layer-boundaries (strategy docs + deny.toml stub)
[████░░░░░░]  40%  tools/lint-policy-bypass (rules doc; linter prototype pending)
[██░░░░░░░░]  20%  tools/lint-private-asset-leak (strategy only)
[██░░░░░░░░]  20%  tools/ts-bindings-gen (placeholder)

HIGH-CONFIDENCE NEXT 2 SESSIONS
  1. Wave 4a — early engine stubs for L1/L2/L3/L4/L6/L7 (coordinator-driven,
     unblocks every other layer agent)
  2. Wave 3.5 — rusqlite wire-up + first real cargo check across the workspace
```
