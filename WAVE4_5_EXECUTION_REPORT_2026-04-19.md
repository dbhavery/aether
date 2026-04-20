# Wave 4.5 — L5 Durable Persistence — Execution Report

**Date:** 2026-04-19
**Mode:** Additive. Opt-in via cargo feature. Default build unchanged.
**Prerequisites:** Waves 0–4, Wave 3.5 storage substrate, Wave 4.1
layer-boundary enforcement — all committed on `dev`.

---

## 1. Scope

Wave 4.5 introduces optional durable persistence for the L5 policy
engine. Specifically:

- New SQL migration `0002_audit_chain.sql` extending the L5 schema with
  payload columns and hash-chain groundwork.
- New SQLite-backed `GrantLedger` and `AuditStore` implementations,
  compiled only when the `sqlite-backend` cargo feature on
  `aether-l5-policy` is enabled.
- A small trait refactor allowing `DefaultPolicyEngine` to accept either
  the in-memory or SQLite-backed backends through trait objects.
- Contributor-facing docs (README + ROADMAP) updated to describe the two
  modes honestly.

Explicitly out of scope:

- Flipping the default L5 backend from in-memory to SQLite. The feature
  stays opt-in; the preview continues to default to the safe, simple,
  process-local path.
- Hash-chain + HMAC row sealing. 0002 lays the groundwork (chain-head
  singleton + `key_id` column) but no chaining code runs yet.
- Cost-counter durability (BYOK).
- Any change to the `PolicyEngine` public trait or IPC surface.

---

## 2. Schema and migration changes

### New file: `packages/storage/migrations/0002_audit_chain.sql`

Additive only — no destructive changes to 0001:

- `ALTER TABLE policy_grants ADD COLUMN payload TEXT` — nullable JSON
  column carrying the full Rust `Grant` struct. The Wave 4.5 SQLite
  ledger treats this as the canonical form and uses 0001's other
  columns for query-path indexing.
- `ALTER TABLE policy_audit_log ADD COLUMN key_id TEXT` — HMAC signing
  key identifier; indexable when the sealing wave lands.
- `ALTER TABLE policy_audit_log ADD COLUMN privileged_profile INTEGER NOT NULL DEFAULT 0`
  — per-row flag so audit queries can split Isabelle-profile rows out.
- `CREATE INDEX idx_policy_audit_key_id ON policy_audit_log(key_id)`.
- `CREATE TABLE policy_audit_chain_head(id INTEGER PRIMARY KEY CHECK (id = 1), head_audit_id TEXT, head_hash BLOB, updated_at TEXT NOT NULL)`
  — singleton chain-tip row, seeded with `NULL` values. Future hash-
  chain wave does `UPDATE` rather than `INSERT` (no race).
- `INSERT OR IGNORE INTO schema_migrations ...` — bookkeeping.

### `packages/storage/src/migrations.rs`

- Added `MIGRATION_0002_AUDIT_CHAIN` referring to the new SQL file via
  `include_str!`.
- Extended `MIGRATIONS` slice to `[0001_INIT, 0002_AUDIT_CHAIN]`.
- Updated `head_id_matches_last_entry` test to expect `"0002_audit_chain"`.

The existing `aether-storage` unit + integration tests (8 total) pass
unchanged: the migration runner picks up 0002 automatically, a cold open
now applies both, and a warm open still records "0 applied".

---

## 3. Storage-layer type changes

### `packages/storage/src/lib.rs`

- Added `pub use rusqlite;` — re-exports the driver so downstream crates
  can use `Connection` without adding their own `rusqlite` dependency.
  This keeps `tools/lint-layer-boundaries/check.py` happy (L5 → storage
  is an allowed edge; L5 → external crates ignored).
- No new helper types. The existing `open_with_migrations` +
  `OpenOutcome` from Wave 3.5 are sufficient.

No changes to the migration runner or the `StorageLayout` type.

---

## 4. L5 changes

### `packages/l5-policy/src/grants.rs` — `GrantLedger` trait extension

Added four new methods **with default implementations**:

- `fn active_count(&self) -> u64`
- `fn expire_ttl(&self, now: MonotonicTimestamp) -> Vec<GrantId>`
- `fn revoke_all(&self, reason: RevokeReason) -> u32`
- `fn revoke_persona(&self, persona: &PersonaId, reason: RevokeReason) -> u32`

The defaults are implemented on top of the trait's existing four required
methods (`snapshot` + `issue` + `revoke` + `covers`), so any implementor
automatically inherits working — if non-optimal — versions. Specialized
backends may override: the in-memory ledger keeps its efficient variants
on the concrete type; `SqliteGrantLedger` uses the defaults.

This is the minimal change needed to let `DefaultPolicyEngine` call
these methods through a trait object without requiring every backend to
re-implement them. No existing callers broke.

