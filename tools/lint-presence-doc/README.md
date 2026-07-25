# lint-presence-doc

Rot guard for [`docs/PRESENCE-V1-ARCHITECTURE.md`](../../docs/PRESENCE-V1-ARCHITECTURE.md).

Mirror of `lint-vision-doc` and `lint-voice-doc`. See those READMEs
for the full rationale; the highlights:

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that the architecture doc claims exist in
code. If any anchor disappears (rename, delete, typo), the linter
fails.

The linter verifies **doc/code consistency**. It is **not** a
behavioural test — acceptance criteria for Presence V1 live in
the L3 unit tests (`cargo test -p aether-l3-presence`) and the
shell tests. Per `docs/GLOSSARY.md` §6, rot guards and AC are
deliberately distinct surfaces.

## Run

```
python tools/lint-presence-doc/check.py          # human output
python tools/lint-presence-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## Updating

When a Presence V1 PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `check.py`.
2. Update `docs/PRESENCE-V1-ARCHITECTURE.md` in the same PR.
3. Bump the doc's `**Status:** Current as of YYYY-MM-DD.` date.

This linter exists so silent drift between the doc and the code is
caught at `pnpm test`-adjacent speed, not during a future
incident.
