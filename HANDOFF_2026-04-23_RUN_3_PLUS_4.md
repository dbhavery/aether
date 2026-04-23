# Handoff — 2026-04-23 Run 3 + Run 4 (Memory V2 step 6 + step 7)

**Written:** 2026-04-23 session end (second half of the long
session that also shipped Run 1 + Run 2 earlier).
**Branch:** `dev`. Tip `09df5b0`. 4 commits ahead of `origin/dev`
at session end (after the mid-session push that made the
Run 1 + Run 2 bundle authoritative).
**Working tree:** clean.

Two-phase implementation session bundled Run 3 (embeddings,
opt-in) + Run 4 (rot guard + doc flip). Six-run roadmap status
after this session:

| Run | State |
| --- | --- |
| 0 | ✅ Truth & Push |
| 1 | ✅ QE Current |
| 2 | ✅ Memory Sweep |
| 3 | ✅ Memory Retrieval (embeddings) |
| 4 | ✅ Memory Lock |
| 5 | ⏳ Polish & IDs (pick ONE) |

Only Run 5 remains on the committed roadmap.

---

## 1. Commit table

| SHA | Subject |
| --- | --- |
| `e135c2a` | feat(memory): Memory V2 step 6 — embeddings (opt-in, local-only) |
| `120b6d0` | feat(tools): lint-memory-doc rot guard + flip Memory V2 doc to Current |
| `09df5b0` | docs(memory): mark V2 §10 items 6+7 as shipped |

Plus this handoff + two execution reports committed together at
session end.

---

