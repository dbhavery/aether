# lint-voice-doc

Rot guard for [`docs/VOICE-V1-ARCHITECTURE.md`](../../docs/VOICE-V1-ARCHITECTURE.md).

Mirror of `lint-vision-doc`. See that README for the full rationale;
the highlights:

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that the architecture doc claims exist in
code. If any anchor disappears (rename, delete, typo), the linter
fails.

## Run

```
python tools/lint-voice-doc/check.py          # human output
python tools/lint-voice-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## Updating

When a Voice V1 PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `check.py`.
2. Update `docs/VOICE-V1-ARCHITECTURE.md` in the same PR.
3. Bump the doc's `**Status:** Current as of YYYY-MM-DD.` date.

This linter exists so silent drift between the doc and the code is
caught at `pnpm test`-adjacent speed, not during a future
incident.
