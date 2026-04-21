# Chunk B — vision boot log clarity — execution report (2026-05-06)

**Status:** Shipped, committed `a9fc15d` on `dev`. Push not authorized.

## Goal

Improve the diagnostic value of the vision-track WARN lines an
operator sees at boot, without changing log levels or adding
structured-telemetry fields. Three specific lines were missing the
URL or path that would have made them immediately actionable.

## Surfaces touched

- `apps/desktop/src-tauri/src/vision_registry.rs::load_persisted`:
  - `vision_provider.json is malformed` WARN now includes the full
    `path.display()` — operators can locate the file without
    grepping the binary or Settings docs.
  - `could not read vision_provider.json` WARN does the same.
- `apps/desktop/src-tauri/src/main.rs::register_ollama_vision_if_configured`:
  - `ollama vision healthcheck failed` WARN now includes the base
    URL it tried (cloned from `cfg.base_url` before the move into
    `OllamaVisionProvider::new`).
- `apps/desktop/src-tauri/src/main.rs::register_llamacpp_vision_if_configured`:
  - `llamacpp vision healthcheck failed` WARN matches the Ollama
    shape.

The wording stays close to the existing `vision provider candidate:
<adapter> model=<m> base=<u>` INFO lines so a WARN reads naturally
as the failed follow-up. The base URL was previously visible only
in INFO; an operator running at WARN-and-above logging would have
seen failures with no host context.

## What was deliberately not changed

- **Log levels.** All four lines stay WARN. None of them indicate
  a programming bug (they're operational misconfiguration the user
  can fix), but they are also not "expected" enough to demote to
  INFO.
- **Structured telemetry.** None of these go through the telemetry
  buffer — they're tracing logs. Promoting them into telemetry
  would conflate operational diagnostics with user-facing turn
  history.
- **The shell-side validation `debug` log.** `maybe_apply_vision`'s
  "skipping route, frame failed validation" line stays at debug.
  The user-facing surface is the friendly error returned by
  `analyze_frame`; the debug log is for operators tracing the
  defense-in-depth mirror.

## Hard-constraint compliance

- **No L5 / audit semantics changes.**
- **No vision_provider.json schema changes.**
- **No new providers.**
- **No new test deps.**

## Tests

No new tests added — these are log-message changes, not behavior
changes. Existing test suites still pass:

- Desktop shell: **93 / 93**
- L4 router: **57 / 57**
- vitest: **86 / 86**
- `cargo fmt`, `cargo check --workspace`, layer-boundary lint, pnpm
  typecheck/build all clean.