## 2. Full check matrix (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | **4** (push after session 1, plus Runs 3+4) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings"` | 33 session + 1 smoke + 16 sqlite |
| `cargo test -p aether-l5-policy` | all pass (20 engine tests) |
| `cargo test -p aether-l4-router --features …` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --all-features` | **210 / 210** (+6 embed) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `python tools/lint-quality-doc/check.py` | OK (60 anchors) |
| `python tools/lint-memory-doc/check.py` | **OK (60 anchors / 12 files)** (NEW) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 fail (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 / 68 kB |
| `apps/desktop && pnpm test` | 185 / 185 |

---

## 3. Post-session subsystem status

- **Vision V1** — CLOSED, rot-guarded. Unchanged.
- **Voice V1** — CLOSED, rot-guarded. Unchanged.
- **Presence V1** — CLOSED, rot-guarded. Unchanged.
- **Memory V2** — **CLOSED, rot-guarded.** Steps 1–7 COMPLETE.
  Retention sweep live (boot + hourly). Embeddings available
  opt-in via `memory.json::embeddings.enabled` + Ollama
  provider. `tools/lint-memory-doc/` enforces 60 anchors.
- **Quality-Eval V1** — CLOSED, rot-guarded. Unchanged. Pending
  only: `pnpm eval` regression harness (Run 5 Option B).
- **Spec package** — glossary + NFR skeleton in. Gaps #3–#6
  pending.
- **Test infrastructure** — Parallel flakes retired (2026-05-18).
- **Architecture**: ADR-0001 + ADR-0002 accepted. Five
  rot-guarded subsystems, zero design-only drift.

---

## 4. Risks / alerts for next session

### A. (RETIRED) Memory V2 subsystem closed.

Prior handoff's Risk C ("Step 5 intentionally only covers the
Session domain") remains technically accurate — the sweep still
only prunes Session domain — but it is now a known limitation
documented both in the execution reports and in the backlog
("5.5a Domain-typed durable store") rather than a blocker.

### B. (NEW) Embedding provider unverified on real workloads.

ADR-0002 picked Ollama `nomic-embed-text` as the default. No
`ollama pull nomic-embed-text` + embeddings-enabled session has
happened on Don's hardware; the first user to flip the toggle
will validate the choice. Failure mode documented: WARN + no-op
on primary writes, Memory tab shows zero embedding rows. Easy
to diagnose.

### C. (CARRIED) Gemma 4 still unverified on real workloads.

Unchanged from prior handoffs. Separate concern from the
embedding model; the text model stays gemma4.

### D. (NEW) Flat-file embedding store rewrites on every
mutation.

Per ADR-0002, the flat-file impl rewrites the entire domain
JSONL on every upsert / delete. Linear in corpus size; at
personal scale this is sub-millisecond. If someone enables
embeddings and grows Durable/Projects/Artifacts rapidly, the
rewrite cost becomes measurable. The trait is swappable — this
is not a blocker, just a thing to watch.

### E. (NEW) Shell always compiles embeddings, gated only at
runtime.

`apps/desktop/src-tauri/Cargo.toml` pins
`aether-l2-memory = { features = ["sqlite-backend", "embeddings"] }`.
Default-off runtime flag, but the code paths compile into the
shipped binary. If privacy reviewers ever ask whether embedding
code is "present even when disabled", the answer is yes. Make
this an explicit comment in any compliance doc that comes up.

### F. (CARRIED) Embedding retention on domain-typed store.

Carried from Run 1+2's Risk C. When the future domain-typed
durable store lands (backlog 5.5a), retention sweep must extend
to prune orphaned embedding rows when their parent memory has
been evicted. Not a blocker today because retention sweep only
affects Session, which is not embed-eligible.

---

## 5. Decisions log additions (#62 onward)

- **62. ADR-0002 — embeddings provider + vector backend
  accepted.** Ollama `nomic-embed-text` default, flat-file
  domain-partitioned store, `MemoryEmbed` capability,
  `embeddings` cargo feature, embed-eligible Durable / Projects
  / Artifacts. Full reasoning in
  `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md`.
- **63. Embedding is best-effort; primary write is authoritative.**
  Provider / store failures trace-warn; the primary
  `memory_write` always returns `Allowed` when its own path
  succeeded. Rationale: embeddings are additive signal, not
  required state.
- **64. Shell pins `embeddings` feature on.** Default-off
  runtime flag via `memory.json::embeddings.enabled`; no
  compile-time gate at the shell boundary. Simpler release
  story; trivial opt-out for end users.
- **65. Embedding delete pairs with per-item
  `MemoryForget` Allow.** Session-level `memory_forget` (clear
  whole session) does NOT cascade because Session is not
  embed-eligible — there are no embedding rows to delete. Bulk
  embedding forget is a future UX.
- **66. Flat-file JSONL persistence rewrites entire domain on
  mutation** (write-to-temp + rename). Atomic, trivial to
  inspect, acceptable cost at personal scale. Append-only
  optimisation deferred.
- **67. Memory V2 doc status flip paired with rot-guard
  creation in the same commit window.** Pattern: `feat(tools):
  lint-<name>-doc ... + flip ... to Current`. Prevents the
  "subsystem ships, doc stays design-only for months" failure
  mode four subsystems have now proven.

Carried: 1–61 from prior handoffs.

---

## 6. Roadmap status

Six-run roadmap 2026-04-23:

1. ✅ Run 0 — Truth & Push
2. ✅ Run 1 — QE Current
3. ✅ Run 2 — Memory Sweep (ADR-0001 execution + sweep)
4. ✅ Run 3 — Memory Retrieval (embeddings)
5. ✅ Run 4 — Memory Lock (rot guard + doc flip)
6. ⏳ Run 5 — Polish & IDs (pick ONE of A/B/C)

### Post-closure backlog (not committed to roadmap)

- **5.5a Domain-typed durable store.** Populates the five
  trace-skipped domains in the retention sweep; enables
  embedding lifecycle paired with non-Session rows.
- **5.5b Per-item sweep telemetry opt-in.** Explicit reopen of
  Decision #56 if the Memory tab surfaces a genuine need.
- **Retrieval wiring.** Turn engine consumes
  `EmbeddingStore::query_nearest` for Durable/Projects/Artifacts
  recall. Separate slice.

---

## 7. Next recommended prompt — Run 5 (Polish & IDs)

Paste the fenced block below verbatim into the next session.

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev (4 commits ahead of origin/dev at session start
unless Don pushed in between).

SESSION TYPE
- Single-phase, small. Run 5 of the six-run roadmap 2026-04-23:
  pick ONE of the three options below. Do NOT bundle. The
  roadmap is explicit — single-purpose runs keep the habit of
  reviewable scope.
- After Run 5, the six-run roadmap is DONE. Consider whether to
  draft a new milestone / roadmap before more work lands.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (Windows fallback:
   `python scripts/current_status.py`). Paste the output. Repo
   beats prompt (Decision #32).
2. `git log --oneline -15`. Confirm `09df5b0`, `120b6d0`,
   `e135c2a`, `2a71849`, `a1e9028`, `ef13b0e`, `4b0a5ce` are in
   history.
3. Read, in order:
   - `HANDOFF_2026-04-23_RUN_3_PLUS_4.md` (this session's end
     state — roadmap is 4/5 done).
   - `ROADMAP_2026-04-23_SIX_RUN_PLAN.md` §Run 5 (three options
     A/B/C).
   - The option-specific file per your pick (see below).

================================================================
§STATUS CORRECTION (supersedes any conflicting prompt)
================================================================

- Vision V1, Voice V1, Presence V1, Memory V2, Quality-Eval V1 —
  ALL CLOSED, rot-guarded. Five subsystems, five rot guards.
- Spec gaps #3–#6 pending.
- Default local text model: gemma4 (unverified); default local
  embedding model: nomic-embed-text via Ollama (unverified).
- ADRs accepted: 0001 (domain relocation), 0002 (embeddings
  defaults).

================================================================
§PHASE — pick ONE (Run 5 discipline)
================================================================

### Option A: MemoryDrawer ↔ MemoryTab consolidation (~15 min)

Smallest scope. One of:
- Retarget the header Memory button to open Trust drawer on the
  Memory tab.
- OR delete `apps/desktop/src/components/MemoryDrawer.tsx` and
  its triggering button.

Either way, remove the redundant surface. The Memory tab is the
durable one; `MemoryDrawer` was a step-4-era scaffold.

Read first:
- `apps/desktop/src/components/MemoryDrawer.tsx`
- `apps/desktop/src/components/MemoryTab.tsx`
- header button wiring in `apps/desktop/src/App.tsx` (or
  wherever the Memory button lives).

Done when: exactly one entry point to the Memory surface,
Vitest tests updated, pnpm test green, pnpm build clean.

### Option B: `pnpm eval` regression harness wiring

Quality-Eval v1 gets a scripted `pnpm eval` command that runs
`tools/evals/__main__.py --dry-run` + the adversarial suite and
surfaces non-zero exit on regression. Downstream of v1.3
session-log importer + Tier 2B rot guard.

Read first:
- `tools/evals/README.md`
- `apps/desktop/package.json` (where `test` / `typecheck` /
  `build` scripts live) — or a root `package.json` if one
  exists.
- `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` §6 step 7 — this is
  the step shipping.

Done when: `pnpm eval` runs the suite, exits non-zero on any
FAIL, and is documented in `tools/evals/README.md`. Update QE
doc §6 step 7 to ✅ and bump the rot guard's doc-status date
(same-session rot-guard re-verify).

### Option C: Forward-looking requirement IDs (Gap #3)

Don-reserved per prior handoffs — **do NOT pick this option
unless Don has explicitly authorised locking the requirement-ID
scheme this session.** If authorised, produce:
- `docs/REQUIREMENT-IDS.md` keyed to `docs/GLOSSARY.md` §11.
- One concrete ID per existing architecture doc
  (VISION-V1-ARCHITECTURE, VOICE-V1-ARCHITECTURE,
  PRESENCE-V1-ARCHITECTURE, QUALITY-EVAL-V1-ARCHITECTURE,
  MEMORY-V2-ARCHITECTURE) as a first batch.
- Validation that the scheme survives NFR + Memory V2 +
  Presence V1 without contradiction.

Done when: `docs/REQUIREMENT-IDS.md` exists, glossary §11 links
to it, each current architecture doc gains its first ID block,
and this doc's "pending" entry in handoff §Reserved Decisions
is retired.

================================================================
§HARD CONSTRAINTS
================================================================

- No multi-option bundling.
- No new packages/crates unless the option genuinely requires one
  (none of A/B/C do).
- Doctrine rules unchanged (L5 single writer, no raw-media
  persistence, additive by default, private assets out of
  public distributables, no silent fallback).
- No `AuditRecordEvent` shape change.
- No new Tauri commands unless Option A/B specifically needs one.
- Do not touch the five rot guards' anchor manifests except to
  reconcile drift surfaced by the option's own changes.

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix (same as this handoff's §2). All green.
2. Working tree clean.
3. One execution report named for the option:
   - `MEMORY_DRAWER_CONSOLIDATION_EXECUTION_REPORT_2026-04-23.md`
     (Option A)
   - `PNPM_EVAL_HARNESS_EXECUTION_REPORT_2026-04-23.md`
     (Option B)
   - `REQUIREMENT_IDS_EXECUTION_REPORT_2026-04-23.md` (Option C)
4. Consolidated handoff `HANDOFF_2026-04-23_RUN_5.md` covering
   commit table, check matrix, post-session status, decisions
   additions (#68 onward), and — since this closes the six-run
   roadmap — a recommended "next milestone" prompt or a
   reflection on what the next committed roadmap should target.
5. Consider authorising `git push`. The roadmap-complete moment
   is the natural place to publish.

================================================================
§STANCE
================================================================

Run 5 is deliberately small. Roadmaps stay honest when the last
run doesn't try to be a whole milestone. Ship one thing, write
the report, push the pile, then plan the next milestone from a
clean slate.
````

---

(end of handoff)
