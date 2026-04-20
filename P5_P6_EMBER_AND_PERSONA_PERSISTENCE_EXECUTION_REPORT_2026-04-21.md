# P5 + P6 — Ember persona + persona persistence

**Date:** 2026-04-21
**Branch:** `dev`
**Layers touched:** apps/desktop (Rust state + TS shell).

## Part A — P5: third persona "Ember" (Cautious)

Hard-coded a third entry in `default_catalog()`:

- **Ember** — Formal tone, Balanced verbosity, **Cautious stance**, Dry humor.
- Description: "Careful and deliberate. Asks before acting, prefers
  the safer path, declines risky tools."

Ember's Cautious stance flows through the existing
`EngineConfig::with_persona_overlay` path that landed in the persona
overlay slice (2026-04-20), so switching to Ember visibly tightens
Auto/Ask/Deny decisions without any further wiring.

`Humor::None` does not exist in `aether_l6_persona::Humor`; using `Dry`
is the closest match to the onboarding spec's "cautious / formal" tone.

Tests added:
- `default_catalog_contains_expected_persona_ids` asserts
  `["aurora", "sable", "ember"]` order.
- `ember_is_the_cautious_persona` asserts stance + display name.

## Part B — P6: persist active persona across launches

Persistence is TS-side (localStorage) for consistency with the
Disclosure/PresetPicker pattern, and to keep the Rust boot path env-var-
pure:

- `aether.persona.last` holds the last explicitly-chosen id.
- `App.tsx` boot: after loading the default banner, reads localStorage.
  If the stored id differs from the default and exists in the current
  catalog, calls `switch_persona(id)` before the UI renders.
- `handleSwitchPersona` writes the id every time the user picks one.
- Catalog-existence check prevents "unknown persona" errors after a
  catalog edit/downgrade — a removed persona silently falls back to
  the default.

`AETHER_PERSONA` env var still takes precedence at the Rust side via
`state.rs::pick_default`, so power-user override remains intact.
If env is set and localStorage disagrees, env wins (because the boot
banner already reflects the env choice; the localStorage check only
fires when stored ≠ current, and current is the env choice).

## Checks run

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean.
- `cargo test --workspace` — all pass.
- `cargo test` tauri default — 11 passed (was 9, +2 state tests).
- `cargo test --features ollama-provider` — 17 passed (was 15).
- `python tools/lint-layer-boundaries/check.py` — 0 violations.
- `pnpm typecheck` — clean.
- `pnpm build` — 46 modules transformed, bundle +~400 B.

## Risks / follow-ups

- **Boot restore does a second `switch_persona` call** when a non-default
  id is stored. That clears the memory store and rebuilds the engine —
  fine for v0, but it means every launch that uses a non-default
  persona goes through an extra IPC round trip. If this shows in perf
  profiling, the fix is to plumb a "preferred id" argument into the
  Rust boot path (a small Tauri command change).
- **localStorage vs tauri-plugin-store** — same tradeoff as the
  PresetPicker slice. If Don prefers plugin-store for all persistence
  we can unify in a later pass.
- **No UI cue when a stored persona is missing from the catalog.** It
  silently falls back; consider adding a transcript system message if
  that becomes surprising.
