# P1 — Transcript tier dedup on vision turns — execution report (2026-05-02)

**Status:** Shipped, committed `ef0689c` on `dev`. Push not authorized.

## Goal

Stop the assistant message footer from rendering near-duplicate
chips on vision turns.

## Background

`maybe_apply_vision` in `commands.rs` overwrites
`route.tier = label` with the active vision provider's full
`label()` string — e.g. `"Ollama vision · llava:latest ·
http://127.0.0.1:11434"`. With the model chip from the prior
session, footer chips on vision turns read like:

> Ollama vision · llava:latest · http://127.0.0.1:11434 ·
> ollama-vision · llava:latest · 1.5s · p256/c12 tok

Provider id, model, and the URL noise all overlap. The dedicated
provider + model chips already say everything the long tier says,
without the URL.

## Surfaces touched

- `apps/desktop/src/components/Transcript.tsx`:
  - New pure helper `tierChipForFooter(meta) -> string | null`:
    - returns `null` when `meta.tier` is missing
    - returns `null` when `meta.provider` is a known vision id
      (drops the chip entirely on those turns)
    - returns `meta.tier` verbatim otherwise
  - `buildMetaParts(meta)` calls the helper instead of unconditionally
    pushing `meta.tier`. Order is unchanged; only the inclusion
    rule for the tier slot moves.
  - Reuses the shared `isVisionProvider` from
    `lib/visionProviders` — the dedupe stays in lockstep with the
    provider-id vocabulary.

## Result

Vision turn footers now read:

> ollama-vision · llava:latest · 1.5s · p256/c12 tok

Text-only (reflex / Ollama text) footers are unchanged — `tier`
still adds info there (`local`, `reflex-stub`).

## Tests

`Transcript.test.tsx` updated:

- existing vision-turn case now asserts the dropped tier
- new case for `llamacpp-vision` (parallel coverage)
- new case for text-only turn (`tier: "local"` preserved)
- new direct `tierChipForFooter` block:
  - null when tier missing
  - preserves tier on text-only / reflex / no-provider rows
  - drops tier on `ollama-vision` and `llamacpp-vision`

vitest 76 passing (was 71, +5).

Full check matrix run before stopping — all green.

## Hard-constraint compliance

- No push.
- No L5 / persistence / streaming changes.
- No new providers; the helper consults the existing shared
  vocabulary.
- Wire types unchanged — only chip rendering shifted.
- No new test deps.
