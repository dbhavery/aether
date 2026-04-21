# P2 — Provider id vocabulary deduplication — execution report (2026-05-02)

**Status:** Shipped, committed `0276bf3` on `dev`. Push not authorized.

## Goal

Stop hard-coding the two vision provider ids
(`"ollama-vision"`, `"llamacpp-vision"`) and their short labels in
multiple TS sites. Adding a third adapter should be one edit, not
four.

## Before

Four sites duplicated the table:

- `mediaTurns.ts::VISION_PROVIDER_IDS` (set literal)
- `mediaTurns.ts::visionProviderShortLabel` (`switch` statement)
- `mediaTurns.ts::visionRouteSummary` (composed of the above)
- `ActiveVisionRoute.tsx::providerShortLabel` (its own `switch`)

A new adapter would have needed all four updated in lockstep with
no compiler help when one was missed.

## After

A new typed registry module `apps/desktop/src/lib/visionProviders.ts`
holds the single source of truth:

```ts
export const VISION_PROVIDER_REGISTRY: ReadonlyArray<{
  id: string;
  shortLabel: string;
}> = [
  { id: "ollama-vision",   shortLabel: "Ollama vision" },
  { id: "llamacpp-vision", shortLabel: "llama.cpp vision" },
];
```

Helpers `isVisionProvider(id)`, `visionProviderShortLabel(id)` and
the derived `VISION_PROVIDER_IDS: ReadonlySet<string>` consult the
registry.

## Surfaces touched

- `apps/desktop/src/lib/visionProviders.ts` (new) — registry +
  helpers + types.
- `apps/desktop/src/lib/visionProviders.test.ts` (new) — 7 cases
  locking the registry contract and helper behavior.
- `apps/desktop/src/lib/mediaTurns.ts`:
  - Drops the inlined id set + `switch` statement.
  - Re-exports `isVisionProvider`, `VISION_PROVIDER_IDS`,
    `visionProviderShortLabel` from `./visionProviders` for
    back-compat with `import { ... } from "../lib/mediaTurns"`
    consumers (TrustDrawer, mediaTurns.test.ts).
  - `visionRouteSummary` consumes the imported helper.
- `apps/desktop/src/components/ActiveVisionRoute.tsx`:
  - Imports `visionProviderShortLabel` from the shared module.
  - Local `providerShortLabel(id, label)` is now a thin wrapper
    that composes the shared lookup with the existing
    `label ?? id ?? "Vision"` fallback chain. Existing
    `ActiveVisionRoute.test.tsx` cases all still pass.

## Adding a third adapter from here

One row in the registry covers:

- `isVisionProvider`,
- `visionProviderShortLabel`,
- `visionRouteSummary` (Trust drawer badge),
- `tierChipForFooter` (transcript footer dedup),
- `providerShortLabel` (ActiveVisionRoute hint).

Rust ids must still be added on the Rust side
(`OllamaVisionProvider::id`, `LlamaCppVisionProvider::id`); a
future ts-rs codegen pass could close that loop. Documented as a
deferred follow-up.

## Tests

vitest **71 passing** (was 64, +7).

Full check matrix run before stopping — all green.

## Hard-constraint compliance

- No push.
- No new providers introduced.
- No L5 or persistence contract changes.
- No breaking changes to externally visible ids.
- No new test deps.
- Re-exports preserve back-compat with existing call sites.