### `packages/l5-policy/src/engine.rs` — `DefaultPolicyEngine` refactor

- `ledger: Arc<InMemoryGrantLedger>` → `ledger: Arc<dyn GrantLedger>`
- `audit: Arc<InMemoryAuditStore>` → `audit: Arc<dyn AuditStore>`
- `DefaultPolicyEngine::new(...)` signature updated accordingly
- `ledger()` / `audit()` accessor return types updated
- Removed two now-unused imports

All 18 existing L5 tests pass unchanged thanks to Rust's automatic
`Arc<T> → Arc<dyn Trait>` coercion at function-argument sites. No test
code needed to change.

### `packages/l5-policy/src/sqlite_backends.rs` — new, feature-gated

The module is compiled only under `#[cfg(feature = "sqlite-backend")]`.
It exposes three public types:

- `SqliteGrantLedger` — implements `GrantLedger`. Holds
  `Arc<Mutex<Connection>>`; serializes `Grant` as JSON into the new
  `payload` column while populating `grant_id`, `actor_persona`,
  `capability`, `resource_scope`, `approval_mode`, `duration_kind`,
  `duration_param`, `issued_at`, `expires_at`, `revoked_at`,
  `revoked_reason` for future query-path work. Reads via
  `SELECT payload` + Rust-side deserialize.
- `SqliteAuditStore` — implements `AuditStore`. Writes the full
  `AuditRecordEvent` as JSON into `payload`, plus granular columns
  (`audit_id`, `timestamp`, `actor_persona`, `capability`, `resource`,
  `decision`, `change_id`, `prev_hash`, `record_hmac`, `key_id`,
  `privileged_profile`). Relies on 0001's `policy_audit_log_no_update`
  and `policy_audit_log_no_delete` triggers for tamper resistance.
- `DurableBackends` — convenience builder. `DurableBackends::open(path)`
  calls `aether_storage::open_with_migrations`, wraps the connection in
  `Arc<Mutex<_>>`, and returns ledger + audit sharing the single
  connection. This enforces SQLite's single-writer invariant inside
  L5: both backends serialize on the same mutex.

`ResourceScope` coverage semantics are duplicated from
`InMemoryGrantLedger` (`None` is blanket; `Path` / `Url` are prefix;
`Mailbox` / `Integration` / `CostScope` are exact).

### `packages/l5-policy/Cargo.toml` + `src/lib.rs`

- New `[features]` block: `default = []`, `sqlite-backend = []`. No
  extra direct dep — rusqlite comes transitively via `aether-storage`.
- `tempfile` added as a dev-dep for the new integration tests.
- `lib.rs` adds `#[cfg(feature = "sqlite-backend")] pub mod sqlite_backends;`
  and re-exports `DurableBackends`, `SqliteGrantLedger`,
  `SqliteAuditStore` under the same cfg.

---

## 5. Known limitations (explicit)

Documented in `sqlite_backends.rs` module docs and repeated here for
visibility:

1. **`verify_chain` is a stub.** Returns `Ok(())` unconditionally. The
   0001 append-only triggers still reject `UPDATE` / `DELETE`, which
   gives a weak tamper guarantee equivalent to the in-memory store's
   `Vec`-only push surface. Real hash-chain + HMAC verification is a
   separate wave gated on OS-keyring-backed key rotation.
2. **`covers` filters in Rust.** The SqliteGrantLedger fetches all
   active grants for the `(persona, capability)` pair, then checks
   `ResourceScope` coverage in Rust. Correct for the preview's expected
   grant counts (tens to low hundreds). A future wave can push prefix /
   exact scope checks into SQL.
3. **`snapshot` / `query` filters in Rust.** `capability`, `persona`,
   `decisions`, and time-window filtering happen after a broad `SELECT`.
   Again correct, not optimal at scale.
4. **No cost-counter SQLite backing.** `CostCounterStore` remains
   whatever in-memory type L5 uses; BYOK caps are still session-local.
5. **Audit-chain groundwork, not chaining.** 0002 adds the `key_id`
   column and the `policy_audit_chain_head` singleton, but neither is
   populated by Wave 4.5 code. The column values will be filled in
   when sealing lands.
6. **Single connection, single Mutex.** Matches SQLite's single-writer
   model and is fine for a single-process Tauri app. An `r2d2` pool is
   not set up yet.

---

## 6. How to enable durable mode

### Cargo feature

```toml
# Downstream crate's Cargo.toml
[dependencies]
aether-l5-policy = { path = "../l5-policy", features = ["sqlite-backend"] }
```

### Code

