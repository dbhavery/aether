# P3 — Trust drawer model annotation — execution report (2026-04-30)

**Status:** Shipped, committed `49d0648` on `dev`. Push not authorized.

## Goal

Make Trust drawer history rows reflect the runtime vision route
*including the model* that actually served each media turn.

## Surfaces touched

### Backend

- `apps/desktop/src-tauri/src/state.rs` — `TelemetryEntry` grows
  `model: Option<String>` (skip_serializing if `None`, additive on
  the wire). Existing test sites updated to pass `model: None`.
- `apps/desktop/src-tauri/src/commands.rs`:
  - `maybe_apply_vision` returns `Option<String>` instead of `bool`.
    `Some(model_id)` when vision substituted content,  `None`
    otherwise. The model is captured **before** `provider.analyze`
    so a concurrent `set_active_vision_model` can't race it.
  - `analyze_frame` stamps the returned model into telemetry.
  - `finalize_turn` (text path) and the provider-error path leave
    `model = None` — the drawer never lies about which route ran.

### L5 audit contract — explicitly NOT touched

`AuditRecordEvent` still carries no provider/model info. Provider
and model specifics live in telemetry/runtime metadata; audit stays
policy-focused. This honours the §4 constraint from the handoff
("L5 policy audit remains policy-focused, provider/model specifics
come from telemetry/runtime metadata").

### Frontend

- `apps/desktop/src/lib/api.ts` — `TelemetryEntry` interface gains
  optional `model?: string`.
- `apps/desktop/src/lib/mediaTurns.ts` — new pure helper
  `visionRouteSummary(provider, model)`:
  - `Some "<provider> · <model>"` when both are known
  - `Some "<provider>"` when the provider is a known vision route
    but the model is missing/empty/whitespace-only
  - `null` when the provider is not a known vision route
- `apps/desktop/src/components/TrustDrawer.tsx`:
  - Badge text uses `visionRouteSummary(provider, model)`.
  - Body line replaces the long tier label with `<persona> ·
    <provider> · <model>` for vision turns; falls back to the long
    tier label only when model is absent (text-only / passive
    adapter / discovery failure).
  - Tooltip via local `visionRouteTitle(provider, model)` helper:
    `"Served by <provider> (<model>)"` or `"Served by <provider>"`.
  - Drops the now-unused `visionProviderShortLabel` import.

## Tests

- `aether-desktop-shell` (with `ollama-provider,vision-llamacpp`):
  **66 passing** (no count change — existing test sites updated to
  set `model: None` for backward-compatible construction).
- `apps/desktop && pnpm test`: **59 passing** (was 56, +3 cases on
  `visionRouteSummary` covering combined label, provider-only
  fallback, null for non-vision providers).
- `cargo fmt --all -- --check`, `cargo check --workspace`,
  `cargo test --workspace`, `python tools/lint-layer-boundaries`:
  all green.
- `pnpm typecheck && pnpm build`: clean.

## Hard-constraint compliance

- No push.
- No L5 audit contract changes.
- No broad UI redesign — the History row gains one extra
  `· <model>` segment in the body line and the badge swaps to a
  combined label.
- Image bytes still transient.
- No streaming/voice work.

## Risks / follow-ups

- The body-line model segment can grow long for verbose model ids
  (`qwen2.5-vl-72b-instruct-q4_k_m`). The line uses `break-all` so
  it wraps, not overflows. If it ever feels noisy, swap the body
  for the combined badge only.
- `visionRouteSummary` is the third helper in `mediaTurns.ts` that
  hard-codes the two known vision provider ids. Adding a third
  adapter means updating all three (`isVisionProvider`,
  `visionProviderShortLabel`, `visionRouteSummary`) — and the
  symmetric helper in `ActiveVisionRoute.tsx`. Documented in the
  handoff dual-contract list.
