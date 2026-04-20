# P1 Execution Report — Durable memory retention policy

**Date:** 2026-04-24
**Scope:** `packages/l2-memory/` + `apps/desktop/` — bound the durable
session memory store so disk usage cannot grow unbounded, and give the
user an explicit "forget older than N days" surface.

## Summary

### L2 — new `RetentionPolicy` primitive

New `RetentionPolicy` struct with two orthogonal dials, each optional:

- `max_rows_per_session: Option<usize>` — hard cap, enforced
  automatically on every `append` inside the same mutex lock.
- `max_age_ms: Option<u64>` — age cap, applied **only** by explicit
  `prune_session(session_id, now_ms)` / `prune_all(now_ms)` maintenance
  calls. `append` does not own a wall clock; running an age cap on the
  write path would let a misconfigured caller retroactively drop other
  callers' history.

Presets:

- `RetentionPolicy::unbounded()` — append-only forever.
- `RetentionPolicy::default_bounded()` (also `Default`) — 500 rows per
  session, no age cap. Chosen so even a talkative user takes weeks to
  hit the ceiling while bounding growth across years of use.

### L2 — writable surface

- `SqliteSessionMemoryStore::new_with_retention(conn, config, policy)`.
- `SqliteSessionMemoryStore::new(...)` now wires
  `RetentionPolicy::default_bounded` automatically.
- `SqliteSessionMemoryStore::prune_session / prune_all` — age-based,
  reads `retention.max_age_ms`, no-op if unset.
- `SqliteSessionMemoryStore::prune_older_than(session_id, cutoff_ms)`
  — explicit, configuration-free deletion, used by the UX "Forget
  older than N days" surface (computes the cutoff at the point of
  action).
- `SqliteSessionMemoryStore::retention()` accessor for diagnostics.
- `DurableSessionStore::open_with_retention(path, config, policy)` and
  `.concrete()` accessor returning the typed store without downcast.

All pruning applies uniformly to every `MemoryRole` — banners,
approvals, user, assistant — because retention is a property of
*age/volume*, not *message type*.

### Shell — wiring & UX command

- `AppState` now carries an optional `Arc<SqliteSessionMemoryStore>`
  populated via `durable.concrete()` so retention maintenance is a
  single method call away, no downcast.
- New Tauri command `forget_older_than_days(days: u32)` → returns
  `{ removed, applied }`:
  - Validates `days >= 1`.
  - Computes `now_ms` on the backend.
  - Calls `prune_older_than(SESSION_ID, cutoff)` against the live
    durable store, or no-ops (`applied: false`) when the shell is
    running on the in-memory backend.
- Registered in `main.rs`.

### Tests

Six new integration tests in `packages/l2-memory/tests/sqlite_session.rs`:

1. `row_cap_retention_evicts_oldest_on_write` — insert 7 rows with
   `max_rows_per_session = 3`, assert on-disk count is 3 with the
   three highest sequences.
2. `row_cap_retention_is_per_session_not_global` — session isolation
   of the row cap.
3. `age_based_prune_session_drops_only_old_rows` — cutoff arithmetic
   against a mixed-age dataset.
4. `age_based_prune_all_applies_across_sessions` — multi-session
   age sweep.
5. `prune_is_noop_when_age_dial_unset` — confirms the `None` guard.
6. `unbounded_retention_leaves_all_rows_on_disk` — regression guard
   for the "no retention" profile.

One new shell test in `apps/desktop/src-tauri/src/state.rs`:

- `durable_store_prune_older_than_removes_only_old_rows` — end-to-end
  through AppState → prunes exactly the rows below the cutoff.

## Behaviour change

- New durable DBs default to the 500-rows-per-session cap. Existing
  DBs with more rows will be trimmed on the next append. For a
  typical user this is invisible; for the rare edge case who had
  thousands of rows, the oldest are dropped first — expected and
  documented.
- Users now have an explicit UI-ready Tauri command to run "Forget
  everything older than N days". The front-end surface for this is
  NOT included in this slice (kept minimal to keep review scope tight);
  adding it to Settings is one React component away.

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | ok |
| `cargo test --workspace` | all green |
| `cargo test -p aether-l2-memory --features sqlite-backend` | 11/11 (+6) |
| `apps/desktop/src-tauri && cargo test` | 20/20 (+1) |
| `python tools/lint-layer-boundaries/check.py` | OK |

## Risks / notes

- **`default_bounded` is now the default behaviour.** If a user has
  an existing `aether.db` with more than 500 rows per session, the
  next `append` will evict the oldest rows to bring it to 500. That's
  the intended semantics but worth flagging in release notes.
- **No UI surface yet.** `forget_older_than_days` is invokable via
  `invoke("forget_older_than_days", { days: 30 })` but isn't wired
  into Settings. Next slice (or a separate P-level) should add the
  Settings entry so the feature is discoverable.
- **Row-cap eviction uses `DELETE … WHERE sequence <= MAX - N`.**
  Under very high write concurrency this could evict slightly more
  than N-1 rows if an append interleaves (the `SELECT MAX` and
  `DELETE` are separate statements). Acceptable: the cap is a
  *bound*, not a *count*. The single-writer mutex makes this near-
  impossible in practice.

## Next (handoff priorities)

P2 — Trust drawer latency/token history tab (telemetry from P2d
surfaced in UI).

P3 — Persona-pack YAML loader replacing `state.rs::default_catalog()`.

Plus the pending UI work for this slice: a Settings entry that calls
`forget_older_than_days`.
