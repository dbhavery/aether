# P2 Execution Report — Trust drawer latency/token history tab

**Date:** 2026-04-24
**Scope:** `apps/desktop/` — surface the existing per-turn latency +
token telemetry (P2d) in a new Trust-drawer tab so the user can review
performance and usage at a glance.

## Summary

### Shell — telemetry ring buffer

- `AppState` now owns a `Mutex<VecDeque<TelemetryEntry>>` ring buffer,
  capped at `TELEMETRY_BUFFER_CAPACITY = 50` entries. Eviction is
  FIFO; poisoned-lock writes log at WARN and drop the entry.
- Helpers on AppState:
  - `record_telemetry(entry)`,
  - `telemetry_recent(limit) -> Vec<TelemetryEntry>` (newest first,
    clamped to capacity),
  - `clear_telemetry()`.
- `finalize_turn` records an entry on every completed or policy-blocked
  turn. `provider_error_payload` also records a row so provider
  failures are visible in history.

### Shell — IPC

- `TelemetryEntry` serializes to camel-case-less snake_case fields
  (`turn_id`, `timestamp_ms`, `kind`, `persona_id`, `provider`, `tier`,
  `latency_ms`, `prompt_tokens`, `completion_tokens`), matching the
  frontend `TelemetryEntry` type.
- Two new Tauri commands:
  - `telemetry_recent(limit: Option<usize>) -> Vec<TelemetryEntry>`
    (limit clamped to capacity; default = capacity),
  - `telemetry_clear() -> void`.

### Frontend — Trust drawer gets tabs

- `TrustDrawer` is now a two-tab surface: **Audit** (pre-existing) and
  **History** (new). Tab state is local to the component; switching
  tabs never re-fetches (both loads happen on open).
- `History` list renders:
  - outcome kind (colour-coded: completed green, denied/provider_error
    red, needs_upgrade/draft_only amber, otherwise muted),
  - persona · provider · tier line,
  - prompt / completion / total tokens,
  - latency formatted as `1.23s` for ≥1s, `820ms` otherwise.
- Footer shows an "In-memory only — cleared on app restart" hint and a
  **Clear** button that calls `telemetry_clear`.
- Empty state copy: *"No turns logged yet. Send a message and timing
  will appear here."*

### `lib/api.ts` additions

- `TelemetryEntry` interface,
- `telemetryRecent(limit) -> Promise<TelemetryEntry[]>`,
- `telemetryClear() -> Promise<void>`,
- Plus `ForgetOlderReport` + `forgetOlderThanDays(days)` binding
  for P1 (included here to keep the api surface cohesive; no UI
  consumer yet).

### Tests

Two new shell tests in `state.rs`:

1. `telemetry_ring_buffer_evicts_oldest_and_returns_newest_first` —
   push `CAPACITY + 5` entries, assert only the newest `CAPACITY`
   survive and order is newest-first.
2. `telemetry_clear_empties_buffer` — write / read / clear / read.

## Behaviour change

The Trust drawer now has two tabs. The Audit tab is unchanged. The
History tab shows the last 50 turns with timing + tokens + outcome.
Closing the app clears the history (documented in the footer). No
disk footprint for telemetry.

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo test --workspace` | all green |
| `apps/desktop/src-tauri && cargo test` | 22/22 (+2) |
| `python tools/lint-layer-boundaries/check.py` | OK |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | clean |

## Risks / notes

- Telemetry is in-memory only. If a user wants persistent history we
  can tee entries into a new SQLite table later; the struct and
  commands are designed to make that drop-in.
- The buffer is process-global per AppState, not per-session. If v0
  ever grows multi-session semantics, add `session_id` to
  `TelemetryEntry`.
- Block rows (denied, needs_upgrade, draft_only) have `None` for
  provider/tier/latency/tokens — the UI formats those as `—` or
  "no token count" so empty rows remain readable.
- Poisoned-lock writes don't crash the shell — telemetry is UX only.

## Next

P3 — Persona-pack YAML loader replacing `state.rs::default_catalog`.
Plus small UI polish: a Settings entry invoking
`forget_older_than_days` (P1 backend already in place).
