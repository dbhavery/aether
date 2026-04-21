# P1 — maybe_apply_vision guard symmetry — execution report (2026-05-04)

**Status:** Shipped, committed `5a4b15c` on `dev`. Push not authorized.

## Goal

Stop `maybe_apply_vision` from emitting a `WARN` "vision: data URL
decode failed: …" line for frame shapes the shell-side
`validate_frame_data_url` already rejects with a friendly,
user-facing error. Make the function safe regardless of caller.

## Before

`analyze_frame` shipped a tight validation gate yesterday
(`validate_frame_data_url`) — empty bodies, missing separators, and
wrong schemes are short-circuited at the shell boundary with a clear
user-facing error before any provider call. But `maybe_apply_vision`
itself still called L4's `split_data_url` directly, so:

- In the production code path, `analyze_frame`'s gate makes it
  unreachable; safe.
- If a future caller (test harness, debug command, parallel route)
  reached `maybe_apply_vision` with a known-bad shape, L4 would
  reject it with `ProviderBadResponse` and the function would emit
  a `WARN` log line — duplicating concerns the gate already owns.

## After

`maybe_apply_vision` now calls `validate_frame_data_url` immediately
after acquiring the provider + route, *before* delegating to
`split_data_url`. On `Err`:

- It returns `None` (existing "no vision call ran" contract).
- It logs at **debug**, not WARN, with the validation detail.
  Operators running at WARN level won't see noise for shapes the
  shell-side gate already owns.

Real provider/decode failures still WARN, since
`split_data_url`'s remaining error paths (e.g. non-base64 encoding,
empty MIME) are genuine surprises that an operator should see.

## Surfaces touched

- `apps/desktop/src-tauri/src/commands.rs::maybe_apply_vision`:
  - 11-line diff inserting the validation guard with a brief
    docstring explaining the production-vs-future-caller rationale.
  - No public surface change. No additional tests required —
    `validate_frame_data_url`'s 8 unit cases own the rules; this
    function only consumes them.

## Tests

Coverage: `validate_frame_data_url` is tested at the unit level (8
cases shipped 2026-05-03). Integration-level coverage of
`maybe_apply_vision` requires constructing a `State<'_, AppState>`
which is Tauri-specific scaffolding; deferred. The behavior change
is *quieter logs*, not a different return value, so the lack of an
integration test is acceptable in this scope.

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 89/89
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 85/85

## Hard-constraint compliance

- No push.
- No new providers introduced.
- No L5 / persistence / streaming changes.
- No microphone / voice / STT / TTS work.
- `vision_provider.json` shape unchanged.
- No `AuditRecordEvent` changes.
- No new test deps.
