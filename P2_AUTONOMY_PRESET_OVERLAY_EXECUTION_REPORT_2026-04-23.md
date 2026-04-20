# P2 Execution Report — Wire onboarding preset into engine policy

**Date:** 2026-04-23
**Scope:** `packages/l5-policy/` + `apps/desktop/` — make the autonomy
preset picker actually change engine behaviour instead of being a
cosmetic localStorage value.

## Summary

### L5 policy — new overlay primitive
- New `AutonomyPreset` enum in `engine.rs` (`Observer | Assistant | Operator`)
  with `wire_name()` / `from_wire()` helpers matching the PresetPicker's
  localStorage wire strings.
- New `EngineConfig::with_preset_overlay(preset)` chainable constructor
  that runs *after* `with_persona_overlay`:
  - **Observer** — every capability except `FilesRead` is pinned to
    `Deny`. Shell and writes are locked down regardless of persona.
  - **Assistant** — baseline no-op (recommended posture).
  - **Operator** — `FilesRead` and `FilesCreate` promoted to `Auto`;
    `ShellExec` is pinned to `Deny` (shell access is not unlocked by
    the preset alone). `FilesEdit` / `FilesDelete` / `BrowserOpen`
    retain their persona-adjusted mode.
  - Updates `preset` id to `wave3.<wire_name>` so audit rows + events
    surface which preset is active.
- Risk classes are never modified — risk is a property of the action,
  not the presentation.
- Five new unit tests:
  - `preset_overlay_observer_denies_every_write_and_shell`,
  - `preset_overlay_assistant_is_baseline_noop`,
  - `preset_overlay_operator_auto_approves_read_and_create_but_not_shell`,
  - `preset_overlay_runs_after_persona_and_wins`,
  - `autonomy_preset_wire_names_round_trip`.

### Desktop shell — consume the overlay
- `AppState` carries a new `preset: RwLock<Option<AutonomyPreset>>`.
- `build_active(profile, memory, preset)` applies the overlay after the
  persona overlay.
- New public methods:
  - `AppState::current_preset()`,
  - `AppState::apply_preset(preset)` — updates the stored preset and
    rebuilds the active engine without clearing session state (preset
    changes are non-destructive).
- `switch_persona` now re-applies the current preset so the overlay
  survives persona switches.
- Two new Tauri commands registered in `main.rs`:
  - `set_autonomy_preset(preset: Option<String>) -> CompanionBanner`
    accepts `"observer" | "assistant" | "operator" | "later" | null`.
    `"later"` and `null` both mean "no overlay". Unknown values are
    rejected.
  - `current_autonomy_preset() -> Option<String>` returns the live wire
    string.
- Two new shell tests:
  - `apply_preset_observer_denies_write_capabilities` drives a
    `FilesEdit` turn through the engine under Observer + Bold (Sable)
    persona and asserts `Decision::Deny`.
  - `preset_persists_across_persona_switch` confirms switching persona
    does not silently drop the overlay.

### Frontend — push the choice through
- `apps/desktop/src/lib/api.ts` — `setAutonomyPreset(preset)` and
  `currentAutonomyPreset()` invoke helpers.
- `PresetPicker.tsx` — `choose()` fires `setAutonomyPreset(selected)`;
  `decideLater()` sends `null` to clear any prior overlay. Stale
  comment about the backend not consuming the preset replaced with
  accurate wiring note.
- `App.tsx` boot path — reads `readStoredPreset()` and calls
  `setAutonomyPreset(...)` so the engine picks up the user's prior
  choice on every launch. Captures the updated `CompanionBanner` so
  the header reflects any preset-effective metadata.

## Behaviour change

Picking **Observer** now actually prevents writes, edits, deletes, and
shell. Picking **Operator** now actually auto-approves file creation
(but still blocks shell). Persona switches and app restarts carry the
preset forward. Clear semantics for "I'll decide later" — no overlay.

## Checks run

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | ok |
| `cargo test --workspace` | all green |
| `cargo test -p aether-l5-policy --lib` | 11/11 ok (up from 6) |
| `cargo test -p aether-l2-memory --features sqlite-backend` | 5/5 ok |
| `apps/desktop/src-tauri && cargo test` | 17/17 ok (up from 15) |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | clean |

## Risks / notes

- Persona overlay can still widen Operator semantics (e.g. a Bold
  persona could Auto FilesEdit even when the baseline says Ask), but
  Observer hard-Denies so user intent wins on the tight end. If we
  later want Observer/Operator to be strict bi-directional clamps, we
  can inline that by running the preset overlay with clamp-style logic
  rather than per-variant match arms.
- `set_autonomy_preset` rebuilds the active engine (new policy engine,
  new audit store, new turn engine), which wipes any in-flight
  approvals. Intentional — preset changes must take effect atomically.
- The `later` sentinel maps to no overlay; this is distinct from
  "Assistant" which is a baseline no-op. Both happen to produce the
  same `preset_defaults`, but only Assistant updates the preset id to
  `wave3.assistant` — `later`/`null` leave it as the persona-adjusted
  `wave3.balanced` default.

## Next (per handoff)

P3 — Persona-switch system-message banner. Currently `switch_persona`
silently wipes session memory; emit a transcript system-role message
so the user sees the state change.
