# P1 Execution Report — Wire durable session memory into AppState

**Date:** 2026-04-23
**Scope:** `apps/desktop/src-tauri/` — flip `AppState::new()` onto the
feature-gated `DurableSessionStore` landed in commit `e223271` so the
companion actually persists conversation history across restarts.

## Summary

- Added a default `sqlite-backend` feature on `aether-desktop-shell`
  that turns on `aether-l2-memory/sqlite-backend`.
- Introduced `AppState::new_with_db_path(path)` which opens (or creates)
  `aether.db` under the OS-native app data dir, runs migration 0004,
  and falls back to the in-memory store — with a `tracing::warn!` — if
  the open fails. Directory is created on demand.
- Added a `MemoryBackend` discriminator + `memory_backend()` accessor
  on `AppState` so diagnostics and future dev-only UI can report which
  backend is live without the engine ever branching on it.
- Flipped `main.rs` to construct `AppState` inside Tauri's `.setup()`
  closure using `app.path().app_data_dir()` for path resolution.
  In-memory fallback is preserved for the `--no-default-features` build
  and for path-resolution failures.
- New integration-shaped tests in `state.rs`:
  - `durable_memory_survives_appstate_reopen` — round-trips turns
    through a fresh AppState + temp `aether.db`, drops it, reopens a
    second AppState against the same file, and verifies both user and
    assistant turns are readable.
  - `durable_open_failure_falls_back_to_in_memory` — points the durable
    constructor at an un-writable path and confirms the shell still
    boots with the in-memory store.

## Behaviour change

The shipped desktop shell now persists session memory to
`%APPDATA%/Aether/aether.db` (or platform equivalent). Turns written
during one run are readable on the next run. Clearing the session via
`commands::clear_session` still deletes rows — matching the existing
`SessionMemoryStore::clear_session` contract and the sqlite_session
module docstring's explicit "a user must be able to forget" semantics.

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | ok (pre-existing missing-docs warnings only) |
| `cargo test --workspace` | all green |
| `cargo test -p aether-l2-memory --features sqlite-backend` | 5/5 ok |
| `cd apps/desktop/src-tauri && cargo test` | 15/15 ok (incl. two new) |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## Risks / notes

- On Windows the app data dir is resolved lazily via Tauri's path API
  at setup time; a user whose `%APPDATA%` is missing or not writable
  degrades to in-memory rather than crashing. Tracing warns at WARN.
- The Tauri 2 `path()` API lives behind the `Manager` trait; main.rs
  now imports it explicitly. No new plugin is required.
- Builds with `--no-default-features` keep the pre-P1 in-memory path
  intact — useful for sandboxes that cannot load `rusqlite`.

## Next (per handoff)

P2 — `EngineConfig::with_preset_overlay(preset)` so the onboarding
autonomy picker actually changes policy. Shell reads the stored preset
on boot / `switch_persona`.
