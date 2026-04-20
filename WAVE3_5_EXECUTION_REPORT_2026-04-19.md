# Wave 3.5 — SQLite Storage Substrate — Execution Report

**Date:** 2026-04-19
**Mode:** Narrow Path 1 — substrate only, no L5 behavioral change.
**Prerequisites:** Waves 0, 1, 2, 3, 4 all committed on `dev`.

---

## 1. Scope (narrow, explicit)

Wave 3.5's real deliverable is **the SQLite substrate**, not durable L5
persistence. Concretely:

- Add `rusqlite` (with the `bundled` feature) to `packages/storage/`.
- Implement a single, minimal entry point (`open_with_migrations`) that
  opens or creates a database, applies every entry in the drafted
  `MIGRATIONS` slice that has not yet been recorded, and returns a live
  connection.
- Prove the migration runner is real with an integration test that opens a
  real SQLite file and asserts the expected tables exist.

Explicitly **out of scope** for this wave:

- Swapping L5's `InMemoryGrantLedger` / `InMemoryAuditStore` for
  SQLite-backed implementations. L5 persistence behavior is unchanged.
- Hash-chain + HMAC triggers for `policy_audit_log` (migration
  `0002_audit_chain.sql` is future work).
- A `Store` trait abstraction over the driver choice.

Scoping this wave narrowly protects L5's 18 passing tests from accidental
behavior change while the substrate beneath it matures.

---

## 2. Toolchain state

| Component | State |
|---|---|
| `rustup` | installed |
| `rustc` | `1.95.0 (59807616e 2026-04-14)` |
| `cargo` | `1.95.0 (f2d3ce0bd 2026-03-21)` |
| `rust-toolchain.toml` | `channel = "stable"`, components `rustfmt`, `clippy` |
| `cargo check --workspace` | green |
| `cargo test --workspace` | green |

The toolchain was available on the primary dev machine this session; the
Wave 3 deferral note ("no `rustup` installed") is now resolved.

---

## 3. Files created or modified

### New

