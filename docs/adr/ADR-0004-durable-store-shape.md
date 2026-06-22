# ADR-0004: Durable-domain store shape — SQLite per-domain log tables

- **Status:** Accepted
- **Date:** 2026-04-24
- **Deciders:** Don (delegated expert call to Claude — "you're the captain, keep going"). Session accepts the decision and executes in the same run per Milestone 1's ADR-before-code invariant.
- **Supersedes:** nothing.
- **Superseded by:** nothing.
- **Related:** `docs/adr/ADR-0001-memory-domain-reconciliation.md` (six-domain taxonomy), `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md` (embed eligibility — Durable/Projects/Artifacts), `docs/MEMORY-V2-ARCHITECTURE.md` §§1–5, `ROADMAP_2026-04-24_MILESTONE_2.md` (Milestone 2 Run 1 target), `HANDOFF_2026-04-24_M2_MINI_RUN_0.md` (reserved decisions #M2-04 and #M2-05).

## Context

Five subsystems are rot-guarded and Memory V2 has embeddings wired — but only the **Session** domain has a backing store. Per `HANDOFF_2026-04-23_RUN_1_PLUS_2.md` §4 C (Memory V2 known limitation), every write regardless of declared domain today funnels through `apps/desktop/src-tauri/src/memory_service.rs::perform_memory_write` into the single `SessionMemoryStore`. The `domain` parameter influences policy evaluation, telemetry, audit scope, and embedding eligibility — but the persisted row carries no domain.

This matters because:

1. **Retention sweep** (Memory V2 step 5) walks `MemoryDomain::ALL` and trace-skips five of six domains with no backing store. The `retention_days.durable = 30` policy value is therefore inert.
2. **Embeddings** (Memory V2 step 6) pair with memory rows by `memory_id`. Today the only rows that exist are Session rows — but Session is deliberately NOT embed-eligible (ADR-0002 §5). Net effect: the embedding pipeline produces zero rows in practice, regardless of the `embeddings.enabled` flag.
3. **Retrieval wiring** (Milestone 2 Run 2, next session) needs rows to query. If Durable has no store, `EmbeddingStore::query_nearest` on Durable returns `Ok(vec![])` for every query.

The domain-typed durable-store gap is the single biggest blocker on Milestone 2's theme ("Aether becomes retrieval-aware and user-facing"). Closing it unlocks Run 2.

Three candidate shapes were considered:

- **(a) Unified table with `domain` column.** One `domain_log(domain, scope_id, sequence, role, content, timestamp_ms)` table serves all non-Session domains. Pros: one migration, one SQL shape. Cons: every query needs a domain filter; `SessionMemoryStore` trait doesn't know about domains — adding domain to every call changes the trait and breaks existing call sites.
- **(b) Per-domain tables with a parameterized `SqliteSessionMemoryStore`.** New migration creates a table per non-Session domain with the same shape as `conversation_log`. `SqliteSessionMemoryStore::with_table(conn, config, retention, table_name)` accepts a constant table name; shell instantiates one store per domain. Pros: no trait churn, drop-in reuse of the existing `SessionMemoryStore` surface, per-domain retention tables are independent, inspection via `sqlite3` CLI is trivial. Cons: migrations balloon if we materialize all five non-Session domains up front.
- **(c) Per-domain JSONL files mirroring the embedding flat-file store.** Pros: trivial to inspect, zero migrations. Cons: rewrite-on-every-mutation is linear-bad for a domain (Durable) that's designed to grow; retention sweep needs to iterate-and-rewrite instead of `DELETE WHERE timestamp < ?`; dual-storage mental model (SQLite for Session, JSONL for others) adds cognitive cost.

## Decisions

### 1. Durable store shape: SQLite per-domain log table (Option b).

- New migration `packages/storage/migrations/0005_durable_log.sql` creates a `durable_log` table mirroring the `conversation_log` shape from `0004_conversation_log.sql`.
- `packages/l2-memory/src/sqlite_session.rs::SqliteSessionMemoryStore` gains a `with_table(conn, config, retention, table_name)` constructor. The existing `::new(conn, config)` remains a thin wrapper that passes `"conversation_log"` as the table name (preserves existing call sites and tests).
- All SQL inside `SqliteSessionMemoryStore` is re-templated to consume `self.table_name`; no table name is hard-coded in queries.
- `DurableSessionStore::open_with_table(path, table_name)` convenience that mirrors the existing opener.

Rationale: reusing the `SessionMemoryStore` trait lets the shell wire a second store with zero new surface area, and the existing tests (16 SQLite session tests) validate every code path the parameterized store inherits. No trait churn, no new capability, no new audit shape. The trade — multiple tables per domain — is a migration-file cost, not a runtime cost.

### 2. Scope this run to Durable only; defer Projects/Artifacts to a later run.

- Migration `0005_durable_log.sql` creates **only** `durable_log`. It does not pre-materialize `projects_log` / `artifacts_log`.
- Shell wires a second `SqliteSessionMemoryStore` for `MemoryDomain::Durable`. `MemoryDomain::Projects` and `MemoryDomain::Artifacts` writes remain in the Session store for now — documented limitation, unchanged from today.
- Facts and Preferences domains also defer (no consumer yet; introducing shape speculatively is premature abstraction).
- Future `ADR-0005` handles Projects/Artifacts when they have a real consumer (likely driven by Milestone 2 Run 6 Memory tab polish or a later phase).

Rationale: Milestone 2 Run 2 (Retrieval Wiring) needs Durable specifically — that is where cross-session conversational recall lives. Projects/Artifacts are a separate UX surface (pinning + notes) that hasn't shipped its user-facing write path yet. Shipping their stores before their UX exists would introduce dead code. This resolves reserved decision **#M2-05** (defer).

### 3. Write routing: shell owns a `DomainStoreRegistry`.

- New struct in `apps/desktop/src-tauri/src/` keyed on `MemoryDomain` → `Arc<dyn SessionMemoryStore>`. Today holds two entries (Session, Durable); extensible for ADR-0005.
- `perform_memory_write` resolves the target store from the registry. If the domain has no store, it falls back to Session with a `warn!` — matches the existing known limitation and keeps the gap debuggable until ADR-0005.
- `perform_memory_forget` / `memory_forget_item` / `memory_edit` / `memory_read` paths all route through the registry.

### 4. Durable = cross-session rolling log, keyed by profile id.

- Today's shell does not carry a persisted "profile id" separate from session id. Durable's store uses the constant `"durable"` as the session_id in every row (one lane per profile; the profile surface is single-profile today). Schema is the same as `conversation_log`; the `session_id` column becomes a degenerate lane identifier.
- Implication: `memory_forget(Durable, "durable")` clears the whole Durable log; `memory_forget_item(Durable, "durable", seq)` targets one row. `memory_forget(Durable, <non-durable-session>)` returns `NotFound` (matches existing semantics for per-item misses).
- A future per-persona or multi-profile release can introduce real `profile_id` scoping via a second migration; today's single-user reality doesn't need it.

Rationale: the simplest thing that could possibly work. No new API shape, no new column, no premature multi-profile work. When Aether grows a second profile, this becomes a one-line change (pass profile_id where `"durable"` is hardcoded).

### 5. Dual-write model: explicit Durable writes land only in the Durable store.

- Writes where the caller passes `MemoryDomain::Durable` land in the Durable store only, not in Session. Same for every other non-Session domain once their stores ship.
- Writes where the caller passes `MemoryDomain::Session` land in the Session store only.
- A future slice may add a Session → Durable migration/mirror on session close (auto-promotion), but this ADR does NOT build it. Current callers that want durable persistence pass `MemoryDomain::Durable` explicitly.

Rationale: avoids the dual-write I/O cost, keeps semantics mechanical. Dual-write is reversible if a product need emerges; silent auto-mirroring is harder to undo if it turns out to misclassify.

### 6. Retention sweep extension.

- `apps/desktop/src-tauri/src/retention.rs` (the existing sweep owner) iterates `MemoryDomain::ALL` and, for each domain with a registry entry, calls `prune_before(ts_now - retention_days * 86_400_000)` with the TTL from `memory.json::retention_days`. `retention_days = null` still means "keep until forgotten" — no prune call is issued.
- Domains without a registry entry continue to trace-skip (unchanged from today).
- Aggregated `memory_forgotten` telemetry extends to Durable: one row per domain per sweep when >0 rows evicted (Decision #56 continues to apply).
- L5 audit: one `MemoryForget` audit row per sweep invocation (Decision #57 continues to apply). No new capability variant.

### 7. Embedding forget cascade.

- `memory_forget_item(Durable, session_id, seq)` calls `EmbeddingStore::delete(MemoryDomain::Durable, &MemoryId::new(&memory_id))` after the primary remove succeeds. Best-effort: failure warns, doesn't block.
- `memory_forget(Durable, session_id)` does NOT cascade today — clearing the whole lane would need an iterate-and-delete over every embedding row, and the flat-file store doesn't expose a `delete_all_for_domain`. Captured as a known limitation with a `// TODO: ADR-0005 or follow-up` comment; surfaces cleanly in the shell's test that already exercises the pattern.
- Embeddings on Projects/Artifacts: unchanged (unreachable — no store to forget from).

### 8. No new L5 capability.

- The existing `MemoryWrite`, `MemoryRead`, `MemoryForget`, `MemoryEmbed`, `MemoryEdit` capabilities are sufficient. `ResourceScope` already carries the domain label. Adding `DurableMemoryWrite` etc. would duplicate the gate surface without adding useful distinction.

This resolves reserved decision **#M2-04** (store shape).

## Consequences

- **New migration + two runtime stores.** Shell DB file gains one table; the `open_with_migrations` entry point picks up `0005_durable_log.sql` on next start. Existing users of the app lose nothing; the new table starts empty.
- **`cargo test -p aether-l2-memory --features "sqlite-backend embeddings"` grows** by ~6–10 tests covering the parameterized constructor and per-table isolation.
- **Shell tests grow** by ~8–12 covering: Durable write lands in the right table, Session write lands in the right table, Durable recall returns only Durable rows, retention sweep prunes Durable-age rows without touching Session, embedding forget cascade on per-item Durable forget.
- **`docs/MEMORY-V2-ARCHITECTURE.md` §10** step 5 (retention sweep) gains a "coverage: Session + Durable" note; the §3 `retention_days.durable = 30` field is no longer inert.
- **Projects/Artifacts routing** remains on the Session store. Documented in this ADR and in the Run 1 execution report; ADR-0005 in a future run closes that gap.
- **Rot-guard anchors** on `tools/lint-memory-doc/check.py` gain entries for the new symbols (migration file, `with_table` constructor, Durable store wiring) to prevent silent drift.

## Rejected alternatives

- **Option (a) unified domain column.** Rejected: trait churn on `SessionMemoryStore`, downstream call-site changes across memory_service, retention scheduler, and tests. Too much coupling change for one run.
- **Option (c) JSONL flat-file.** Rejected: linear rewrite cost contradicts the "Durable grows unbounded" premise. Consistent storage mental model (SQLite for everything rows, flat-file for embeddings only) is cheaper to reason about.
- **Ship Projects/Artifacts stores speculatively in this run.** Rejected: dead code until a UX consumer exists. Follow the additive-by-default doctrine.
- **Introduce a real `profile_id` column.** Rejected: single-profile reality today; ADR-able when multi-profile ships.
- **Auto-mirror Session writes to Durable on session close.** Rejected: silent data duplication is harder to back out than explicit dual-write paths. Defer until a product need justifies it.

## Verification (Run 1 close checklist)

- `packages/storage/migrations/0005_durable_log.sql` exists; `aether-storage` tests include a migration-runs-clean test if one was in the previous pattern.
- `SqliteSessionMemoryStore::with_table` compiles, is documented, and is covered by at least one per-table-isolation test.
- `DomainStoreRegistry` (or equivalent shell-side routing) exists and is used by every `perform_memory_*` path.
- `memory_write(MemoryDomain::Durable, ...)` persists to `durable_log`, not `conversation_log`, verified by a shell test that inspects the SQLite tables directly via `rusqlite::Connection::query_row`.
- Retention sweep test covers: Durable row older than 30 days evicted, Session row of same age preserved, aggregated `memory_forgotten` telemetry emitted for Durable only when >0 rows evicted.
- Embedding forget cascade test covers: per-item Durable forget removes the paired embedding row; Session-lane forget does NOT cascade (session is not embed-eligible).
- `cargo fmt --all -- --check`, `cargo check --workspace`, `cargo test --workspace`, `python tools/lint-memory-doc/check.py`, `apps/desktop && pnpm test` — all green.
- `docs/MEMORY-V2-ARCHITECTURE.md` §§5, 10 updated to reflect the coverage change.

## Notes

This ADR is deliberately narrow. It ships Durable because Milestone 2 Run 2 needs it; it defers Projects/Artifacts because speculative shipping violates additive-by-default. ADR-0005 will close the remaining gap when a UX consumer appears (Memory tab polish in Run 6 is the likely driver).

The pattern established here — per-domain tables with a parameterized store constructor — is the template ADR-0005 will extend. Future domains are two-line migrations plus a registry entry; no structural churn.
