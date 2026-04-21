# P3 — Always-on vision cache TTL boot log — execution report (2026-05-02)

**Status:** Shipped, committed `3434e0b` on `dev`. Push not authorized.

## Goal

Improve operator observability — operators should always see the
effective vision model-list cache TTL at boot, not only when
`AETHER_VISION_MODEL_TTL_SECS` is set.

## Before

`ModelListCache::from_env` logged INFO only on a valid env override
and WARN only on an invalid value. The default-TTL boot path was
silent, which left operators wondering whether the cache was
actually active and at what value.

## After

A single unconditional INFO line is stamped at every construction:

```
vision model-list cache TTL: 60s (default)
vision model-list cache TTL: 30s (env override)
vision model-list cache TTL: 60s (default after invalid env)
```

The existing WARN line for invalid env values is preserved and
emitted before the INFO line so misconfiguration stays visible
alongside the resolved fallback.

## Surfaces touched

- `apps/desktop/src-tauri/src/vision_cache.rs`:
  - New small `TtlSource` enum
    (`Default | EnvOverride | DefaultAfterInvalidEnv`) plus a
    stable `.label()` mapping for the log line.
  - New pure helper
    `resolve_ttl_from_env() -> (Duration, TtlSource)` so the
    resolution rules are unit-testable without sniffing log
    output.
  - `from_env` now delegates to `resolve_ttl_from_env`, emits the
    WARN line only when the source is `DefaultAfterInvalidEnv`,
    and always emits the INFO line.

All existing TTL behavior is unchanged:

- default 60s
- bounds `[5, 3600]` seconds
- no hot reload (env read once at boot)

## Tests

`vision_cache::tests` gains 4 cases (16 total, was 12):

- `resolve_ttl_from_env_reports_default_when_unset`
- `resolve_ttl_from_env_reports_env_override`
- `resolve_ttl_from_env_reports_invalid_env_fallback` (covers
  both `"garbage"` and `"0"`)
- `ttl_source_label_is_stable` — locks the strings the boot log
  prints.

Env-set tests serialise through the existing file-scoped
`ENV_MUTEX`.

`apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 81/81.

Full check matrix run before stopping — all green.

## Hard-constraint compliance

- No push.
- No UI surface for TTL — operator-only via env + boot log.
- No other cache configuration knobs added.
- No L5 / persistence / streaming changes.
- No new providers.
