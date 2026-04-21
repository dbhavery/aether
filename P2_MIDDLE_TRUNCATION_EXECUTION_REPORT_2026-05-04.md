# P2 — Trust drawer middle-truncation — execution report (2026-05-04)

**Status:** Shipped, committed `b2ee7ff` on `dev`. Push not authorized.

## Goal

Stop dropping the suffix of long, filename-style model ids when the
Trust drawer truncates them. The 2026-05-03 polish round added
prefix-truncation (`qwen2.5-vl-72b-instruct-q4_k_m` →
`qwen2.5-vl-72b-instruct-q4…`) which hid the most informative part
of the id — the quantization tag (`q4_k_m`).

## Before

`MODEL_ID_DISPLAY_MAX = 28` with prefix-truncation:

```
qwen2.5-vl-72b-instruct-q4_k_m  (30) → qwen2.5-vl-72b-instruct-q4…
```

The `_k_m` quantization detail is gone.

## After

A second helper sits beside the existing one in the same module:

```ts
truncateMiddleForDisplay(s: string, max: number, suffixLen = 8): string
```

- Returns `s` unchanged when `s.length <= max`.
- Otherwise returns `<prefix>…<suffix>` where `suffix` is the last
  `suffixLen` chars and `prefix` fills the rest, so the result
  length is exactly `max`.
- `max` is clamped to ≥ `suffixLen + 2` so the prefix always gets
  at least one character — never collapses to `…<suffix>`.

`MODEL_ID_DISPLAY_MAX = 28` is unchanged. With `suffixLen = 8`:

```
llava:latest                    (12) → llava:latest          (untouched)
qwen2.5-vl-72b-instruct-q4_k_m  (30) → qwen2.5-vl-72b-inst…t-q4_k_m (28)
```

The quantization tag survives. `truncateForDisplay` (the prefix
helper) stays exported — it's still useful for cases where the
suffix is not load-bearing.

## Surfaces touched

- `apps/desktop/src/lib/displayString.ts`:
  - New `truncateMiddleForDisplay` next to the existing
    `truncateForDisplay`. Pure data, no React.
- `apps/desktop/src/lib/displayString.test.ts`:
  - 4 new vitest cases: shorter-than-max no-op, long quantized id
    suffix preserved, tiny-max clamp behavior, empty input.
- `apps/desktop/src/components/TrustDrawer.tsx`:
  - Import swap from `truncateForDisplay` →
    `truncateMiddleForDisplay`. Single call site change.
  - `MODEL_ID_DISPLAY_MAX` constant unchanged.
  - `title` attribute on the wrapper span continues to carry the
    full id for hover recovery.

No other Trust drawer layout was touched.

## Tests

vitest: **85 passing** (was 81, +4).

Full check matrix run before stopping — all green:

- `cargo fmt --all -- --check`
- `cargo check --workspace`
- `cargo test --workspace`
- `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp` → 57/57
- `apps/desktop/src-tauri && cargo test --features ollama-provider,vision-llamacpp` → 89/89
- `python tools/lint-layer-boundaries/check.py` → 0 violations
- `apps/desktop && pnpm typecheck && pnpm build && pnpm test` → 85/85

## Hard-constraint compliance

- No push.
- No new vision providers.
- No new test deps.
- One helper + one call site swap — did not bleed into broader
  Trust drawer redesign.
- L5 / persistence / streaming / `vision_provider.json` all
  unchanged.
