# lint-memory-doc

Rot guard for [`docs/MEMORY-V2-ARCHITECTURE.md`](../../docs/MEMORY-V2-ARCHITECTURE.md).

Mirror of `lint-vision-doc`, `lint-voice-doc`, `lint-presence-doc`,
and `lint-quality-doc`. See those READMEs for the full rationale;
the highlights:

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that the architecture doc claims exist in
code. If any anchor disappears (rename, delete, typo), the linter
fails.

Covers the full Memory V2 surface as shipped through step 6:

- §1 six-domain taxonomy (ADR-0001 relocation — `packages/l2-memory/src/domain.rs`).
- §3 policy surface (`memory.json`, `MemoryConfig`, `MemoryRisk`,
  `EmbeddingsConfig`).
- §4 L5 capabilities (`MemoryRead`, `MemoryWrite`, `MemoryForget`,
  `MemoryEdit`, `MemoryEmbed`).
- §5 telemetry kinds (all six Memory-V2 kinds + the step-6
  `memory_embedded`).
- §6 UI surfaces (Memory tab, Trust drawer, Settings drawer).
- §10 step 4 (session store remove/update), step 5 (retention
  sweep — `prune_before`, `list_sessions`, `run_retention_sweep`,
  `RETENTION_SWEEP_INTERVAL_MS`, `run_retention_sweep_loop`),
  step 6 (embeddings module + traits + Ollama provider defaults).
- ADR-0001 + ADR-0002 existence.

The linter verifies **doc/code consistency**. It is **not** a
behavioural test — that lives in unit + integration tests across
`packages/l2-memory`, `packages/l5-policy`, and
`apps/desktop/src-tauri`. Per `docs/GLOSSARY.md` §6, rot guards
and AC are deliberately distinct surfaces.

## Run

```
python tools/lint-memory-doc/check.py          # human output
python tools/lint-memory-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## Updating

When a Memory V2 PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `check.py`.
2. Update `docs/MEMORY-V2-ARCHITECTURE.md` in the same PR.
3. Bump the doc's `**Status:** Current as of YYYY-MM-DD.` date.

Steps 7+ (future waves) should extend this manifest, not clone it.
