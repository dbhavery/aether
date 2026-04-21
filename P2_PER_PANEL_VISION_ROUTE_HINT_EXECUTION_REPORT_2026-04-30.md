# P2 — Per-panel active vision route hint — execution report (2026-04-30)

**Status:** Shipped, committed `06f2743` on `dev`. Push not authorized.

## Goal

Surface the current vision route at the point of action — the
Analyze button. Reading "→ Ollama vision · llava:latest" right above
the button removes the "scroll up to the badge" cost.

## Surfaces touched

- `apps/desktop/src/components/ActiveVisionRoute.tsx` (new) — small
  one-liner. Three states:
  - enabled + model id known: `→ <provider> · <model>`
  - enabled + adapter can't report a model: `→ <provider>`
  - text-only fallback: `→ Text-only fallback` (muted)
  - Pure helpers `formatRouteHint(status)` and
    `providerShortLabel(id, label)` exported for unit tests so the
    wording can be locked without rendering React.
- `apps/desktop/src/components/ActiveVisionRoute.test.tsx` (new) —
  8 tests covering all three render states + the short-label
  fallback chain.
- `apps/desktop/src/components/VisionBadge.tsx` — adds an optional
  `onRouteChanged?: () => void` prop. Fires after a successful
  provider swap, model swap, or refresh. Failures don't fire — the
  user-visible error line stays inside the badge. Existing badge
  tests still pass unchanged because the prop is optional.
- `apps/desktop/src/components/CameraPanel.tsx` and `ScreenPanel.tsx`
  — wire the new hint above the Analyze button. Each panel keeps a
  `routeKey` state, bumps it from `onRouteChanged`, and threads it
  to both the badge (`refreshKey`) and the hint (`refreshKey`) so
  they stay synchronised.
- `apps/desktop/src/components/CameraPanel.tsx` — incidental copy
  fix: the footer no longer claims "the model sees the note you
  wrote, not the pixels". Vision is wired now; the new copy reads
  "Frames are captured locally and handed to the active vision
  route shown above. Image bytes stay transient — only the cue and
  the model's reply are recorded."

## Why an `onRouteChanged` callback rather than polling

Polling would add request load to the daemon and feel slow on a
fresh swap. The badge is the only surface that mutates the route in
the panel; making it announce changes is cheap and explicit.
`refreshKey` then composes naturally with the panel-open lifecycle
(initial fetch happens on mount; subsequent fetches happen on bump).

## Tests

- `apps/desktop && pnpm test` → **56 / 56** (was 48, +8 in
  `ActiveVisionRoute.test.tsx`).
- `pnpm typecheck && pnpm build` → clean.

## Hard-constraint compliance

- No push.
- No streaming or continuous capture; the hint reads `vision_status`
  on mount and on `refreshKey` bump only.
- No privacy-posture changes; pixels still transient.
- No broad UI redesign — one new compact line per panel and one
  optional callback prop on the badge.

## Risks / follow-ups

- The hint refetches `vision_status` independently from the badge.
  That's two fetches per panel-open, but both are cheap (the badge
  also caches model lists separately). Could be coalesced if it ever
  becomes a concern.
- `providerShortLabel` ships hard-coded mappings for the two
  built-in adapter ids. A new adapter requires a one-line update
  here AND in `mediaTurns.ts::visionProviderShortLabel`. Documented
  as a dual-contract risk in the handoff (was already on the watch
  list).
