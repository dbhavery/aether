# Quality-Eval Tier 2B execution report — 2026-04-23

**Run 1 of six-run roadmap (2026-04-23).** Closes documentation
drift on the subsystem that moved fastest (v1.0 → v1.3 shipped
while the architecture doc stayed "design-only").

## What shipped

| SHA | Subject |
| --- | --- |
| `4b0a5ce` | feat(tools): lint-quality-doc rot guard + flip QE doc to Current |

One commit covering:

- `tools/lint-quality-doc/check.py` — mirror of
  `tools/lint-presence-doc/check.py`. Same CLI (`--json`), same
  output format, same exit codes.
- `tools/lint-quality-doc/README.md` — mirror of
  `tools/lint-presence-doc/README.md`, adapted for the QE
  surface.
- Anchor manifest: **60 anchors across 19 files.** Covers:
    - v1 scaffold: `__main__.py` (Scenario, ScenarioResult,
      _iter_scenarios, _last_user_prompt, _resolve_actual,
      _run_scenario, main), `expectations.py` (EVALUATED_KINDS,
      ExpectationResult, evaluate_expectation), `report.py`
      (build_markdown_report).
    - v1.1 live Ollama: `_ollama_env`, `_ollama_generate`, three
      env-var names (`AETHER_EVAL_OLLAMA_BASE_URL`,
      `AETHER_EVAL_OLLAMA_MODEL`, `AETHER_EVAL_OLLAMA_TIMEOUT_S`).
    - v1.2 capture + replay: `_capture_filename`,
      `_write_capture_json`, `_load_replay_capture`,
      `test_capture_replay.py`.
    - v1.3 session-log importer: `session_log_import.py`
      (SessionTurn, ImportReport, _parse_session_log,
      _pair_user_assistant, _extract_scenarios, match_scenario,
      import_session_log, main), `test_session_log_import.py`.
    - Expectation kind strings (`forbids`, `requires`, `length`,
      `tone`) + `patterns` key.
    - Backend tokens (`dry-run`, `ollama`, `replay`,
      `session-log`).
    - Scenario JSONL field names (`id`, `domain`, `turns`,
      `actual`, `expectations`).
    - One seed scenario per domain + one adversarial probe per
      domain (12 scenario files anchored).
    - `tools/evals/README.md` pointer.
- `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` — status flipped from
  "Design-only as of 2026-05-14" to **"Current as of 2026-04-23"**.
  §3 rewritten to describe the shipped harness (layout +
  live-backend config + capture/replay) instead of a proposed
  runner. §6 roadmap: steps 1–6 marked ✅; step 7 ("Regression
  harness + `pnpm eval`") remains pending.
- `tools/evals/README.md` — roadmap section updated: items 6 + 7
  (session-log importer, rot guard) now marked shipped; item 8
  (`pnpm eval`) remains the one open slice.

## Reconciled drift

During anchor seeding the following design-vs-code deltas surfaced
and were reconciled by rewriting the doc (not changing code):

- §3 described a planned `runner.py` module that never shipped —
  `__main__.py` is the single file that loads scenarios, resolves
  `actual`, and runs expectations. Rewritten to describe the
  actual module layout.
- §3 didn't mention the v1.1 live Ollama hook, the v1.2 capture
  directory schema, or the v1.3 session-log importer. All three
  are now canonical §3 content.
- §6 listed step 5 as "Replay harness. Import-from-session-log
  command" and step 7 as regression harness. Actual sequencing
  shipped as v1.2 capture/replay → v1.3 session-log importer →
  Tier 2B rot guard. Roadmap renumbered to match reality.
- §7 previously said "Until step 6 lands the rot guard, this is a
  design doc". The rot guard IS step 6 today; prose updated to
  describe ongoing enforcement rather than a pending flip.

No code behaviour changed in this commit.

## Check matrix (all green)

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l4-router --features …` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --all-features` | 198 / 198 |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `python tools/lint-quality-doc/check.py` (NEW) | **OK (60 anchors / 19 files)** |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 fail (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 / 68 kB |
| `apps/desktop && pnpm test` | 185 / 185 |

## Done-when checklist

- [x] `tools/lint-quality-doc/check.py` prints `OK` with an
      anchor count.
- [x] `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` reads as current (no
      "design-only" or "will ship later" claims for shipped
      features).
- [x] Existing three rot guards still pass.
- [x] Full check matrix green.
- [x] Scope bounded — no new backends, no new expectation kinds,
      no feature work on the eval harness.

## Out of scope (intentional)

- `pnpm eval` regression harness wiring — Run 5 Option B candidate.
- Any feature work on the eval harness.
- Any new Tauri commands.
