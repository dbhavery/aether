# P1 — vision_provider.json schema-tolerant read test — execution report (2026-05-05)

**Status:** Shipped, committed `3c94037` on `dev`. Push not authorized.

## Goal

Lock the additive-default-safe contract for `vision_provider.json`
*by test* so a future field addition doesn't silently regress the
forward-compat guarantee the handoff has been claiming since
2026-05-01.

## Surface inspected

- `apps/desktop/src-tauri/src/vision_registry.rs`
  - `VisionPersistedState` struct
    (`active: Option<String>`, `model_per_provider: BTreeMap<String, String>`).
  - `#[derive(... Deserialize, Default ...)]` — no
    `#[serde(deny_unknown_fields)]`, so by serde's defaults
    unknown keys are silently dropped during deserialization.
  - `load_persisted(path)` — reads the file, calls
    `serde_json::from_str`, falls back to `VisionPersistedState::default()`
    on read or parse error (with a WARN log).
  - `save_persisted(path, state)` — writes
    `serde_json::to_string_pretty(state)` via a `.tmp` rename.
- `apps/desktop/src-tauri/src/main.rs::127` — first-launch seeding
  hook. Uses the same struct.

## Tests added (4)

All four landed in `vision_registry::tests`.

### `unknown_top_level_field_is_ignored_on_load`

Writes a JSON file containing:
- valid `active`,
- valid `model_per_provider`,
- three unknown fields with deliberately mixed JSON types:
  string (`"future_unknown_field"`), object (`"future_object"`),
  and array (`"future_array"`).

Calls `attach_persistence` (the production load path). Asserts
`active` and the model map survived intact and the load did not
fail / fall back to defaults.

### `load_persisted_directly_tolerates_unknown_fields`

Same shape, but invokes `load_persisted` directly. Proves the
serde derive itself is the gate — the additive contract is
enforced at the type level, not by `attach_persistence` happening
to swallow errors. Important because it means future call sites of
`load_persisted` inherit the same forward-compat behavior for free.

### `unknown_fields_are_dropped_on_rewrite`

Writes a file with an unknown `future_field`, loads it via
`attach_persistence`, then triggers a normal rewrite via
`set_active_model`. Asserts the rewritten file no longer contains
`future_field`. Documents the intentional limitation in the test
itself.

### `malformed_json_falls_back_to_default_state`

Adjacent contract: a truly broken file (here, `active` typed as an
array instead of a string-or-null) must not panic. Confirms
`load_persisted` warns and returns `VisionPersistedState::default()`,
so the shell still boots cleanly.

## How unknown fields behave (documented behavior)

- **On read:** Silently dropped during deserialization. `active`
  and `model_per_provider` are preserved exactly as written. The
  shell does not warn — unknown fields are not anomalies.
- **On rewrite:** Lost. The struct has no
  `#[serde(flatten)] HashMap<String, Value>` extras bag, so
  any unknown keys present in the on-disk file are gone the next
  time the shell saves the file (e.g. on a model swap).

This is acceptable under the additive-default-safe contract:

1. Old shells reading a new file → known fields preserved, unknowns
   ignored. **Pass.**
2. New shells reading an old file → known fields preserved, missing
   fields default-safe via `#[serde(default)]`. **Pass** (already
   covered by `old_persistence_without_model_map_still_loads`).
3. Old shell rewriting a file with new fields → new fields lost.
   **Acceptable** — the contract requires new fields to default-safe
   on read AND tolerate being absent from a freshly-rewritten file.

The cost of preserving unknowns on round-trip would be either:

- adding `#[serde(flatten)] extras: BTreeMap<String, serde_json::Value>`
  (mixes typed and untyped data, complicates equality, leaks
  yesterday's UI state into tomorrow's shell), or
- introducing a versioning system / schema migration framework
  (out of scope and explicitly forbidden by this session's hard
  constraints).

Neither is worth doing today. The test now makes the limitation
explicit so a future PR doesn't quietly add a field assuming
round-trip preservation.

## Tests

Vision registry: **26 passing** (was 22, +4).
Desktop shell: **93 passing** (was 89, +4).

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 93/93
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 85/85

## Hard-constraint compliance

- No push.
- No new providers introduced.
- No new fields added to `VisionPersistedState`.
- No versioning / migration framework introduced.
- No L5 / persistence / streaming changes.
- No `AuditRecordEvent` changes.
- No new test deps.
