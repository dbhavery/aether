# P2 — TTL cache + manual refresh for vision model lists — execution report (2026-04-29)

**Status:** Shipped, committed `b777749` on `dev`. Push not authorized.

## Goal

Stop hitting the vision provider's `list_models` endpoint on every
status query. Add a small TTL cache plus a manual `↻` refresh
affordance for when the user pulls a new model and wants to see it
immediately.

## Surfaces touched

- `apps/desktop/src-tauri/src/vision_cache.rs` (new) — pure
  per-provider TTL cache. Default TTL 60 s. `get` / `put` /
  `invalidate` / `clear`. Tests drive the clock via `_with_now`
  variants — no sleeps.
- `apps/desktop/src-tauri/src/state.rs` — adds `vision_model_cache:
  ModelListCache` to `AppState`. New methods:
  `vision_model_list_cached` (cache-first lookup) and
  `vision_model_list_refresh` (cache-bypass refetch). Both return a
  typed `VisionModelListError` enum (`NoActive` / `Unavailable(id)`)
  so the command layer can render plain-language messages.
  `set_active_vision_provider` invalidates the new active provider's
  slot; `set_active_vision_model` invalidates the active provider's
  slot. Both keep other providers' entries warm.
- `apps/desktop/src-tauri/src/commands.rs` — `list_vision_models`
  now consults the cache. New `refresh_vision_models` command forces
  a refetch. The `set_active_vision_model` validation path uses the
  cached helper too, so swapping a model doesn't double-fetch.
- `apps/desktop/src-tauri/src/main.rs` — registers `vision_cache`
  module and the `refresh_vision_models` command.
- `apps/desktop/src/lib/api.ts` — exports `refreshVisionModels`.
- `apps/desktop/src/components/VisionBadge.tsx` — adds a small `↻`
  button next to the model strip header (and the "models
  unavailable" hint) that calls `refresh_vision_models`. Disables
  while a swap or load is in flight so a second refresh can't queue
  on top of an in-flight one.

## Cache semantics

- Hit when the entry's age is `< TTL`.
- Miss → fetch via `provider.list_models()`, store, return.
- `invalidate(provider_id)` drops one entry; other providers stay
  warm (e.g. swap from Ollama to llama.cpp leaves Ollama's cached
  list valid for the next swap-back).
- `clear()` empties everything (used by tests; not wired to a
  command — manual refresh is per-active-provider only).

## Tests

- `aether-desktop-shell` (with `ollama-provider,vision-llamacpp`):
  **66 passing**, was 60. +6 new in `vision_cache::tests`:
  - `miss_on_empty_cache`
  - `hit_within_ttl_returns_cached_list`
  - `miss_after_ttl_expires`
  - `put_overwrites_prior_entry`
  - `invalidate_forces_next_lookup_to_miss`
  - `clear_empties_every_entry`
- All other suites unchanged.

## Hard-constraint compliance

- No push.
- Cache is in-process only; persisted contract
  (`vision_provider.json`) is untouched.
- No L5 audit changes; cache lookups produce no audit rows.
- No streaming / continuous capture; the cache front-ends a
  single-shot list endpoint.

## Risks / follow-ups

- 60 s TTL is a guess — easy to retune via `ModelListCache::with_ttl`.
- Cache uses `std::time::Instant`; tests inject `Instant::now()` via
  the `_with_now` helpers so we never sleep in tests. Production
  paths use the wall-clock helpers.
- The `↻` button lives next to the model strip; if the model strip
  is hidden because models is `null` (no active provider), the
  refresh button is hidden too — that's deliberate (nothing to
  refresh in text-only mode).
