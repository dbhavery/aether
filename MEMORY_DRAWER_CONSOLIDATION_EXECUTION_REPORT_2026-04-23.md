# MemoryDrawer ↔ MemoryTab consolidation — execution report 2026-04-23

**Run 5 (Option A) of six-run roadmap 2026-04-23.** Closes the
roadmap with a small UX cleanup: retire the legacy v0
`MemoryDrawer` and make the Trust drawer's Memory tab the single
canonical entry point for "what does Aether remember about me".

## What shipped

| SHA | Subject |
| --- | --- |
| (this commit) | feat(ui): consolidate Memory entry point |

Single scoped commit covering:

### Component changes

- **Delete** `apps/desktop/src/components/MemoryDrawer.tsx`
  (92 lines). The v0 drawer showed only the session transcript
  window with a hard-coded "Durable memory inspection, editing,
  and export are on the roadmap" footer note. Memory V2 step 4
  shipped all that behaviour — per-domain lanes, forget, edit,
  approval modals — in `MemoryTab.tsx` inside the Trust drawer.
- **`TrustDrawer.tsx`**: add optional `initialTab?: Tab` prop.
  Re-applied on each `open: false → true` transition so the
  header's Memory button lands on Memory even after the user
  previously switched tabs and closed the drawer. Preserves v0
  "defaults to Audit" behaviour when the prop is omitted.
- **`App.tsx`**: drop the `MemoryDrawer` import + JSX block.
  The existing `drawer === "memory"` state now renders
  `<TrustDrawer initialTab="memory">`, and `drawer === "trust"`
  renders `<TrustDrawer>` (defaulting to Audit). Both map to the
  same component — the drawer state machine retains its existing
  string labels; only the render path changed.

### Test changes

- **New** `apps/desktop/src/components/TrustDrawer.test.tsx`
  locking the `initialTab` contract. Three cases:
  - defaults to Audit when no `initialTab` is set,
  - opens on Memory when `initialTab="memory"`,
  - re-applies `initialTab` on an open-false → open-true
    transition (the "close and reopen via the Memory button"
    flow).
- `api` module mocked at the test boundary — assertions are
  against `role="tab"` + `aria-selected`, not implementation
  details.

### Docs

None in this commit. The Memory V2 architecture doc already
references `MemoryTab.tsx`, `TrustDrawer.tsx`, and
`SettingsDrawer.tsx` as the §6 UI surfaces (anchored by
`tools/lint-memory-doc/check.py`); the retired component was not
anchored, so the rot guard stays green by construction.

## Check matrix

Narrow subset appropriate for a frontend-only change:

| Check | Result |
| --- | --- |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm test` | **188 / 188** (was 185, +3 TrustDrawer tests) |
| `apps/desktop && pnpm build` | 235 / 68 kB (was 237 / 68 kB — `MemoryDrawer.tsx` deleted) |

The Rust tree was not touched — `cargo` checks and the five rot
guards were not re-run and remain valid from the prior Run 3 + 4
session's check matrix.

## Done-when checklist

- [x] Exactly one entry point to the Memory surface (the Trust
      drawer's Memory tab).
- [x] `MemoryDrawer.tsx` deleted; no other references remain in
      the source tree.
- [x] Vitest suite green, including the new `initialTab` contract.
- [x] `pnpm typecheck` + `pnpm build` clean.
- [x] Memory V2 rot guard still passes (no anchored file was
      touched; re-verified at session end).

## Decisions in-flight

- **Keep `drawer === "memory"` vs. `drawer === "trust"` as
  distinct state values** rather than collapsing to a single
  `"trust"` state with a separate `trustInitialTab`. Rationale:
  the header button semantics stay explicit (`onOpenMemory` vs.
  `onOpenTrust`), the state machine reads the same way, and a
  future "close the drawer AND remember which entry opened it"
  behaviour becomes trivial.
- **Re-apply `initialTab` on every open transition**, not just
  on mount. Trust-drawer instances outlive individual open/close
  cycles; without the effect, a user would see their last-viewed
  tab after reopening via the Memory button. The targeted test
  covers this.

## Out of scope

- Runtime user-config persistence of drawer-tab preferences.
- Any Memory V2 behavioural change.
- Header button relabelling or keyboard shortcut changes.
- Rust-side work.
