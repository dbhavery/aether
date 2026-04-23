# lint-quality-doc

Rot guard for [`docs/QUALITY-EVAL-V1-ARCHITECTURE.md`](../../docs/QUALITY-EVAL-V1-ARCHITECTURE.md).

Mirror of `lint-vision-doc`, `lint-voice-doc`, and `lint-presence-doc`.
See those READMEs for the full rationale; the highlights:

## What it does

`check.py` carries a curated manifest of anchors — files, symbols,
and string constants — that the architecture doc claims exist in
code. If any anchor disappears (rename, delete, typo), the linter
fails.

Covers the full Quality-Eval v1.x surface as shipped:

- v1 scaffold — `tools/evals/__main__.py`, `expectations.py`,
  `report.py`, seed scenario + adversarial probes per domain.
- v1.1 — live Ollama backend hook (env vars, `_ollama_env`,
  `_ollama_generate`).
- v1.2 — capture + replay (`_write_capture_json`,
  `_load_replay_capture`, `test_capture_replay.py`).
- v1.3 — session-log importer (`session_log_import.py`,
  `test_session_log_import.py`).

The linter verifies **doc/code consistency**. It is **not** a
behavioural test — the eval runner itself enforces scenario
semantics (`python tools/evals/__main__.py --dry-run`), and the
unit tests (`test_capture_replay.py`, `test_session_log_import.py`)
enforce the harness behaviour. Per `docs/GLOSSARY.md` §6, rot
guards and AC are deliberately distinct surfaces.

## Run

```
python tools/lint-quality-doc/check.py          # human output
python tools/lint-quality-doc/check.py --json   # machine-readable
```

Exit codes:

- `0` — all anchors resolve.
- `1` — one or more anchors failed.
- `2` — could not locate workspace root.

## Updating

When a Quality-Eval PR adds, removes, or renames an anchor it MUST:

1. Update `ANCHORS` in `check.py`.
2. Update `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` in the same PR.
3. Bump the doc's `**Status:** Current as of YYYY-MM-DD.` date.

This linter exists so silent drift between the doc and the code is
caught at `pnpm test`-adjacent speed, not during a future
incident.
