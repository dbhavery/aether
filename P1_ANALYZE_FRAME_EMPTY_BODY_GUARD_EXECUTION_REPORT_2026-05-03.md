# P1 — analyze_frame empty-body guard — execution report (2026-05-03)

**Status:** Shipped, committed `48757f5` on `dev`. Push not authorized.

## Goal

Reject obviously broken frame payloads (empty body, missing comma
separator, body too short to decode) at the shell boundary, with a
clear user-facing message — so the user is told what went wrong and
what to do next, instead of seeing an opaque
`ProviderBadResponse: data URL ...` error from the L4 layer.

## Before

`analyze_frame` ran a single inline check:

```rust
if !request.frame_data_url.starts_with("data:image/") {
    return Err("frame_data_url must be a data:image/... URL".into());
}
```

A payload like `data:image/png;base64,` (prefix correct, body empty)
sailed past this guard, was handed to `maybe_apply_vision`, was
forwarded to `split_data_url` which happily returned an empty body,
and only blew up at the provider with a low-level decode error. The
error surfaced in the UI as raw provider noise — no actionable hint
that the capture itself had failed.

## After

A small pure helper now owns the rules:

```rust
fn validate_frame_data_url(url: &str) -> Result<&str, String>
```

Rules in order:

1. URL must start with `data:image/`.
2. URL must contain a comma (the base64 body separator).
3. The substring after the comma, once trimmed, must be non-empty.
4. The trimmed body must be at least `MIN_FRAME_BODY_LEN = 4` chars
   — the floor for any non-empty base64 payload (4 chars decode to
   3 bytes; anything shorter cannot represent even one decoded byte).

`analyze_frame` calls the helper immediately after the existing
prefix check site. On `Err`, the shell returns a friendly string:

```
<specific failure detail>. Try capturing a new frame.
```

Concretely:

- `frame_data_url must be a data:image/... URL. Try capturing a new frame.`
- `frame_data_url is missing the base64 body separator (','). Try capturing a new frame.`
- `frame_data_url has an empty image body — capture may have failed. Try capturing a new frame.`
- `frame_data_url body is too short to decode — capture may have failed. Try capturing a new frame.`

The user-facing copy explains *what* went wrong in plain language and
gives a concrete next step (recapture). No provider call runs, no
audit row is written, no telemetry is recorded for the failed call —
the gate is a true short-circuit.

## Surfaces touched

- `apps/desktop/src-tauri/src/commands.rs`:
  - New `MIN_FRAME_BODY_LEN: usize = 4` constant.
  - New `validate_frame_data_url(url: &str) -> Result<&str, String>`
    pure helper, doc-commented to explain the layered relationship
    with L4's `split_data_url` (the helper is the friendly first line
    of defense; L4 still does the strict MIME / encoding check when
    the engine is invoked).
  - The inline prefix check inside `analyze_frame` is replaced with a
    call to the helper and a single error-shape conversion.

## Tests

`commands::tests` gains 8 cases (89 total in the desktop shell, was
81):

- `validate_frame_data_url_accepts_well_formed_payload`
- `validate_frame_data_url_accepts_jpeg`
- `validate_frame_data_url_rejects_wrong_scheme`
- `validate_frame_data_url_rejects_non_image_mime`
- `validate_frame_data_url_rejects_missing_separator`
- `validate_frame_data_url_rejects_empty_body`
- `validate_frame_data_url_rejects_whitespace_only_body`
- `validate_frame_data_url_rejects_too_short_body`

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 89/89
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 81/81

## Where the error surfaces in the UI

`analyze_frame` returns `Result<FrameAnalysisOutcome, String>`. The
existing camera/screen panel error path renders the `Err(String)` on
the panel's status line, so the new copy lands in exactly the same
place existing `analyze_frame` errors already show. No UI changes
were required.

## Hard-constraint compliance

- No push.
- No new providers introduced.
- No L5 / persistence / streaming changes.
- No microphone / voice / STT / TTS work.
- `vision_provider.json` shape unchanged.
- No `AuditRecordEvent` changes — failed-validation calls don't
  reach the audit layer at all by design (they short-circuit before
  the engine is invoked).
- No new test deps.
