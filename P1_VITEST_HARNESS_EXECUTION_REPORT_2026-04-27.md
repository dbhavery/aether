# P1 — Vitest harness + multimodal pure-logic tests (2026-04-27)

## What shipped

### Harness

- `vitest@^2` (Vite-5 compatible) + `jsdom` added as dev dependencies.
- `apps/desktop/vitest.config.ts` — minimal config: `jsdom` env, picks
  up `src/**/*.test.ts(x)`, no global API exposure.
- `package.json` scripts: `test` (run) and `test:watch`.

### Tests landed

- `apps/desktop/src/lib/cueHistory.test.ts` — 18 tests.
  - `applyCue` (pure) — empty / whitespace ignored, trim before
    storing, prepend new, dedup-with-recency-wins, trimmed-equal
    duplicate, `MAX_CUE_HISTORY` cap, no-op when already at front,
    no input mutation.
  - `pushCue` / `readCueHistory` (localStorage) — empty default,
    per-panel persistence, panel isolation, cap respected, dedup
    moves to front, empty pushes ignored, `clearCueHistory`
    targeting, malformed-blob fallback, non-string entries filtered.
- `apps/desktop/src/lib/mediaTurns.test.ts` — 13 tests (later 23
  after P3 additions).
  - `MEDIA_TURN_KINDS` — exact contract with the four Rust kinds.
  - `isMediaTurn` — table-driven inclusion + exclusion (empty
    string, near-miss extras, case sensitivity).

### Refactor (narrow, in service of testability)

- Extracted `MEDIA_TURN_KINDS` / `isMediaTurn` from
  `TrustDrawer.tsx` to `apps/desktop/src/lib/mediaTurns.ts`. The
  TrustDrawer module still re-exports both names for back-compat.

## Verification

- `pnpm test` — **31 / 31** initially; grew to **41 / 41** after the
  P3 vision-provider helper tests landed in the same module.
- `pnpm typecheck` — clean.
- `pnpm build` — clean.

## Notes for review

- **Vite 5 vs Vitest 4 incompatibility.** Vitest 4 requires Vite
  ≥6; the repo is on Vite 5. Pinned Vitest to `^2` for compatibility
  without forcing a Vite upgrade. When the project moves to Vite 6+,
  bump Vitest in the same change.
- **No React Testing Library.** Out of scope this run. Pure logic
  only — `cueHistory.ts` and `mediaTurns.ts`. Component tests are a
  separate decision.
- **`globals: false`** in the Vitest config. Tests import `describe`,
  `it`, `expect` explicitly so the global type pollution stays out
  of `tsconfig`.
