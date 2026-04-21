# P3 — Telemetry filter UI (media turns) (2026-04-25, late evening)

## Goal

Make it easy for reviewers to inspect camera + screen frame turns
on the Trust drawer's History tab — independent of how chatty the
text path has been.

## What shipped

### Frontend — `apps/desktop/src/components/TrustDrawer.tsx`

- New `MEDIA_TURN_KINDS` constant + `isMediaTurn(kind)` helper.
  Single source of truth for "which telemetry kinds came from
  `analyze_frame`?". Mirrors the four string constants the Rust
  `analyze_frame` command produces (`frame_analyzed`,
  `frame_blocked`, `permission_denied`, `permission_ask`).
- New `HistoryView` wrapper inside the History tab, with an
  All / Media-only `FilterPill` toggle. Pill labels carry the
  current count for each bucket so users see at a glance how
  much of the buffer is media work.
- Empty-state copy adapts to the active filter — "No media turns
  yet. Open the Camera or Screen panel and analyze a frame."
- `kindClass` extended so:
  - `frame_analyzed` → green (ok),
  - `frame_blocked` / `permission_denied` → red,
  - `permission_ask` → amber.

## Backend story

No backend work needed — the `kind` string field on
`TelemetryEntry` already carried the four media kinds (added in
the P3 multimodal-foundation slice earlier today). The filter is a
pure client-side projection over the existing telemetry buffer.

## Verification

- `apps/desktop && pnpm typecheck && pnpm build` — clean.

## Notes for review

- `MEDIA_TURN_KINDS` is the contract. If the Rust command surface
  ever adds a new media `kind` (e.g. `mic_analyzed`), update both
  the Rust command and this set.
- Counts in the pill labels reflect what's in the (in-memory,
  capped at 50) telemetry buffer — not the lifetime total.
