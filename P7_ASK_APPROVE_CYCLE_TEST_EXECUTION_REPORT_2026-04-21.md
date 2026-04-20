# P7 — Ask → Approve / Reject cycle test against AppState

**Date:** 2026-04-21
**Branch:** `dev`
**Layers touched:** apps/desktop/src-tauri tests only.

## What shipped

Two new integration-style tests inside `state.rs`'s test module that
drive the same engine cycle the Tauri `submit_turn` and
`resolve_approval` commands use:

- `ask_approve_cycle_reaches_router_on_replay`:
  - Build a `TurnRequest` for `FilesEdit` (Ask in wave3 defaults).
  - `engine.handle_turn(req)` → asserts `AwaitingPolicyApproval` +
    `Decision::Ask { ticket }`.
  - `record_pending(ticket_id, PendingTurn { request, ask_result })`.
  - `build_approval_response(&ticket, Approve, _)` →
    `policy.respond_approval(...)`.
  - `take_pending` consumes the entry; a second call returns None.
  - Replay the stored `TurnRequest` → asserts `Completed`,
    `Decision::Allow`, non-empty route text, and that
    `latency_ms` is stamped on the replay turn too.
- `ask_reject_clears_pending_and_engine_remains_usable`:
  - Same Ask setup; rejection resolution; pending cleared after the
    first take; engine can still service a fresh `FilesRead` turn
    afterwards (`Completed` on follow-up).

## Why this, not a Tauri command test

Testing the Tauri `#[command]` functions directly would require
`State<'_, AppState>` instances from `tauri::test::mock_app()` —
a new dev-dep and extra scaffolding that doesn't meaningfully improve
coverage. The command wrappers around the engine cycle are thin
(~20 lines); the substance we want verified is the `handle_turn →
record_pending → respond_approval → take_pending → handle_turn` path
against a real `AppState`, which is exactly what these tests do.

## Checks run

- `cargo fmt --all -- --check` — clean.
- `cargo test` (default) — 13 passed (was 11, +2 cycle tests).
- `cargo test --features ollama-provider` — 19 passed (was 17).
- `cargo test --workspace` — all green.
- Layer-boundary lint — 0 violations.

## Risks / follow-ups

- The AppState under test is wired to the default catalog → pick
  aurora → reflex stub path. If a future slice makes `AppState::new()`
  non-deterministic (e.g. reads time of day into persona selection),
  the tests will need a seeding hook.
- Tauri command wrappers (`submit_turn`, `resolve_approval`) are not
  tested against the event-emitter path (they call
  `app.emit("presence:update", ...)`). If a future regression drops a
  presence event, these tests won't catch it. Consider adding a
  `tauri::test::mock_app()` pass if that becomes important.
