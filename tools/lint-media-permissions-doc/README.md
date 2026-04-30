# lint-media-permissions-doc

Rot guard for [`docs/MEDIA-PERMISSIONS.md`](../../docs/MEDIA-PERMISSIONS.md).

Mirror of `lint-voice-doc` and `lint-presence-doc`. See those READMEs for
the full rationale; the highlights:

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that `docs/MEDIA-PERMISSIONS.md` claims exist
in code (capability names, Tauri command names, wire-format labels,
vision env vars, the Tauri capability allowlist, the frontend
`VisionBadge` component, etc.). If any anchor disappears (rename,
delete, typo), the linter fails.

## Run

```
python tools/lint-media-permissions-doc/check.py          # human output
python tools/lint-media-permissions-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## Updating

When a media-permissions PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `check.py`.
2. Update `docs/MEDIA-PERMISSIONS.md` in the same PR.
3. Bump the doc's `**Status:** Current as of YYYY-MM-DD.` date.

This linter exists so silent drift between the doc and the code is
caught at `pnpm test`-adjacent speed, not during a future incident.