```rust
use aether_l5_policy::{
    DefaultPolicyEngine, DurableBackends, EngineConfig, InMemorySink, PersonaId,
};
use std::sync::Arc;

let persona = PersonaId("aurora".into());
let backends = DurableBackends::open("./aether.db")?;
let engine = DefaultPolicyEngine::new(
    EngineConfig::wave3_default(persona),
    backends.ledger.clone(),
    backends.audit.clone(),
    Arc::new(InMemorySink::new()),
);
```

### Default (in-memory) mode stays unchanged

```rust
use aether_l5_policy::{DefaultPolicyEngine, EngineConfig, InMemoryAuditStore,
                       InMemoryGrantLedger, InMemorySink};
use std::sync::Arc;

let engine = DefaultPolicyEngine::new(
    EngineConfig::wave3_default(persona),
    Arc::new(InMemoryGrantLedger::new()),
    Arc::new(InMemoryAuditStore::new()),
    Arc::new(InMemorySink::new()),
);
```

Both constructors have the same shape — only the backend type differs.

---

## 7. Tests and checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | green |
| `cargo check --workspace` | green |
| `cargo check -p aether-l5-policy --features sqlite-backend --all-targets` | green |
| `cargo test --workspace` | green (default feature set) |
| `cargo test -p aether-storage` | green (5 unit + 3 integration) |
| `cargo test -p aether-l5-policy` | green (18 tests, in-memory) |
| `cargo test -p aether-l5-policy --features sqlite-backend` | green (18 existing + 7 smoke + 5 new SQLite = 30) |
| `python tools/lint-layer-boundaries/check.py` | green (0 violations) |

### New tests — `packages/l5-policy/tests/sqlite_backends.rs`

5 integration tests, all gated on `#[cfg(feature = "sqlite-backend")]`:

1. `grant_survives_a_process_restart` — issue a grant, drop the
   backends, reopen the DB, confirm the grant is still active and
   `covers()` still reports it. The single load-bearing guarantee of
   Wave 4.5.
2. `revoke_persists_across_restart` — revoke a grant, reopen, confirm
   `active_only` snapshot excludes it but historical snapshot still
   includes it, and `covers()` returns `None`.
3. `audit_rows_survive_restart_and_filter_by_time_window` — append two
   rows at different timestamps, reopen, confirm `AuditFilter { since }`
   filters correctly. Also calls `verify_chain()` to confirm the stub
   path is wired.
4. `sqlite_audit_store_cannot_delete_rows` — proves the 0001
   append-only trigger fires when a DELETE is issued through the shared
   connection, even when the caller holds a `SqliteAuditStore`. Inherited
   guarantee, not a new one, but explicitly tested.
5. `engine_accepts_sqlite_backends_and_evaluates` — constructs a
   `DefaultPolicyEngine` with the SQLite trait objects and runs
   `evaluate()` end-to-end. Proves the Wave 4.5 engine refactor
   successfully generalized beyond the concrete in-memory types.

---

## 8. Boundary considerations

`tools/lint-layer-boundaries/check.py` was run after the refactor and
reports **0 violations**. No updates to the `ALLOWED` table were needed:

- `aether-l5-policy`'s allowed targets remain `{event-bus, storage, telemetry}`.
- Adding `sqlite_backends.rs` uses only `aether_storage::rusqlite::Connection`
  and internal L5 types — no new workspace edge.
- Re-exporting `rusqlite` from `aether-storage` does not create a new
  intra-workspace edge (rusqlite is an external crate).

The `sqlite-backend` feature is additive; disabling it produces a build
with strictly fewer symbols, not different ones.

---

## 9. Updated L5 persistence status summary

| Mode | Availability | Persistence | Notes |
|---|---|---|---|
| In-memory (default) | Always | None — state lost on process exit | Fast, zero setup. Use for Wave 3 behavior. |
| SQLite (`sqlite-backend`) | Opt-in cargo feature | Durable via `aether.db` | `DurableBackends::open(path)` is the intended constructor. `verify_chain` stubbed; row sealing future work. |

---

## 10. Recommended next session

**First engine first-logic slice — L1 turn FSM OR L4 provider adapter.**

Either choice unlocks a visible end-to-end path — L1's turn state
machine gives us a real "user speaks → acknowledge → respond" trace,
while L4's provider adapter demonstrates a remote call actually going
through the L5 gate. The Wave 4.5 durable path means that whichever is
chosen can be exercised with both persistence modes without rewriting
tests.

Scope suggestion for the next brief:

- Pick L1 or L4 (not both).
- First-logic slice only: enough to produce a non-trivial trace through
  the existing events + L5 gate, not a full implementation.
- A dated `WAVE*_EXECUTION_REPORT_*.md` alongside.
- Don't touch L5 durable persistence further in that wave; leave it
  bedded in.

If hash-chain / HMAC sealing is the higher priority (e.g., ahead of
any audit-export feature), that can substitute as the next wave — see
ROADMAP §3.
