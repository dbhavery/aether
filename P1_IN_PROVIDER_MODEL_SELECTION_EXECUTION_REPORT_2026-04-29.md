# P1 — In-provider model selection — execution report (2026-04-29)

**Status:** Shipped, committed `c593e32` on `dev`. Push not authorized.

## Goal

Let the user pick a specific model on the active vision provider
(Ollama vision / llama.cpp vision) without restarting Aether, and
have the pick survive provider swaps and app restarts.

## Surfaces touched

- `packages/l4-router/src/vision.rs` — extends `VisionProvider` trait
  with `set_model(&self, id: &str) -> Result<(), L4Error>` (default
  `Ok(())`, no-op for passive adapters) and `current_model() ->
  Option<String>` (default `None`).
- `packages/l4-router/src/providers/ollama_vision.rs` and
  `llamacpp_vision.rs` — `model: String` becomes `model:
  RwLock<String>`, base_url and timeout stay immutable. Both adapters
  implement `set_model` (rejects empty/whitespace) and
  `current_model`. `analyze` and `label` read the live model so a
  swap is reflected immediately on the next call.
- `apps/desktop/src-tauri/src/vision_registry.rs` —
  `VisionPersistedState` grows `model_per_provider: BTreeMap<String,
  String>` (serde default for forward compat). `attach_persistence`
  reads the map and pushes each entry into its matching adapter.
  `set_active` reapplies the newly-active provider's persisted model.
  New `set_active_model(model)` swaps the active adapter's model and
  records it in the map. New `active_model()` reads the live adapter
  state so callers see what the next analyze will use.
- `apps/desktop/src-tauri/src/state.rs` — adds `vision_active_model`
  and `set_active_vision_model` accessors.
- `apps/desktop/src-tauri/src/commands.rs` — `VisionStatus` grows
  `active_model: Option<String>`. New `set_active_vision_model(id)`
  command validates against the active provider's most-recent
  list_models snapshot before swapping; empty/unavailable lists fall
  through to optimistic accept (the daemon's own error path catches
  real misses on the next analyze).
- `apps/desktop/src-tauri/src/main.rs` — registers the new command.
- `apps/desktop/src/lib/{api.ts,types.ts}` — exports
  `setActiveVisionModel` and adds `active_model` to `VisionStatus`.
- `apps/desktop/src/components/VisionBadge.tsx` — promotes the model
  strip from read-only chips to clickable buttons. The active model
  gets a green ring; other chips highlight on hover; both disable
  while a swap is in flight. Click → `set_active_vision_model` → live
  status update.

## Persistence wire shape

Old (still loads):
```json
{ "active": "ollama-vision" }
```

New (additive):
```json
{
  "active": "ollama-vision",
  "model_per_provider": {
    "ollama-vision": "llava:latest",
    "llamacpp-vision": "minicpm-v"
  }
}
```

`model_per_provider` defaults to `{}` on read so files written by
older builds keep loading. Unknown provider ids in the map are
retained (a future build that registers them inherits the pick) but
never panic the registry.

## Hot-swap semantics

- Per-call: in-flight `analyze_frame` keeps whatever model handle it
  captured on entry. Subsequent calls use the new model.
- Provider swap reapplies the new provider's last-known model via
  `set_model`; the adapter's live model state stays consistent with
  what the user picked.

## Tests

- `aether-l4-router` (with `ollama-provider,vision-llamacpp`): **57
  passing**, was 51. +6 new:
  - `ollama_vision::tests::set_model_round_trips_and_label_reflects_new_model`
  - `ollama_vision::tests::set_model_rejects_empty_id`
  - `ollama_vision::tests::build_vision_payload_uses_current_model_after_swap`
  - `llamacpp_vision::tests::set_model_round_trips_and_label_reflects_new_model`
  - `llamacpp_vision::tests::set_model_rejects_empty_id`
  - `llamacpp_vision::tests::build_vision_payload_uses_current_model_after_swap`
- `aether-desktop-shell` (with `ollama-provider,vision-llamacpp`):
  **60 passing**, was 54. +6 new:
  - `vision_registry::tests::set_active_model_writes_through_provider_and_map`
  - `vision_registry::tests::set_active_model_errors_when_no_active_provider`
  - `vision_registry::tests::provider_swap_preserves_each_providers_last_model`
  - `vision_registry::tests::persisted_model_map_round_trips_and_reapplies_on_reopen`
  - `vision_registry::tests::persisted_model_for_unknown_provider_is_retained_but_not_applied`
  - `vision_registry::tests::old_persistence_without_model_map_still_loads`
- `python tools/lint-layer-boundaries/check.py` → 0 violations.
- `apps/desktop && pnpm typecheck && pnpm build` → clean.
- `apps/desktop && pnpm test` → 41/41.

## Hard-constraint compliance

- No push.
- No release / distribution / signing work.
- No streaming or continuous capture.
- No microphone / voice / STT / TTS work.
- No broad settings redesign.
- `LlamaCppConfigError` and `OllamaConfigError` not unified.
- L5 `AuditRecordEvent` unchanged.
- Image bytes still transient (memory entries only carry the
  `[frame analysis · …]` cue, never raw pixels).
- `analyze_frame` trust/audit contract unchanged.

## Risks / follow-ups

- Validation against the daemon's model list is per-call today — P2
  caches it so the cost is borne at most once per TTL. See P2 report.
- The `↻` refresh affordance and cache live in P2.
- VisionBadge component test (P3) deferred — see handoff for the
  reasoning.
