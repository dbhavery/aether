# P2 / P6 — Onboarding autonomy-preset picker

**Date:** 2026-04-21
**Branch:** `dev`
**Scope:** Onboarding spec §Step 5 (preset picker). Step 1 already
scaffolded via `Disclosure.tsx` — left untouched.
**Layers touched:** apps/desktop shell (TS only).

## What shipped

- `PresetPicker.tsx` — modal that prompts for an autonomy preset
  (Observer / Assistant / Operator) after the welcome disclosure closes.
  Each preset renders with a tagline and a three-line "Can / Asks /
  Never" plain-language summary per onboarding spec §"Info-explainer on
  every option".
- "I'll decide later" button persists a `later` sentinel so the card
  doesn't re-surface every launch (spec §"No dead ends").
- Choice is stored in `window.localStorage` under
  `aether.onboarding.autonomy-preset` with a versioned companion key
  (`…-preset.version`). Bumping the version re-prompts all existing
  users if the preset taxonomy ever changes shape.
- `App.tsx` renders `<PresetPicker />` alongside `<Disclosure />`.
  Disclosure's `onClose` bumps a `disclosureCloseNonce` that is used
  as the PresetPicker's `key`, so when the user dismisses the welcome
  banner the picker remounts and re-checks localStorage — they
  sequence within a single first-run session instead of waiting for a
  second launch.
- `readStoredPreset()` export for future consumers. Returns
  `AutonomyPreset | "later" | null`.

## Intentional scope cuts vs the handoff backlog

- **localStorage instead of `tauri-plugin-store`.** The Disclosure
  component already uses `window.localStorage` for the acknowledgement
  flag. Adding `tauri-plugin-store` would require a new Rust plugin
  registration + `@tauri-apps/plugin-store` npm dep, both for a piece
  of state that the backend does not yet consume. When a later slice
  needs to *read* the preset from Rust (e.g. to seed
  `EngineConfig::with_persona_overlay`), we can move to
  `tauri-plugin-store` or a dedicated Tauri command at that point.
  Flagged in the risks section so morning review can reverse this if
  undesired.
- **Preset does not yet influence policy.** `EngineConfig::wave3_default`
  remains the source of truth server-side. Wiring the picker's choice
  into a `EngineConfig::with_preset_overlay` is a follow-up slice,
  separate from surfacing the choice.
- **Step 1 (welcome) not touched.** Already in `Disclosure.tsx`.

## Checks run

- `pnpm typecheck` — clean.
- `pnpm build` — 46 modules transformed (was 45), +25ms, +4 kB JS
  bundle. Expected given the new component.
- No Rust changes, so Rust checks not re-run for this slice — relying
  on the clean run from the P1 commit immediately prior.

## Risks / follow-ups

- **Backend is deliberately unaware of the user's choice.** If a user
  picks Observer and then tries to write a file, today's behaviour
  (policy evaluates against `wave3_default`) may surprise them. The
  next slice should wire preset → `EngineConfig::with_preset_overlay`
  through the same path `with_persona_overlay` already uses.
- **localStorage is per-webview-origin.** Nothing hostile here; a
  fresh install wipes it like any browser cache. If Don wants this
  preserved across reinstalls, move to Tauri-side storage later.
- **Two modals stacking on first launch.** Sequenced via the
  disclosure-close nonce; if that state ever gets lost (e.g. by an
  app crash between the two), the preset card will surface on the
  next launch.
- **Taglines are my guesses for each preset.** Worth Don-review — the
  onboarding spec is the doctrine but hasn't locked the exact copy.
