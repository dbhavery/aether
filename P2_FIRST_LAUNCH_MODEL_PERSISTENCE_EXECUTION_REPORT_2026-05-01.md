# P2 — First-launch vision model persistence — execution report (2026-05-01)

**Status:** Shipped, committed `521d30f` on `dev`. Push not authorized.

## Goal

On first boot (no `vision_provider.json` yet), seed
`model_per_provider` from each registered adapter's env-supplied
default model so the persisted file reflects what the user is
actually running — even before they've touched the badge.

## Why it mattered

Before this change, the bootstrap order was:

1. Construct each adapter from env (model = `AETHER_OLLAMA_VISION_MODEL`
   or equivalent).
2. Register each adapter into the registry.
3. `attach_persistence(path)` — loads the file (empty default on
   first launch), applies any persisted models via `set_model`.
4. `auto_select_first_if_unset()` — picks the first registered
   provider as active.

After this sequence, `model_per_provider` was empty on disk and in
memory until the user clicked a model chip. The provider swap
restoration logic had nothing to restore. Small, but it broke the
"first-run state already reflects pre-configured intent" principle.

## Surfaces touched

- `apps/desktop/src-tauri/src/vision_registry.rs`:
  - New `seed_missing_models_from_adapters() -> Result<(), String>`.
    For every registered provider not already in the map, insert
    `(id, current_model)` when `current_model` is a non-empty
    (non-whitespace) string. Idempotent. Persists immediately if
    anything changed.
  - Adapters that don't expose `current_model()` (passive future
    adapters) are skipped — better an absent entry than a misleading
    empty string.
- `apps/desktop/src-tauri/src/state.rs`:
  - New `vision_seed_missing_models()` accessor on `AppState` that
    forwards to the registry method.
- `apps/desktop/src-tauri/src/main.rs`:
  - `wire_vision_registry` calls `state.vision_seed_missing_models()`
    after `attach_persistence` + `auto_select_first_if_unset`.
    Failures (e.g. read-only data dir) are logged and continued so
    first launch never blocks on disk I/O.

## Wire-shape and back-compat

`vision_provider.json` schema is unchanged. The two-field shape
`{ active, model_per_provider }` already shipped; this work just
populates `model_per_provider` earlier in the lifecycle. Old files
without the map keep loading because of the existing serde default.
Re-running on subsequent launches is a no-op because every provider
is already present.

## Tests

`vision_registry::tests` gains 5 cases (22 total, was 17):

- `seed_missing_models_writes_through_for_first_launch` — registers
  two adapters with distinct env-supplied models, confirms the map
  is empty before seeding, calls the seed, asserts both models are
  in the map AND that a fresh registry pointing at the same path
  recovers both.
- `seed_missing_models_is_idempotent_after_user_pick` — seeds, then
  user picks a different model, then seeds again — user pick is
  preserved.
- `seed_missing_models_skips_providers_with_no_current_model` — a
  passive provider that returns `None` from `current_model()`
  contributes no map entry.
- `seed_missing_models_skips_whitespace_only_models` — defensive: a
  buggy adapter reporting `"   "` is treated as "no model".
- `seed_missing_models_no_op_when_persistence_unwired` — without an
  attached persistence path, in-memory map is still updated but no
  I/O is attempted.

Full check matrix:

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test --workspace` — all green.
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57.
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 71/71.
- `python tools/lint-layer-boundaries/check.py` → 0 violations.

## Hard-constraint compliance

- No push.
- No new mandatory env vars — adapters keep their existing
  `AETHER_OLLAMA_VISION_MODEL` / `AETHER_LLAMACPP_VISION_MODEL`
  config; this work just propagates those values further.
- `vision_provider.json` contract unchanged (still
  `{ active, model_per_provider }`); seeding only populates
  existing fields.
- L5 audit untouched.
- Image-persistence posture unchanged.
- No new providers introduced.

## Risks / follow-ups

- If a user manually edits `vision_provider.json` between boots and
  removes a model entry that adapter still reports via
  `current_model()`, the next boot will re-seed it. That matches
  the "missing entries get filled" intent — if a user wants
  text-only mode, they should set `active: null` (already
  supported), not edit the map.
- `seed_missing_models_from_adapters` returns `Err` when persistence
  fails. main.rs swallows it with a warn; tests can assert error
  paths if a future caller wants stricter handling.
