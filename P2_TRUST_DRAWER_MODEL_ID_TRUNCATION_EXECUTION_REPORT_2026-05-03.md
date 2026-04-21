# P2 — Trust drawer long-model-id truncation — execution report (2026-05-03)

**Status:** Shipped, committed `b653e6a` on `dev`. Push not authorized.

## Goal

Stop verbose vision model ids
(e.g. `qwen2.5-vl-72b-instruct-q4_k_m`, 30 chars) from visually
dominating the Trust drawer history body line, while still keeping
the full id recoverable by the user.

## Before

The body line concatenated `persona_id · provider · model · tier`
inside a `font-mono text-[12px] break-all` div. With a long model
id the row would wrap to two lines, push provider out of frame on
narrow widths, and made the Trust drawer feel cramped.

## After

A new pure helper:

```ts
truncateForDisplay(s: string, max: number): string
```

— returns `s` unchanged when `s.length <= max`, otherwise returns
the first `max - 1` characters followed by `…` (so the result length
is exactly `max`). Tiny-max values are clamped to ≥1 so a non-empty
input never collapses to an empty output.

`TrustDrawer.tsx` wraps just the model id in a span:

```tsx
{e.model ? (
  <>
    {" · "}
    <span title={e.model}>
      {truncateForDisplay(e.model, MODEL_ID_DISPLAY_MAX)}
    </span>
  </>
) : null}
```

`MODEL_ID_DISPLAY_MAX = 28` — picked so:

- `llava:latest` (12) renders untouched.
- `qwen2.5-vl-72b-instruct-q4_k_m` (30) becomes
  `qwen2.5-vl-72b-instruct-q4…` (28) inline; full id is in the
  span's `title` attribute.

The span is the only thing wrapped — `persona_id`, `provider`, and
the trailing `tier` fallback render exactly as before. `break-all`
on the parent div is preserved so rows still wrap gracefully if the
unrelated fields are unusually long.

## How users still see the full id

Hover the truncated model id; the browser surfaces the `title`
attribute as a tooltip with the complete string. We deliberately did
not add a custom hover-card or click-to-expand surface — kept the
intervention to one helper + one call site, per scope guard.

## Surfaces touched

- `apps/desktop/src/lib/displayString.ts` (new) — pure helper,
  no React, no Tauri imports.
- `apps/desktop/src/lib/displayString.test.ts` (new) — 5 vitest
  cases (shorter-than-max, exactly-max, longer-than-max with
  ellipsis-and-length assertion, tiny-max clamp, empty input).
- `apps/desktop/src/components/TrustDrawer.tsx`:
  - Imports `truncateForDisplay`.
  - New `MODEL_ID_DISPLAY_MAX = 28` constant.
  - Body line of the `HistoryList` row swaps the inline
    `${e.model}` interpolation for a `<span title>` wrapper around
    the truncated value.

No other Trust drawer layout was refactored.

## Tests

vitest: **81 passing** (was 76, +5).

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 89/89
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 81/81

## Hard-constraint compliance

- No push.
- No new vision providers.
- No new test dependencies (vitest already installed; no new
  React-Testing-Library helpers needed).
- No L5 / persistence / streaming changes.
- No `vision_provider.json` shape changes.
- One helper + one call site — did not bleed into broader Trust
  drawer redesign.
