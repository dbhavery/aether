# P3 — Durable session memory (SqliteSessionMemoryStore)

**Date:** 2026-04-22
**Branch:** `dev`
**Layers touched:** `packages/storage` (migration) + `packages/l2-memory`
(new module, feature-gated).

## What shipped

1. **`packages/storage/migrations/0004_conversation_log.sql`** —
   additive migration declaring:
   ```sql
   conversation_log(
     session_id TEXT NOT NULL,
     sequence   INTEGER NOT NULL,
     role       TEXT NOT NULL,
     content    TEXT NOT NULL,
     timestamp_ms INTEGER NOT NULL,
     PRIMARY KEY (session_id, sequence)
   );
   CREATE INDEX idx_conversation_log_session_timestamp
     ON conversation_log(session_id, timestamp_ms);
   ```
   Deliberately no append-only triggers — users must be able to clear
   their session. That's the single behavioural difference from
   `policy_audit_log`.
2. **`packages/storage/src/migrations.rs`** — registers
   `MIGRATION_0004_CONVERSATION_LOG`, updates `expected_head_id()`
   assertion to `"0004_conversation_log"`.
3. **`packages/l2-memory/Cargo.toml`** — new `sqlite-backend` cargo
   feature, `tempfile` added as dev-dep for the integration test.
4. **`packages/l2-memory/src/sqlite_session.rs`** — new module behind
   `#[cfg(feature = "sqlite-backend")]`:
   - `SqliteSessionMemoryStore` implementing `SessionMemoryStore`.
     Uses a shared `Arc<Mutex<Connection>>` (same pattern L5's
     `DurableBackends` uses to keep the single-writer invariant).
   - `DurableSessionStore::open(path)` / `open_with_config(path, cfg)`
     convenience builder — opens DB, runs migrations, wraps the
     connection.
   - Append assigns per-session monotonic sequences via
     `MAX(sequence) + 1`; mirrors in-memory semantics.
   - `recent()` uses `max_turns` as a **read-side LIMIT**, not a
     write-side eviction — durable history is preserved on disk, the
     window just bounds how much surfaces. `max_chars` is applied
     after the fetch to mirror the in-memory store's secondary trim.
   - `clear_session()` executes a plain `DELETE` (no triggers reject it).
5. **Exports:** `SqliteSessionMemoryStore`, `DurableSessionStore` from
   `lib.rs`, gated on the same feature.
6. **Integration tests in `packages/l2-memory/tests/sqlite_session.rs`**
   (5, all against a real temp-dir SQLite file):
   - `append_and_recent_round_trip_through_real_sqlite`
   - `records_survive_reopen_of_the_same_db_file` (includes sequence
     continuation across reopen)
   - `clear_session_removes_only_target_session` (plus sequence
     restart after clear)
   - `recent_bounds_to_config_max_turns_without_dropping_rows_on_disk`
     (asserts 6 rows on disk even when `recent()` returns 3)
   - `unknown_session_returns_empty_window_not_error`

## Intentional scope cuts

- **No live shell wiring yet.** The desktop shell's `AppState` still
  constructs `InMemorySessionMemoryStore`. Flipping it to
  `DurableSessionStore::open(app_data_dir.join("aether.db"))` is a
  follow-up slice — small change in `state.rs`, but needs a Tauri
  `path` resolution step + user-data-dir semantics that deserve their
  own slice. The durable store is ready to be dropped in.
- **`max_chars` semantics** are approximated, not exact. We LIMIT by
  row count (`max_turns`) and then trim by chars oldest-first. For
  the window sizes v0 uses (tens of turns), this matches the
  in-memory behaviour; a future slice can push char budgets into SQL
  if that ever matters.
- **No migration for pre-existing `InMemory` content.** There is no
  persisted state to migrate; the current shell never wrote any.

## Checks run

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo check -p aether-l2-memory --features sqlite-backend` — clean.
- `cargo test --workspace` — all pass (101 total; baseline was 100).
- `cargo test -p aether-l2-memory --features sqlite-backend` — 5
  integration tests pass.
- Desktop shell: 13 default, 19 with `ollama-provider`.
- `pnpm typecheck` + `pnpm build` — clean.
- `python tools/lint-layer-boundaries/check.py` — 0 violations.

## Risks / follow-ups

- **The read-side LIMIT decouples bound from truth.** If the shell
  uses `SqliteSessionMemoryStore` and a user scrolls through
  "recent", they'll only ever see the last `max_turns`. A future UI
  that wants "show all history" will need a second method (e.g.
  `range()` or `count()`) on the trait — doesn't exist today because
  the in-memory store never needed it.
- **`role_from_wire` fails on unknown strings** — if the table picks
  up a new role value from a future migration, `recent()` returns
  `L2Error::Storage`. Safer than silently dropping, and the
  round-trip test guards the known-good values.
- **Single-writer discipline is the caller's responsibility** for
  now. Two `SqliteSessionMemoryStore` instances constructed from
  separate `open_with_migrations` calls against the same file would
  race on `MAX(sequence)+1` inside a concurrency window. The
  `Arc<Mutex<Connection>>` the builder returns handles the common
  case; the edge case is documented in the module header.
