# Handoff — 2026-04-24 Milestone 2 Mini-Run 0

**Written:** 2026-04-24 mid-session (post-planning, pre-Run-1).
**Branch:** `dev`. Tip `344fbcf` at Mini-Run 0 start → (this commit) at end.
**Working tree:** clean after this handoff commit.
**Session type:** research + ADR + default constant swaps. Net new: 1 ADR,
2 Rust constants + 1 doc-string per file across L2/L4, 1 Python eval default,
5 architecture-doc lines, 1 test fixture literal, 1 roadmap amendment,
this handoff.

---

## 1. Commit table

| SHA | Subject |
| --- | --- |
| `344fbcf` (earlier this session) | chore: silence CRLF warnings + current_status reads newest handoff |
| (this commit) | feat(models): ADR-0003 — pin gemma4:e4b + swap embeddings default to bge-m3 |

---

## 2. What shipped

### ADR-0003
`docs/adr/ADR-0003-model-defaults-supersession.md` — supersedes ADR-0002
Decision 1 (embedding-model default) only. All other ADR-0002 decisions
remain in force.

### Text model default: `gemma4` → `gemma4:e4b`
- `packages/l4-router/src/providers/ollama.rs::DEFAULT_MODEL`
- `tools/evals/__main__.py::AETHER_EVAL_OLLAMA_MODEL` default literal