- `packages/storage/src/db.rs` — `open_with_migrations`, `OpenOutcome`,
  `OpenError`, plus private helpers `apply_pragmas`,
  `run_pending_migrations`, and one unit test that rejects a downgrade
  scenario (database recorded a migration the binary doesn't know about).
- `packages/storage/tests/migration_runs.rs` — three integration tests:
  - `cold_open_creates_all_policy_tables` — opens a fresh DB, asserts every
    table enumerated in `0001_init.sql` exists (`policy_grants`,
    `policy_audit_log`, `policy_audit_checkpoints`, `cost_counters`,
    `schema_migrations`).
  - `audit_log_rejects_delete` — inserts a row into `policy_audit_log`
    directly, then asserts `DELETE` is rejected by the append-only trigger.
    This is the load-bearing audit invariant from the planning corpus.
  - `warm_open_is_idempotent` — opens, drops, reopens; asserts
    `outcome.applied.is_empty()` on the second open, and asserts
    `schema_migrations` head matches `expected_head_id()`.

### Modified

- `Cargo.toml` (workspace) — added `rusqlite = { version = "0.31",
  features = ["bundled"] }` and `tempfile = "3"` to
  `[workspace.dependencies]`. Also normalized the workspace license to
  `MIT` (already committed uncommitted in the working tree — see §7).
- `packages/storage/Cargo.toml` — pulled `rusqlite` via `workspace = true`
  from `[dependencies]`; added `tempfile` as a `[dev-dependencies]` entry
  for the integration tests. Removed the Wave-1 "TODO(wave-2): add
  rusqlite" comment block now that it is resolved.
- `packages/storage/src/lib.rs` — added `pub mod db;`, re-exported
  `open_with_migrations`, `OpenError`, and `OpenOutcome` from the crate
  root. Replaced the old `TODO(wave-2)` block with a `// Wave 3.5 landed
  the substrate:` block describing what's in and what's still deferred.

### Pre-existing bug surfaced and fixed

- `packages/media-engine/Cargo.toml` — `cargo test --workspace` surfaced a
  missing `serde_json` dependency used by the crate's existing
  `stt_chunk_is_serializable` unit test. Added `serde_json = { workspace
  = true }` under `[dev-dependencies]`. Orthogonal to Wave 3.5, but
  required for the "workspace tests green" acceptance bar.

### Not modified (intentional)

- `packages/l5-policy/` — no change. L5 still uses `InMemoryGrantLedger`
  and `InMemoryAuditStore`. Flipping the backends is the next L5 wave.
- `packages/storage/migrations/0001_init.sql` — already real DDL from
  Wave 3; this wave only added the runner that executes it.
- `packages/storage/src/migrations.rs` — already defined `Migration` +
  `MIGRATIONS`; no change needed.

---

## 4. Behavior spec — `open_with_migrations`

Signature:

```rust
pub fn open_with_migrations(path: impl AsRef<Path>) -> Result<OpenOutcome, OpenError>;
```

Pipeline:

1. `Connection::open(path)` — creates the file if it doesn't exist.
2. **Pragmas** applied unconditionally on every open:
   - `journal_mode = WAL`
   - `synchronous  = NORMAL`
   - `foreign_keys = ON`
   - `temp_store   = MEMORY`
   - `busy_timeout = 5000`
   Source: header comment in `migrations/0001_init.sql`.
3. **Migration runner** (`run_pending_migrations`):
   a. `CREATE TABLE IF NOT EXISTS schema_migrations (id TEXT PK, applied_at
      TEXT NOT NULL)` — bootstraps the bookkeeping table so a cold open can
      proceed.
   b. `SELECT id FROM schema_migrations ORDER BY id ASC` — read recorded
      ids.
   c. Verify the recorded prefix matches the binary `MIGRATIONS` slice
      order-for-order. Mismatch or unknown-id returns a typed error; the
      runner never silently skips.
   d. For each migration after the recorded prefix, run
      `conn.execute_batch(m.sql)`. Each migration file wraps itself in
      `BEGIN/COMMIT` and inserts its own `schema_migrations` row.
4. Returns `OpenOutcome { conn, path, applied: Vec<&'static str> }`.

Error surface (`OpenError`):

- `Sqlite(rusqlite::Error)` — driver-level failure.
- `UnknownRecordedMigration { found }` — downgrade: database recorded an id
  this binary doesn't know.
- `OrderMismatch { position, found, expected }` — migrations reordered or
  swapped.

These errors are typed specifically so a future `Store` trait can surface
downgrade failures distinctly from I/O failures.

---

## 5. Tests and checks run

| Command | Result |
|---|---|
| `cargo check --workspace` | green (pre-existing `unused_import` + `missing_docs` warnings only) |
| `cargo test --workspace` | green |
| `cargo test -p aether-storage` | 5 unit + 3 integration tests, all green |
| `cargo test -p aether-l5-policy` | 18 tests, all green (unchanged by this wave) |

Per-crate test counts (unit + integration, excludes doctests):

- `aether-event-bus`: 1
- `aether-storage`: 5 unit + 3 integration = 8
- `aether-media-engine`: 1 (fixed by adding serde_json dev-dep)
- `aether-telemetry`: 2
- `aether-l1-interaction`: 2
- `aether-l2-memory`: 2
- `aether-l3-presence`: 1
- `aether-l4-router`: 2
- `aether-l5-policy`: 18
- `aether-l6-persona`: 1
- `aether-l7-trust`: 1

All doctests pass (currently zero per crate).

---

## 6. L5 persistence posture — explicit status

Unchanged from Wave 3. L5 still uses:

- `InMemoryGrantLedger` at `packages/l5-policy/src/ledger.rs`
- `InMemoryAuditStore` at `packages/l5-policy/src/audit_store.rs`

Consequence: **L5 state is lost on process exit today.** This is correct
for Wave 3.5's narrow scope, but must be reflected in every user-facing
doc. README §3 "What does not run yet" and ROADMAP § "L5 durable
persistence" both state this explicitly after this wave.

---

## 7. Side fixes landed for coherence

Two diffs were already in the working tree from the prior session and were
carried forward unchanged, because they are prerequisites for the Wave 3.5
commit to be coherent:

- `Cargo.toml` workspace license: `Apache-2.0` → `MIT`. Aligns with
  `LICENSE` (MIT) and with the public README claim of MIT. Without this,
  every crate's `cargo check` would surface a license mismatch once the
  license metadata is consumed by packaging tools.
- `packages/l6-persona/Cargo.toml` and `packages/l7-trust/Cargo.toml`:
  added `serde_json` to `[dependencies]`. Those crates import `serde_json`
  in their `smoke.rs` tests; without the dep, Wave 4 tests would not
  compile.

Both are small, orthogonal fixes that would otherwise block the Wave 3.5
validation bar ("cargo test --workspace green").

---

## 8. Recommendations for the real L5 persistence wave

When the next wave swaps L5's backends, the expected shape is:

1. Introduce a `Store` trait in `packages/storage/` that exposes
   `open(), migrate(), transaction()` and the necessary prepared-statement
   helpers.
2. Implement `SqliteStore: Store` on top of `Connection`. The
   `open_with_migrations` primitive from this wave is the starting point —
   wrap it in a `pool: r2d2::Pool` once concurrency matters.
3. In `packages/l5-policy/src/storage_hooks.rs`, add `SqliteGrantLedger`
   and `SqliteAuditStore` behind a `durable-persistence` cargo feature.
4. Migrate `EngineConfig::wave3_default` to select between in-memory and
   SQLite backends based on the feature.
5. Add migration `0002_audit_chain.sql` with the hash-chain + HMAC trigger
   described in `planning/plans/implementation_prep/sqlite_schema_pack.md`
   §3b / §3c.
6. Ship with an integration test that writes a grant + audit row,
   tears the process down, reopens the DB, and confirms both survive —
   this is the single end-to-end invariant that proves durability.

That wave should carry the name `WAVE3_6_*` or `WAVE5_*` depending on the
coordinator's preference; keep it distinct from Wave 3.5 so the scoping
boundary is preserved in history.
