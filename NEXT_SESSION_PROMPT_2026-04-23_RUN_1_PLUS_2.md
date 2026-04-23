# Next session prompt — Run 1 (QE Current) + Run 2 (Memory Sweep)

Paste the fenced block below verbatim into a fresh Claude Code
session. It is designed for a multi-phase, multi-hour run that
closes two roadmap items in one sitting: Quality-Eval Tier 2B
(rot guard + doc flip) in Phase 1, then Memory V2 step 5
(retention sweep) per ADR-0001 in Phase 2.

---

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev

SESSION TYPE
- Multi-phase, multi-hour. Two roadmap runs bundled. Scope
  ambition: close Run 1 cleanly, then Run 2 per ADR-0001, then
  optionally one Tier-3 cleanup if time remains.
- Don has delegated tactical decisions within the bounds below.
  Do not block waiting for him on anything except the items in
  §RESERVED DECISIONS.

================================================================
§MANDATORY FIRST STEPS — run these before reading anything else
================================================================

1. `./scripts/current_status.sh`  (Windows fallback:
   `python scripts/current_status.py`)
   Paste the output. Do NOT restate status from memory. Repo beats
   prompt (Decision #32). If the script's output conflicts with
   anything below, trust the script and update this prompt
   instead of silently complying.
2. `git log --oneline -15`. Confirm ADR-0001 and
   `HANDOFF_2026-04-23_ADR_AND_ROADMAP.md` are in history.
3. Read, in order:
   - `HANDOFF_2026-04-23_ADR_AND_ROADMAP.md` (this session's
     starting state).
   - `docs/adr/ADR-0001-memory-domain-reconciliation.md`
     (authoritative for Phase 2).
   - `ROADMAP_2026-04-23_SIX_RUN_PLAN.md` (Runs 1 + 2 scope
     comes from here).
   - `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` (Phase 1 reconciles
     this).
   - `docs/MEMORY-V2-ARCHITECTURE.md` §§1, 3, 4, 10 item 5 (Phase 2
     builds the retention sweep).
   - `tools/lint-presence-doc/check.py` (Phase 1 mirrors this
     exactly).

================================================================
§STATUS CORRECTION (read first, supersedes any conflicting prompt)
================================================================

Verified subsystem state at session start (from the 2026-04-23
handoff — run `./scripts/current_status.sh` to confirm live):
- Vision V1, Voice V1, Presence V1 — closed, rot-guarded.
- Memory V2 steps 1–4 — COMPLETE.
- Memory V2 step 5 (retention sweep) — NOW UNBLOCKED by ADR-0001.
- Memory V2 steps 6–7 — pending, downstream of 5.
- Quality-Eval V1 — v1.3 complete (scaffold, adversarial, live
  Ollama, capture+replay, session-log importer). Doc still
  "design-only" — Phase 1 closes that.
- Spec package — glossary (gap #1) + NFR skeleton (gap #2) in.
- Default local model: gemma4 since 2026-05-17. Unverified on
  real workloads; fix is narrow if it misbehaves.
- ADR-0001 accepted: retire L2 kernel stub, relocate
  `MemoryDomain` to `packages/l2-memory/src/domain.rs`,
  `SessionMemoryStore` is the shared contract.
- Parallel-test flakes retired 2026-05-18; default parallelism
  is safe. Do NOT add `--test-threads=1` back.

================================================================
§DOCTRINE GROUNDING (compact; hard rules remain in force)
================================================================

Full text in `planning/00_VISION_AND_GUARDRAILS.md` and
`planning/01_product_doctrine.md`. Hard rules relevant to this
session:

- L5 is single writer for side effects; no direct executor calls
  outside `l5-policy`.
- Rot guards != acceptance criteria. Tests / evals enforce
  behavior; rot guards enforce doc↔code anchor presence. Do not
  collapse.
- Observation vs action: retention-sweep evictions ARE actions
  (memory mutates), so they emit L5 audit rows AND
  `memory_forgotten` telemetry. Not observation-only.
- No raw-media persistence. Transcript text is persistable;
  image/audio bytes are not.
- No silent fallback (Voice V1 contract, generalized).
- Additive by default — do not delete legacy files in `src/`,
  `desktop/`, `frontend/`, `configs/`, `tests/`, `scripts/`.
- Private assets (Isabelle-tagged) never enter public
  distributables.
- ADR-0001 authorises the Phase 2 cross-layer change
  (L2 + shell in one session). You do not need additional
  coordinator sign-off for that specific work.

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

1. Any doctrine-level change. Seven-layer structure.
   Product-tier boundaries. "No close-enough SaaS" rule scope.
2. Avatar / viseme / L3 social-behavior rendering.
3. Onboarding wizard redesign.
4. Forward-looking requirement IDs (Gap #3, GLOSSARY.md §11).
5. `docs/AC-STYLE.md` shape.
6. Any new `packages/*/` or `apps/*/` directory (`CLAUDE.md` §3).
7. Removing or weakening existing rot guards, tests, lints,
   or layer-boundary enforcement outside what Phase 1 / Phase 2
   EXPLICITLY require.
8. Gemma 4 rollback. If Gemma 4 misbehaves, document and leave
   the flip in place.
9. `git push`. Don handled (or deferred) push before the session.
   Do not push.
10. Embeddings shape (Run 3 scope). Phase 2 is NOT allowed to
    introduce an `EmbeddingStore` trait, an embeddings-specific
    file, or a retention path that reads embedding metadata.
11. Memory V2 step 6 or step 7. This session lands step 5 ONLY.

================================================================
§DELEGATED DECISIONS (you may decide; use best judgment)
================================================================

Within Phase 1 / Phase 2 scope:
- Anchor manifest contents (Phase 1). Seed the quality-eval rot
  guard from whatever symbols / file paths / strings the QE arch
  doc references.
- Trait/method shapes, module organisation, test patterns.
- Commit messages (follow the `<scope>: <subject>` + Co-Authored-By
  format already established).
- Which sub-tasks to drop if time is tight — drop the Tier-3
  cleanup first; never drop check-matrix verification.
- Execution reports and handoff content.
- Small helper scripts that support the work (none expected).
- Refactoring for readability within a single file (not structural).

================================================================
§PHASE 1 — Run 1 — Quality-Eval Tier 2B
================================================================

Target: close documentation drift on the subsystem that has moved
fastest (v1.0 → v1.3 shipped while doc stayed "design-only").

### Scope

1. `tools/lint-quality-doc/check.py` — mirror `tools/lint-presence-doc/check.py`
   exactly. Same CLI, same output format, same exit codes.
2. Anchor manifest covering the QE v1 / v1.1 / v1.2 / v1.3
   surface. Required anchors include (non-exhaustive — grep
   `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` for any file path or
   symbol name it mentions):
     - `tools/evals/__main__.py` and its `Scenario`,
       `ScenarioResult`, `_capture_filename`, `_write_capture_json`,
       `_load_replay_capture`, `_resolve_actual`, `_run_scenario`,
       `main`.
     - `tools/evals/expectations.py` and `EVALUATED_KINDS`,
       `evaluate_expectation`, `ExpectationResult`.
     - `tools/evals/report.py` and `build_markdown_report`.
     - `tools/evals/test_capture_replay.py` (v1.2 unit tests).
     - `tools/evals/session_log_import.py` and its
       `_parse_session_log`, `_pair_user_assistant`,
       `_extract_scenarios`, `match_scenario`, `import_session_log`,
       `ImportReport`, `SessionTurn`, `main`.
     - `tools/evals/test_session_log_import.py` (v1.3 unit tests).
     - `tools/evals/scenarios/` and at least one scenario per
       domain.
     - `tools/evals/adversarial/` and at least one probe per
       domain.
     - `AETHER_EVAL_OLLAMA_BASE_URL`, `AETHER_EVAL_OLLAMA_MODEL`,
       `AETHER_EVAL_OLLAMA_TIMEOUT_S` env var names.
     - Scenario JSONL fields: `id`, `domain`, `turns`, `actual`,
       `expectations`, `kind`, `patterns`.
     - Expectation kinds: `forbids`, `requires`, `length`, `tone`.
     - Backend tokens: `dry-run`, `ollama`, `replay`, `session-log`.
3. Flip `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` status from
   "Design-only as of 2026-05-14" (or whatever it says) to
   "Current as of 2026-04-23". Reconcile any drift surfaced by
   anchor seeding — the doc must describe what the code actually
   does, not what it was planned to do.
4. Full check matrix must stay green (see §CHECK MATRIX).

### Out of scope (Phase 1)

- `pnpm eval` regression harness wiring (Run 5 candidate).
- Any feature work on the eval harness. No new backends, no new
  expectation kinds, no new scenarios.
- Any new Tauri commands.
- Session-log-importer changes.

### Commit cadence

Two or three commits: rot guard → anchor seed → doc flip +
reconcile. Combine if the anchor set is small.

### Done when

- `python tools/lint-quality-doc/check.py` prints `OK` with an
  anchor count.
- `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` reads as current (no
  "design-only" or "will ship later" for features that have
  shipped).
- Existing three rot guards still pass.
- Full check matrix green.

================================================================
§PHASE 2 — Run 2 — Memory V2 step 5 (retention sweep)
================================================================

Target: implement the retention sweep per
`docs/MEMORY-V2-ARCHITECTURE.md` §10 item 5, executing ADR-0001
en route. Two sub-phases — 2a MUST land before 2b.

### Phase 2a — ADR-0001 execution (cross-layer, one commit)

1. Create `packages/l2-memory/src/domain.rs`. Export
   `MemoryDomain` with exactly the six shell-enum variants
   (`Session`, `Durable`, `Facts`, `Projects`, `Preferences`,
   `Artifacts`), the existing `const ALL`, the existing
   `label()`, and the existing `#[serde(rename_all =
   "snake_case")]` attribute. Full doc comment tying to
   MEMORY-V2-ARCHITECTURE.md §1.
2. Update `packages/l2-memory/src/lib.rs`: add
   `pub mod domain;` and `pub use domain::MemoryDomain;`.
   Remove kernel re-exports (`MemoryKernel`, `MemoryItem`,
   kernel `MemoryDomain`, `MemoryId`, `EmbeddingRef`,
   `EmbeddingStore`, `PrivacyClass`, `ProvenanceTag`,
   `RetentionKind`). Remove `pub mod kernel;`.
3. Delete `packages/l2-memory/src/kernel.rs`.
4. Update `apps/desktop/src-tauri/src/memory_config.rs`: delete
   the local `MemoryDomain` declaration. Import `MemoryDomain`
   from `aether_l2_memory`. Keep `MemoryRisk` as-is (it is
   policy config, not the taxonomy — ADR-0001 §Consequences).
5. Update all callsites: `memory_service.rs`, `commands.rs`,
   tests. The enum's public surface (variants, `ALL`,
   `label()`) does not change; only the import path does.
6. Verify: `cargo check --workspace`, `cargo test --workspace`,
   shell `cargo test --all-features`, `pnpm typecheck`.
   All green before moving to Phase 2b.

### Phase 2b — retention sweep implementation

Design reference: `docs/MEMORY-V2-ARCHITECTURE.md` §§3, 4, 10
item 5. `memory.json` already carries `retention_days` per
domain; the sweep honours it.

1. Extend `SessionMemoryStore` (or add a `RetentionSweep` trait
   — your call) with a `prune_before(session_id, cutoff_ms)`
   method that returns the number of rows evicted. Impl on both
   `InMemorySessionMemoryStore` and `SqliteSessionMemoryStore`.
   Unit tests for both.
2. Add a shell-level `AppState::run_retention_sweep()` method.
   Iterates all known session ids, reads `memory_config().retention_for(domain)`
   for each domain, computes the cutoff, calls `prune_before`,
   emits one `memory_forgotten` telemetry row per evicted
   item (or one aggregated row per sweep — your call, document
   it), and produces one L5 audit row per sweep invocation via
   the existing `MemoryForget` capability.
3. Wire the sweep to fire at boot (before the first command is
   served) and on a low-rate background tick. Tick rate: 1 hour
   is a sane default; lock the choice in a comment. Do NOT add
   a user-visible config for the tick rate in this phase.
4. `memory.json` format does NOT change. If a domain's
   `retention_days` is null, the sweep skips it.
5. Tests:
     - Unit: `prune_before` evicts rows older than the cutoff and
       leaves newer rows.
     - Unit: `run_retention_sweep` respects the per-domain
       `retention_days` map.
     - Unit: `null` retention means skip.
     - Integration: audit row + telemetry counts match the
       number of rows evicted.
     - Add the MemoryTab test's mock surface if `memory_list`
       was affected (it should not be).

### Out of scope (Phase 2)

- Embeddings (Run 3).
- Step 7 rot guard (Run 4).
- Any `MemoryKernel` trait resurrection.
- Any change to `memory.json` shape.
- Any change to `AuditRecordEvent` shape (hard constraint).
- Any user-sensitive domain default flip (Facts / Artifacts
  stay Ask).

### Commit cadence (Phase 2)

Two slices: (1) Phase 2a (ADR-0001 execution, single commit
crossing L2 + shell because it is a coherent rename/move),
(2) Phase 2b (sweep implementation, 1–2 commits: core sweep
then boot/tick wiring if they split cleanly).

### Done when

- `MemoryDomain` lives in L2; kernel.rs is gone; shell imports
  from L2.
- Retention sweep runs at boot + every hour.
- Sweep eviction produces telemetry + audit.
- Full check matrix green.
- `docs/MEMORY-V2-ARCHITECTURE.md` §10 item 5 no longer says
  "pending" (move it to the done list, or mark in place).

================================================================
§CHECK MATRIX — run after each phase, all green to proceed
================================================================

| Check | Expected |
| --- | --- |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --all-features` | new sweep tests pass |
| `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` | parallel pass (no `--test-threads=1`) |
| shell `cargo test --all-features` | all pass |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK |
| `python tools/lint-voice-doc/check.py` | OK |
| `python tools/lint-presence-doc/check.py` | OK |
| `python tools/lint-quality-doc/check.py` (NEW after Phase 1) | OK |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 FAIL (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | clean |
| `apps/desktop && pnpm test` | 185+ pass (Memory tab tests still green) |

================================================================
§TIER 3 — optional, one only if Phases 1 + 2 land cleanly with time
================================================================

Pick one. Do NOT bundle. Do NOT attempt without the check matrix
already green.

- A. **Flake-harness regression sweep.** Run the two
  previously-flaky tests 10 times each under default parallelism
  to confirm the 2026-05-18 fix is still holding.
- B. **Decisions log consolidation.** Cross-reference decisions
  #46–#52 against the code and mark any that have been
  superseded. Write a short `docs/DECISIONS.md` index.
- C. **Skip.** Clean handoff is more valuable than a half-done
  Tier-3 item. If in doubt, skip.

================================================================
§SESSION-END DISCIPLINE (mandatory)
================================================================

Before stopping:

1. Full check matrix from §CHECK MATRIX. All green.
2. Working tree clean.
3. One execution report per phase you finished
   (pattern: `MEMORY_V2_STEP2_EXECUTION_REPORT_2026-05-16.md`):
   - `QUALITY_EVAL_TIER_2B_EXECUTION_REPORT_2026-04-23.md` if
     Phase 1 landed.
   - `MEMORY_V2_STEP5_EXECUTION_REPORT_2026-04-23.md` if
     Phase 2 landed.
4. One consolidated session handoff
   `HANDOFF_2026-04-23_RUN_1_PLUS_2.md` covering:
   - commit table,
   - full check-matrix results,
   - post-session subsystem status (Memory V2 step 5 done;
     Quality-Eval rot guard live; doc flipped),
   - new risks / retired risks,
   - decisions log additions (#53 onward),
   - next recommended prompt (paste-verbatim for Run 3
     — Memory Retrieval / embeddings).
5. Consider: does the prior 2026-04-23 handoff still read
   correctly? If Phase 2 superseded Risk A, note it retired.

================================================================
§RETURN FORMAT
================================================================

When you stop, respond in this structure:

## Phase completion
- Phase 1 (QE Tier 2B): done / partial / blocked (reason)
- Phase 2a (ADR-0001 execution): done / partial / blocked
- Phase 2b (retention sweep): done / partial / blocked
- Tier 3 entered: yes (which) / no

## Commits
- SHA — message

## Full check matrix
- (list; all should be green)

## Subsystem status post-session
- Memory V2: step 5 done (or in-progress)
- Quality-Eval V1: rot-guarded, doc flipped
- Other subsystems: unchanged

## Risks / alerts for next session
- (new surfaces; retired handoff Risks A, B if applicable)

## Decisions log (new this session)
- #53 onward

## Anti-drift corrections
- (any stale prompt / memory-note corrections made in-flight)

## Next recommended prompt
(paste-verbatim, for Run 3 — Memory Retrieval / embeddings.
Shape it as its own multi-phase prompt if Phase 2 revealed
subtleties about the embeddings design.)

================================================================
§STANCE
================================================================

ADR-0001 is the authoritative reference for Phase 2. If Phase 2b
(the sweep) surfaces a reason to revisit the ADR, STOP and write
the handoff. Do not silently widen scope. "Partial scaffold with
a clear TODO beats fake completeness" (CLAUDE.md §9).

Ship Phase 1 cleanly. Execute Phase 2a as a single clean
cross-layer rename. Implement Phase 2b with tests for every new
path. Skip Tier 3 unless the rest is unambiguously done.

Good luck.
````

---

## How to use this file

1. Don does Run 0's manual steps (status, push, record the ADR —
   already done).
2. Paste the fenced block above into the next Claude Code session.
3. Agent executes both phases and writes a handoff with a Run 3
   prompt.

The Run 3 prompt will follow the same shape but target
embeddings. Run 4 (rot guard + doc flip) and Run 5 (one cleanup)
mirror this pattern.