Rationale: `gemma4:latest` currently resolves to the `e4b` variant (9.6 GB,
128K context). Pinning explicitly freezes that today and avoids silent drift
if Ollama later points `:latest` at the 31B Dense variant, which has an
unresolved FlashAttention hang on prompts > 3–4K tokens ([Ollama issue
#15350](https://github.com/ollama/ollama/issues/15350), not fully fixed in
v0.20.3 per April 2026 reports). Aether's conversational-companion workload
matches `e4b`'s profile; the larger 26B-A4B MoE is a coding-agent shape that
users can opt into via `AETHER_OLLAMA_MODEL=gemma4:26b-a4b-it-q4_K_M`.

### Embedding model default: `nomic-embed-text` → `bge-m3`
- `packages/l2-memory/src/embeddings.rs::DEFAULT_OLLAMA_EMBED_MODEL`

Rationale: Tiger Data's April 2026 RAG benchmark — BGE-M3 72% retrieval
accuracy vs nomic-embed-text 57.25%. ~25-point lift. BGE-M3 also supports
multi-functional retrieval (dense + sparse + multi-vector), setting up
future hybrid-search cleanly. MIT licence. 8K context (same as nomic). 1.2
GB pull vs nomic's ~274 MB — acceptable at personal scale; still CPU-viable
at 568M params.

**Dimension change:** nomic is 768-dim; BGE-M3 dense is 1024-dim. No
migration needed — `FlatFileEmbeddingStore::query_nearest` filters by
length mismatch (line 304 in `embeddings.rs`), so any stale-dimension rows
from a prior on-flag session are silently skipped. Recommended hygiene if
Don has enabled embeddings pre-swap: delete `<data_dir>/embeddings/*.jsonl`
once before the next on-flag session.

### Runtime decision: no pivot
Research scanned `mistral.rs`, `candle`, ZML, vLLM, LM Studio, and llama.cpp
direct. None surfaced in April 2026 mainstream comparisons as a justified
pivot for a Tauri-Rust desktop app at personal scale. Ollama stays. ADR-0003
documents this explicitly so it doesn't get relitigated.

### Doc updates
- `docs/ARCHITECTURE-V2.md` — hybrid-search line + stack table embeddings row.
- `docs/MEMORY-V2-ARCHITECTURE.md` — §embeddings open-question retired
  (closed to BGE-M3) + §10 item 6 now references ADR-0003.
- `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` — env-var line updated.
- `docs/adr/ADR-0002-…md` — header updated with superseded-by marker.
- `ROADMAP_2026-04-24_MILESTONE_2.md` — amendment banner added at top,
  revised M2 run order (Durable Store before Retrieval) documented.

---

## 3. Check matrix

| Check | Result |
| --- | --- |
| `git status` | clean (post-commit) |
| Commits ahead of `origin/dev` | 1 (this commit + 344fbcf pushed already would = 2 — but 344fbcf already pushed in commit 1's push; verify at end) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (2 pre-existing L1 warnings unchanged) |
| `cargo test -p aether-l2-memory --lib --features "sqlite-backend embeddings"` | **33 / 33** (includes `ollama_provider_label_includes_model` retuned to `bge-m3`) |
| `cargo test -p aether-l2-memory --all-features` (sqlite_session tests) | 16 / 16 |
| `apps/desktop/src-tauri cargo test --all-features` | **210 / 210** (unchanged) |
| `python tools/lint-memory-doc/check.py` | OK (60 anchors / 12 files) |
| `python tools/lint-quality-doc/check.py` | OK (60 anchors / 19 files) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `scripts/current_status.sh` | correctly surfaces HANDOFF_2026-04-24_MILESTONE_2_PLAN.md (newest-handoff fix from 344fbcf working) |

Rot guards tolerate the value swaps because anchors key on symbol names
(`DEFAULT_OLLAMA_EMBED_MODEL`, `AETHER_EMBED_OLLAMA_MODEL`), not on the
literal string values.

---

## 4. Post-session subsystem status

No subsystem-level state change. All five subsystems (Vision V1, Voice V1,
Presence V1, Memory V2, Quality-Eval V1) remain CLOSED and rot-guarded.
Only their configured defaults moved.

---

## 5. Risks / alerts for next session

### A. (NEW) First post-swap Ollama session needs two pulls.
- `ollama pull gemma4:e4b` (if not already present — may alias existing
  `gemma4` cache).
- `ollama pull bge-m3` (if embeddings flag on).

Failure mode: healthcheck returns `ProviderModelNotFound`, friendly-error
mapping already surfaces "Model `X` isn't installed. Pull it with `ollama
pull X` and try again." (`memory_router.rs::friendly_provider_error`).
Same surface for embeddings — WARN + no-op per ADR-0002 best-effort
semantics.

### B. (NEW) Pre-swap embedding rows (if any) are dimension-orphaned.
If Don flipped `embeddings.enabled` on before this swap and generated
768-dim nomic rows, those rows sit in `<data_dir>/embeddings/*.jsonl` and
are silently skipped by the length-filter in `query_nearest`. Not a crash,
not a data loss; just non-queryable until cleared. Delete the JSONL files
once if present. M2 Run 1's Durable-store work can include a "clear stale
embeddings on dimension change" helper if we want to formalise.

### C. (RETIRED) Two Milestone 1 retrospective findings closed.
- `current_status.sh` stale-handoff bug — retired by 344fbcf (newest by
  git commit time, not filename).
- LF/CRLF warnings — retired by `.gitattributes` (344fbcf).

Both confirmed working this session: script surfaces correct handoff,
`git add` of this commit's files produced zero line-ending warnings.

### D. (CARRIED) Gemma 4 still unverified on real workloads.
Pinning to `:e4b` doesn't validate `:e4b` itself. First on-hardware run
is still the live verification. Narrow rollback path documented in ADR-0003
(flip two constants).

### E. (CARRIED) BGE-M3 unverified on Don's hardware.
Same as Ollama embedding provider risk from M1 Run 3+4 §B, but the provider
swap makes this Risk E new. First `ollama pull bge-m3 && pnpm tauri dev`
with embeddings on validates the ADR-0003 pick.

---

## 6. Decisions log additions

Milestone 2 decisions start at `#M2-01` per the planning handoff. Mini-Run
0 consumed some of the reserved slots and added new ones:

- **#M2-09 (NEW).** Text model default pinned `gemma4` → `gemma4:e4b`.
  Rationale: tag-drift hygiene + FA-hang avoidance. See ADR-0003 §Decision 1.
- **#M2-10 (NEW).** Embedding model default swapped `nomic-embed-text` →
  `bge-m3`. Supersedes ADR-0002 Decision 1. See ADR-0003 §Decision 2.
- **#M2-11 (NEW).** Eval harness default flipped to match router pin
  (`gemma4:e4b`). See ADR-0003 §Decision 3.
- **#M2-12 (NEW).** Ollama stays as the runtime. No `mistral.rs` / `candle`
  / ZML pivot in Milestone 2. Reevaluate in 6–12 months. See ADR-0003
  §Decision 5.
- **#M2-13 (NEW).** Policy: future changes to `DEFAULT_MODEL` or
  `DEFAULT_OLLAMA_EMBED_MODEL` constants require an ADR. Silent pin
  changes are a doctrine violation. See ADR-0003 §Consequences.
- **#M2-14 (NEW).** M2 run order revised: Durable Store (was Run 2) now
  runs before Retrieval Wiring (was Run 1). Reason: retrieval needs real
  rows to query. See `ROADMAP_2026-04-24_MILESTONE_2.md` amendment banner.
- **#M2-01 / #M2-02 / #M2-03** remain reserved — they belong to Retrieval
  Wiring (now Run 2), which has not shipped yet.

Carried: #1–#70 from Milestone 1, #M2-01..#M2-08 from the planning handoff
(reserved, unresolved, shifted up by 2 where overlap with run-order change
matters — see planning doc §§5+6 which stay accurate).

---

## 7. Revised Milestone 2 Run 1 prompt — Durable Store (ADR-0004)

The original `NEXT_SESSION_PROMPT_M2_RUN_1.md` points at Retrieval Wiring.
That's now **M2 Run 2**. The new M2 Run 1 is **Durable Store + ADR-0004**.

Paste the fenced block below verbatim into the next session:

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Verify tip with `git log --oneline -5` at session start.
Push state: this prompt assumes Mini-Run 0 was pushed; verify with
`git log origin/dev..dev --oneline`.

SESSION TYPE
- Implementation. M2 Run 1 per the amended roadmap:
  `ROADMAP_2026-04-24_MILESTONE_2.md` amendment banner — Durable Store +
  ADR-0004. Originally scheduled as Run 2; reordered because Retrieval
  Wiring (now Run 2) needs real embed-eligible rows to query.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (or `python scripts/current_status.py`).
   Paste the output. The newest-handoff fix from 344fbcf is live — trust
   what the script shows. Repo beats prompt.
2. `git log --oneline -15`. Confirm Mini-Run 0's ADR-0003 commit + 344fbcf
   are present.
3. Read, in order:
   - `HANDOFF_2026-04-24_M2_MINI_RUN_0.md` (this handoff — Mini-Run 0 end
     state, risks A/B live).
   - `ROADMAP_2026-04-24_MILESTONE_2.md` amendment banner + original Run 2
     section (the one now promoted to Run 1).
   - `docs/adr/ADR-0001-memory-domain-reconciliation.md` — six-domain
     taxonomy that Durable belongs to.
   - `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md` §2+3
     (flat-file store shape you're now paralleling for Durable/Projects/
     Artifacts).
   - `docs/adr/ADR-0003-model-defaults-supersession.md` (Mini-Run 0's
     context — BGE-M3 is the embedding default now).
   - `packages/l2-memory/src/domain.rs`, `session.rs`, `sqlite_session.rs`
     (for the existing store pattern).
   - `apps/desktop/src-tauri/src/memory_service.rs` (shell integration
     surface).

================================================================
§STATUS CORRECTION
================================================================

- Five subsystems CLOSED + rot-guarded. Unchanged.
- Default text model: `gemma4:e4b` (ADR-0003 pin). Default embedding
  model: `bge-m3` (ADR-0003 supersession).
- Embeddings feature is live and opt-in. Durable domain ENABLED for
  embedding writes but has no backing store yet — that is what this run
  builds.
- Decisions: #1–#70 (M1) + #M2-01..#M2-14 (#M2-09..#M2-14 shipped
  Mini-Run 0; #M2-01..#M2-08 reserved for later runs).

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

1. **#M2-04 — ADR-0004 store shape.** Three candidates to propose:
   - (a) SQLite (reuse `sqlite_session.rs` pattern as a new
     `sqlite_durable.rs`).
   - (b) Per-domain JSONL files mirroring the embedding store.
   - (c) Hybrid: SQLite for row storage, reuse flat-file for embeddings.
   Propose with tradeoffs — long-term scale, query shape, retention sweep
   integration, transactional durability, disk footprint.
2. **#M2-05 — whether Facts / Preferences domains ship alongside**
   Durable / Projects / Artifacts in this run, or defer until a consumer
   appears. Lean: defer. Propose.
3. Git push. Requirement IDs. Gemma rollback. Unchanged.

================================================================
§DELEGATED DECISIONS (you may decide)
================================================================

- Module layout within `packages/l2-memory/src/`. Trait naming, test
  patterns, commit messages, execution-report shape.
- Whether to feature-gate the durable store behind a cargo feature
  (probably yes — mirrors `sqlite-backend`).
- Retention-sweep extension approach (extend existing
  `RetentionScheduler`, or add a per-domain sweeper?).

================================================================
§PHASE — Durable Store
================================================================

Propose ADR-0004, get sign-off, then implement. Commit cadence:

1. ADR-0004 draft + accept (one commit, just the ADR).
2. New L2 store crate/module per ADR. Tests.
3. Shell wiring — Durable / Projects / Artifacts writes land in the new
   store (not Session).
4. Retention sweep extension — walks real rows in all three new domains.
5. Embedding lifecycle — forget on a Durable row cascades to the paired
   embedding row (if present).
6. Docs: MEMORY-V2-ARCHITECTURE.md §10 step 5 updated with actual coverage.

### Out of scope (defer)

- Retrieval wiring (that is M2 Run 2).
- Any UI beyond existing Memory tab (which surfaces counts, not per-domain
  row detail yet).
- Facts / Preferences domains unless #M2-05 decides otherwise.
- Any CI / pnpm eval work (that is M2 Run 5).

================================================================
§DONE WHEN
================================================================

- ADR-0004 accepted + executed this session (same-run discipline per
  Milestone 1 pattern).
- `cargo test --workspace` clean including new durable-store tests.
- Retention sweep tests cover all four domains (Session + Durable +
  Projects + Artifacts).
- Forget-cascade tested (Durable row forget → paired embedding row
  deleted).
- Rot guards (`lint-memory-doc`) still pass after adding new symbol
  anchors.

================================================================
§CHECK MATRIX
================================================================

Same shape as `HANDOFF_2026-04-23_RUN_3_PLUS_4.md` §2. Add new test count.

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix. All green.
2. Working tree clean.
3. One execution report: `DURABLE_STORE_EXECUTION_REPORT_2026-04-24.md`.
4. Handoff `HANDOFF_2026-04-24_M2_RUN_1.md` with commit table, check
   matrix, decisions #M2-15 onward, next prompt for Run 2 (Retrieval
   Wiring).
5. `git push origin dev`. Milestone 1 retrospective §3 item 3 made
   "push after every run" doctrine.

================================================================
§STANCE
================================================================

ADR before code. Propose #M2-04 and #M2-05 up front; wait for Don; then
ship. Don't bundle Retrieval Wiring — that's the next run's work. One
new store, one ADR, one sweep extension.

Good luck.
````

---

## 8. Session-end gate

- [x] ADR-0003 written.
- [x] Constants flipped (router + evals + embeddings).
- [x] Docs updated (ARCHITECTURE-V2, MEMORY-V2, QUALITY-EVAL-V1, ADR-0002).
- [x] Roadmap amended.
- [x] Rot guards pass.
- [x] `cargo fmt`, `cargo check`, `cargo test -p aether-l2-memory --lib --features`, shell tests, Python evals — all green.
- [ ] Commit + `git push origin dev`.

---

(end of handoff)
