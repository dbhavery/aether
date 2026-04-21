# Chunk A — analyze_frame early-exit telemetry — execution report (2026-05-06)

**Status:** Shipped, committed `d61a97e` on `dev`. Push not authorized.

## Goal

Make the Trust drawer's History tab honest about every camera/screen
analysis attempt, including ones that short-circuit before any
provider call. Today the user can submit a capture and see no row in
History when:

- the media permission gate evaluates to Deny or Ask, or
- the shell-side `validate_frame_data_url` rejects the payload.

That silence is misleading — the user took an action and the system
made a decision; the History tab should reflect that.

## Surfaces touched

- `apps/desktop/src-tauri/src/commands.rs`:
  - New `record_frame_early_exit_telemetry(state, kind)` helper. It
    writes a `TelemetryEntry` whose `provider`, `model`, `tier`,
    `latency_ms`, and token fields are all `None` — only the persona
    id and timestamp carry signal. Kind values are stable strings
    consumed by the History tab and the TS allow-list:
    - `"frame_invalid"` (validation rejection),
    - `"permission_denied"` (gate Deny),
    - `"permission_ask"` (gate PromptUser).
  - `analyze_frame` calls the helper:
    - inside the `CaptureGate::Deny` branch (after the existing
      memory record),
    - inside the `CaptureGate::PromptUser` branch,
    - inside the `validate_frame_data_url` rejection branch (before
      the early `Err` return).
  - The doc-comment on the helper enumerates the kinds and the
    intentional `None` fields for future readers.
- `apps/desktop/src/lib/mediaTurns.ts`:
  - `MEDIA_TURN_KINDS` picks up `"frame_invalid"`.
  - The leading docstring lists all five kinds (was four) and
    documents what each represents.
- `apps/desktop/src/lib/mediaTurns.test.ts`:
  - The `MEDIA_TURN_KINDS` parity test grows to expect the new kind.
  - `isMediaTurn` parameterized cases include `"frame_invalid"`.
- `apps/desktop/src/components/TrustDrawer.tsx`:
  - `kindClass` colors `"frame_invalid"` as `text-aether-err`,
    matching the other failure tier.

## Hard-constraint compliance

- **L5 / audit semantics unchanged.** No policy decision was made on
  these paths; no audit row is written. `record_telemetry` writes to
  the in-memory `AppState::telemetry` buffer only — that buffer is
  cleared on app restart per the existing contract documented in
  the Trust drawer footer.
- **No `AuditRecordEvent` changes.**
- **No durable-memory privacy posture change.** Telemetry remains
  in-memory.
- **No new providers.**
- **No new test deps.**
- **No streaming / continuous capture / mic / voice work.**

## Tests

- Desktop shell: **93 / 93** (unchanged — no Rust tests added; the
  helper is six lines of straight-line code and writing a State-
  driven integration test for it would have required Tauri-specific
  scaffolding that does not exist in the test harness today).
- vitest: **86 / 86** (was 85; +1 case grew implicitly from the
  `MEDIA_TURN_KINDS` parity test since the expected set now has
  five members and the parameterized `isMediaTurn` test now runs
  five rows).

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 93/93
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 86/86

## Why no Rust unit test for the helper

The helper takes `&State<'_, AppState>`, which is Tauri's typed
state-injection wrapper. Constructing one in a `#[cfg(test)]` block
requires a real `tauri::App` or a dedicated mock that does not exist
in the workspace today; building one is a larger investment than
the helper itself justifies. The contract is enforced by:

1. The TS allow-list parity test (`MEDIA_TURN_KINDS` includes
   `"frame_invalid"`).
2. The kind strings being literal at the three call sites — any
   typo would produce an unrecognized History entry that the next
   manual smoke test would catch.

If the helper grows beyond the current straight-line shape, revisit
and add the State plumbing.
