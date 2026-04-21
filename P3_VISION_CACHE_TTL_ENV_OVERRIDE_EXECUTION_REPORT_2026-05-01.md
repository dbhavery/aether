# P3 — `AETHER_VISION_MODEL_TTL_SECS` env override — execution report (2026-05-01)

**Status:** Shipped, committed `f5ecb24` on `dev`. Push not authorized.

## Goal

Operator-level knob for the vision model-list cache TTL without code
changes — so future remote / fast-changing adapters can be tuned
out-of-band.

## Surfaces touched

- `apps/desktop/src-tauri/src/vision_cache.rs`:
  - New public constants:
    - `TTL_ENV_VAR = "AETHER_VISION_MODEL_TTL_SECS"`
    - `TTL_FLOOR_SECS = 5`
    - `TTL_CEILING_SECS = 3_600`
    - `DEFAULT_TTL = 60s` (existing).
  - New pure helper `parse_ttl_secs(raw: &str) -> Option<Duration>`.
    Returns `Some` when the input parses as a `u64` of seconds in
    `[5, 3600]`. Returns `None` for missing / non-numeric / out-of-
    range / fractional / negative input.
  - New `ModelListCache::from_env()` constructor reads `TTL_ENV_VAR`
    via `parse_ttl_secs`. Falls back to default with a `tracing::warn`
    when the env var is set to an invalid value, INFO-logs when a
    valid override is applied, no log noise when unset.
  - New `ttl()` accessor for tests + diagnostics.
- `apps/desktop/src-tauri/src/state.rs`:
  - `AppState::build` now uses `ModelListCache::from_env()` instead
    of `::new()`. `::new()` stays as the default-only constructor for
    direct unit tests.

## Bounds rationale

- **Floor 5 s**: anything below thrashes the daemon enough that the
  cache becomes a net negative. Fast iteration is what the manual
  `↻` button is for.
- **Ceiling 3600 s** (1 hour): typo guard — common mistake is
  passing a millisecond value (e.g. `60000` meant for 60 s); rejecting
  anything past one hour catches that without blocking legitimate
  long TTLs (which would mean "I almost never want to refresh").

## Hot reload

Intentionally NOT supported. The env var is read once at AppState
construction. A subsequent in-process `setenv` does not affect the
running cache. Documented in the env var const docstring.

## Tests

`vision_cache::tests` gains 6 cases (12 total, was 6):

- `parse_ttl_secs_accepts_in_range_values` — covers the floor, a
  middle value, the ceiling, and a value with leading/trailing
  whitespace.
- `parse_ttl_secs_rejects_out_of_range` — `0`, `4` (below floor),
  `3601`, `60000` (above ceiling — the typo case).
- `parse_ttl_secs_rejects_non_numeric_and_empty` — empty,
  whitespace-only, alpha (`abc`), units-suffixed (`60s`), negative
  (`-1`), fractional (`1.5`).
- `from_env_uses_default_when_var_unset` — env var absent → default
  TTL.
- `from_env_picks_up_valid_override` — sets `30`, asserts the cache
  is built with a 30 s TTL.
- `from_env_falls_back_to_default_on_invalid_value` — `"garbage"`
  and `"0"` both fall back to default without panicking.

Env-set tests serialise through a file-scoped `ENV_MUTEX` mirroring
the same pattern in `providers::ollama::tests`.

Full check matrix:

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test --workspace` — all green.
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57.
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → **77 / 77** (was 71, +6).
- `python tools/lint-layer-boundaries/check.py` → 0 violations.
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → clean, 64/64.

## Hard-constraint compliance

- No push.
- No UI surface for TTL — explicitly an operator-level setting per
  spec.
- No other cache configuration knobs added in this run (e.g. no
  per-provider TTL, no max-entries cap).
- No L5 audit changes.
- No provider list expansion.
- No streaming/voice work.
- No image-persistence posture changes.

## Risks / follow-ups

- If a future remote adapter wants per-provider TTLs, the cache
  shape allows it (entries are keyed by `provider_id`); only the
  parser would need to extend. Defer until that adapter exists.
- Bounds are conservative — easy to widen if Don wants
  longer-than-1h TTLs. A user who really wants a 24 h TTL would be
  blocked today; that seems wise but documented as a follow-up.
