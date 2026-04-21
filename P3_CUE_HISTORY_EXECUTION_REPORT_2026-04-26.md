# P3 — Per-panel cue history (2026-04-26)

## Goal

Make the camera + screen panels remember recent prompts so users can
re-run "describe what you see", "summarize this slide", etc. without
retyping.

## What shipped

### Frontend — `apps/desktop/src/lib/cueHistory.ts` (new)

- `CuePanel = "camera" | "screen"` — separate buckets per panel.
- `MAX_CUE_HISTORY = 5` cap, newest-first ordering.
- `applyCue(history, cue)` — pure projection used internally and
  exposed for unit tests once a Vitest harness lands. Rules:
  - empty / whitespace-only input is ignored,
  - duplicates are removed and the existing entry moves to the
    front (so re-using a cue re-prioritises it),
  - the list is capped at `MAX_CUE_HISTORY`.
- `readCueHistory(panel)`, `pushCue(panel, cue)`,
  `clearCueHistory(panel)` — localStorage-backed wrappers around
  `applyCue`. Resilient to SSR / no-localStorage / quota-exceeded.

### Frontend — `apps/desktop/src/components/CueHistoryStrip.tsx` (new)

- Tiny horizontal wrap of clickable chips. Hidden when the history
  is empty. `title` attribute carries the full cue so long entries
  remain inspectable when truncated.

### Frontend — `CameraPanel.tsx`, `ScreenPanel.tsx`

- Each panel hydrates its own history when opened.
- The strip is rendered immediately below the cue input.
- Click-to-fill repopulates the input — the user can still edit
  before submitting.
- History is saved **only on `frame_analyzed` outcomes** so
  permission refusals (`permission_denied`, `permission_ask`) and
  policy blocks don't pollute the list with stub strings the user
  never actually ran.

## Storage layout

```
window.localStorage["aether.cue-history.camera"] → JSON array
window.localStorage["aether.cue-history.screen"] → JSON array
```

Stored locally; never crosses the IPC boundary; never lands in the
durable conversation memory.

## Verification

- `pnpm typecheck && pnpm build` — clean.
- Type-driven correctness — `applyCue` is a pure function and
  `pushCue`/`readCueHistory` are exposed for the eventual Vitest
  pass.

## Notes for review

- **No backend changes.** Cue history is pure client-side state.
  The cue itself is the same string `analyze_frame` already
  receives, so no new IPC.
- **No Vitest setup this run.** Adding Vitest + a sample test was
  out of charter (avoid scope creep). When the harness lands, the
  pure `applyCue` is ready to wire up — covers the dedup, cap,
  empty-input, and ordering invariants in one file.
- **Per-panel separation is structural.** A future "Window" or
  "Mic" panel just adds a new `CuePanel` variant; the storage
  helper picks up the new key automatically.
