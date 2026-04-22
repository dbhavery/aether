# lint-vision-doc

Rot guard for [`docs/VISION-V1-ARCHITECTURE.md`](../../docs/VISION-V1-ARCHITECTURE.md).

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that the architecture doc claims exist in
code. If any anchor disappears (rename, delete, typo), the linter
fails.

## Run

```
python tools/lint-vision-doc/check.py          # human output
python tools/lint-vision-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## What it checks

- **FILE anchor** — the named file exists.
- **SYMBOL anchor** — a literal substring (e.g. `fn analyze_frame`,
  `struct VisionRequest`, `MEDIA_TURN_KINDS`) appears at least once
  in the named file.
- **STRING anchor** — a literal token (telemetry kind, env var
  name, provider id, config filename) appears at least once in the
  named file.
- **Doc header** — the doc has a parseable
  `**Status:** Current as of YYYY-MM-DD.` line near the top.

## What it does NOT check

- Whether the prose still matches the code.
- Whether newly-added behavior is reflected in the doc.
- Whether a freshly-introduced telemetry kind has been propagated
  into the manifest.

The anchor manifest is a **contract between the doc and the code**.
Keeping it honest is a human responsibility; the linter catches the
mechanical half.

## How to resolve a failure

A failure means one of the following:

1. You renamed or deleted a symbol in code without updating the
   doc. **Fix:** either restore the symbol, or update the doc prose
   AND the anchor manifest to reflect the rename/removal, and bump
   the doc's `Status: Current as of YYYY-MM-DD.` line.
2. You added a brand-new anchor to the doc but forgot to add it to
   the manifest. **Fix:** add the anchor entry to `ANCHORS` in
   `check.py`.
3. A file moved. **Fix:** update the path in the manifest.
4. The doc is missing the `**Status:**` header. **Fix:** add it
   back — the linter needs it to keep the doc self-dating.

## When to extend the manifest

Add a new entry to `ANCHORS` whenever the doc starts claiming a new:

- file path,
- function / struct / trait / const name,
- string constant that's part of a user-visible or cross-boundary
  contract (telemetry kind, env var, provider id, config filename).

Do **not** add anchors for:

- implementation details the doc does not name,
- prose-level descriptions,
- ephemeral state.

The goal is to keep the manifest small enough to maintain and
large enough to catch real drift.

## Why not integrate with `cargo test` or `pnpm test`?

Because this is a doc linter, not a code test. Running it from the
session check set and (future) CI pipeline is the right layer. A
code test failing on doc drift would be confusing; a doc-specific
linter is honest about its scope.
