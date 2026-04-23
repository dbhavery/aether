# Handoff — 2026-04-23 Run 1 + Run 2 (QE Tier 2B + Memory V2 step 5)

**Written:** 2026-04-23 session end.
**Branch:** `dev`. Tip `a1e9028`. 3 commits ahead of the
pre-session tip `43e43f9`; 40 commits ahead of `origin/dev` (push
still not authorised — handoff Risk D below).
**Working tree:** clean.

Multi-phase implementation session. Bundled Run 1 (Quality-Eval
Tier 2B) + Run 2 (Memory V2 step 5) from the six-run roadmap
written in the previous planning session. Both land cleanly, full
check matrix green.

Tier 3 skipped (Option C — clean handoff > half-done cleanup).

---

## 1. Commit table

| SHA | Subject |
| --- | --- |
| `4b0a5ce` | feat(tools): lint-quality-doc rot guard + flip QE doc to Current |
| `ef13b0e` | refactor(l2-memory,shell): execute ADR-0001 — relocate MemoryDomain, retire kernel stub |
| `a1e9028` | feat(memory): Memory V2 step 5 — retention sweep (boot + hourly tick) |

Plus this handoff + two execution reports (`QUALITY_EVAL_TIER_2B_EXECUTION_REPORT_2026-04-23.md`,
`MEMORY_V2_STEP5_EXECUTION_REPORT_2026-04-23.md`) to be committed
together at session end.

---

## 2. Full check-matrix results (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | **40** (unchanged push policy) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --all-features` | 21 session + 1 smoke + 16 sqlite |
| `cargo test -p aether-l4-router --features ollama-provider,vision-llamacpp,speech-whispercpp` | **96 / 96 under default parallelism** |
| `apps/desktop/src-tauri cargo test --all-features` | **204 / 204** (was 198, +6 sweep) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc/check.py` | OK (51 anchors) |
| `python tools/lint-voice-doc/check.py` | OK (48 anchors) |
| `python tools/lint-presence-doc/check.py` | OK (39 anchors) |
| `python tools/lint-quality-doc/check.py` | **OK (60 anchors / 19 files)** (NEW) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial` | 6 fail (as designed) |
| `python tools/evals/test_capture_replay.py` | 13 / 13 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 / 68 kB (unchanged) |
| `apps/desktop && pnpm test` | 185 / 185 |

---

## 3. Post-session subsystem status

- **Vision V1** — CLOSED. Rot-guarded. Unchanged.
- **Voice V1** — CLOSED. Rot-guarded. Unchanged.
- **Presence V1** — CLOSED. Rot-guarded. Unchanged.
- **Memory V2**:
  - Steps 1, 2, 3, 4, **5 COMPLETE**. Retention sweep runs at
    boot and every hour; aggregated `memory_forgotten` telemetry
    per domain + one L5 audit row per sweep invocation via
    `MemoryForget`.
  - Step 6 (embeddings) — pending, **Run 3 target**.
  - Step 7 (rot guard `tools/lint-memory-doc/`) — pending,
    downstream of step 6 (Run 4 target).
- **Quality-Eval V1** — v1.0, v1.1, v1.2, v1.3 shipped.
  **Tier 2B (rot guard + doc flip) COMPLETE.** `tools/lint-quality-doc/`
  live; doc status is "Current as of 2026-04-23". Pending:
  `pnpm eval` regression harness (Run 5 Option B).
- **Spec package** — glossary (gap #1) + NFR skeleton (gap #2) in.
  Gaps #3–#6 pending.
- **Test infrastructure** — parallel-test flakes still retired
  (2026-05-18). Default `cargo test` parallelism remains safe.
- **Architecture**: `aether_l2_memory::MemoryDomain` is the
  single source of truth for the six-domain taxonomy per
  ADR-0001. `SessionMemoryStore` is the only shared storage
  contract. `packages/l2-memory/src/kernel.rs` is gone.

---

## 4. Risks / alerts for next session

### A. (RETIRED) Memory V2 step 5 unblocked and shipped.

The prior handoff's Risk C ("L2/shell `MemoryDomain` enum
mismatch") is retired. ADR-0001 chose Option 3 (retire kernel
stub), ef13b0e executed it, a1e9028 consumed the new surface for
the retention sweep. The six-domain taxonomy lives in
`packages/l2-memory/src/domain.rs`.

### B. (RETIRED) Quality-Eval doc drift closed.

The prior handoff's Tier 2B action is done. Doc is "Current as of
2026-04-23"; `tools/lint-quality-doc/` enforces 60 anchors
across 19 files. Drift surfaces on the next eval run as a hard
failure.

### C. Step 5 intentionally only covers the Session domain.

Memory V2 ships six domains; today only `Session` has a backing
store (`SessionMemoryStore`). The sweep walks `MemoryDomain::ALL`
but trace-skips the five domains with no backing store. Memory V2
step 6 (embeddings) and/or a future domain-typed durable store
will populate the other five; until then, retention policy values
persisted in `memory.json` for Durable/Facts/Projects/Preferences/
Artifacts are inert. Not a bug — documented in the execution
report's "Known limitations" section.

### D. 40 commits unpushed on `dev`.

Push still not authorised. Grew from 37 (prior handoff) to 40 this
session. The roadmap's Run 0 ("Truth & Push") intended the push
before Run 1; that gate was deferred. Worth authorising at the
start of the next session, before Run 3 adds another 2–3 commits
on top.

### E. Gemma 4 still unverified on real workloads.

Unchanged from 2026-04-23 planning handoff Risk D. No
`ollama pull gemma4` + `--backend ollama` run has happened. Narrow
rollback path (two constants + doc references) if needed.

### F. Embeddings trait slate is clean (Run 3 impact).

ADR-0001 deleted the pre-V2 `EmbeddingStore` trait along with the
rest of `kernel.rs`. Memory V2 step 6 (Run 3) will reintroduce an
embedding trait from scratch, shape informed by the chosen local
embedding provider (Ollama embedding model is the design-doc
candidate). No legacy trait shape to preserve.

### G. Aggregated telemetry is a one-way design decision.

The sweep emits **one `memory_forgotten` row per domain per
sweep**, not per evicted item. If the Trust drawer's Memory tab
or a future auditing surface requires per-item eviction
telemetry, step 6 or step 7 must re-open this decision. Schema is
additive (the existing per-item `memory_forgotten` emitted by
user-initiated forgets continues unchanged).

### H. The boot sweep runs before the first `memory_recent` call.

Intentional — the user shouldn't see rows their policy says are
already gone. Side effect: the first few telemetry entries the
History tab shows after a restart may include a sweep's
`memory_forgotten` row. Acceptable; it's honest.

---

## 5. Decisions log additions (#53 onward)

- **53. Quality-Eval V1 rot-guard pattern mirrors presence-doc.**
  60 anchors covering v1 / v1.1 / v1.2 / v1.3 surface across 19
  files; doc/code divergence now fails CI-equivalent
  immediately. Chose to reconcile by editing the doc to describe
  shipped code (not by modifying code to match the old design).
- **54. `tools/evals/README.md` roadmap kept in sync with the
  architecture doc's §6.** Both share the same numbered
  sequence; a future PR that ships `pnpm eval` will flip item
  8 / item 7 together.
- **55. ADR-0001 executed by `pub use` re-export, not full
  callsite migration.** The shell's `memory_config::MemoryDomain`
  path still compiles; the canonical home is
  `aether_l2_memory::MemoryDomain`. Callsites can migrate
  opportunistically without a one-shot churn PR.
- **56. Retention sweep emits aggregated telemetry, not per-row.**
  One `memory_forgotten` row per domain per sweep when >0 rows
  evicted; zero rows emits nothing. Prevents History-tab flooding
  on first large eviction.
- **57. Retention sweep emits exactly one L5 audit row per
  invocation**, via the existing `MemoryForget` capability. No
  `AuditRecordEvent` shape change. Symmetric with other
  scheduled maintenance tasks (presence tick, future sweep
  analogs).
- **58. `SessionMemoryStore::prune_before` uses strict `<`
  comparison.** A row whose `timestamp_ms` equals the cutoff is
  kept. Matches the existing `prune_older_than` semantics on
  the SQLite backend; reduces off-by-one risk at day
  boundaries.
- **59. `RETENTION_SWEEP_INTERVAL_MS = 60 min`, locked in a
  comment, not user-configurable in this phase.** TTLs are
  measured in days; anything sub-hourly is noise. A later
  Settings UI surface can expose this if the need arises.
- **60. Non-Session domains skip retention sweeping with a
  `trace!` note.** The sweep walks `MemoryDomain::ALL`; five of
  six domains today have no backing store to prune. Explicit
  skip is more debuggable than silent no-op.
- **61. Boot sweep runs inside Tauri's `setup` closure before
  the presence loop and retention-tick loop are spawned.**
  Ensures the first `memory_recent` the UI asks for never
  surfaces rows the user's policy says should already be gone.

Carried: 1–52 from prior handoffs (including #52 ADR-0001
acceptance).

---

## 6. Anti-drift corrections made in-flight

- The `scripts/current_status.sh` helper read the 2026-05-18
  handoff, which still listed Risk A as blocking. I treated the
  2026-04-23 planning handoff as authoritative (ADR-0001 retires
  Risk A) and did not re-open the enum decision. Surfaced in
  §1's status output with a note to the user.
- The 2026-05-18 handoff's check-matrix count (198 shell tests)
  is now stale — this session's Phase 2b adds 6 sweep tests,
  taking the count to 204. The repo-beats-prompt rule made this
  a non-event; noting for the next handoff reader.

---

## 7. Next recommended prompt — Run 3 (Memory Retrieval / embeddings)

Paste the fenced block below verbatim into the next session.

````md
You are Claude Code, continuing work on Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev (40 commits ahead of origin/dev at session start
unless Don pushed in between).

SESSION TYPE
- Single-phase. Run 3 of the six-run roadmap 2026-04-23:
  Memory V2 step 6 (embeddings, opt-in).
- Smaller scope than Run 1 + Run 2. Single commit acceptable
  if the work stays coherent; two commits (trait + integration)
  acceptable if they split cleanly.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh`  (Windows fallback:
   `python scripts/current_status.py`). Paste the output.
   Repo beats prompt (Decision #32).
2. `git log --oneline -15`. Confirm `a1e9028`, `ef13b0e`, and
   `4b0a5ce` are in history.
3. Read, in order:
   - `HANDOFF_2026-04-23_RUN_1_PLUS_2.md` (this session's
     starting state — risks A + B are retired, C + D + F + G
     are live).
   - `docs/MEMORY-V2-ARCHITECTURE.md` §§3, 8, 9 (embeddings
     design).
   - `docs/adr/ADR-0001-memory-domain-reconciliation.md` — the
     "Consequences" section explicitly says Run 3 gets a fresh
     `EmbeddingStore` trait slate.
   - `ROADMAP_2026-04-23_SIX_RUN_PLAN.md` Run 3 section.
   - `packages/l2-memory/src/domain.rs` — the frozen
     six-domain surface.
   - `packages/l2-memory/src/session.rs` §§1-40 — the existing
     trait shape that the embedding trait will live adjacent
     to, not inside.
   - `apps/desktop/src-tauri/src/memory_config.rs` §EmbeddingsConfig
     — the policy surface the opt-in flag lives in.

================================================================
§STATUS CORRECTION (supersedes any conflicting prompt)
================================================================

Verified subsystem state at session start:
- Vision V1, Voice V1, Presence V1 — CLOSED, rot-guarded.
- Memory V2 steps 1–5 — COMPLETE. Retention sweep live (boot +
  hourly tick). Step 6 (embeddings) — NEXT. Step 7 still pending.
- Quality-Eval V1 — v1.3 + Tier 2B (rot guard + doc flip) COMPLETE.
  Pending: `pnpm eval` (Run 5 Option B).
- Spec package — glossary + NFR in; gaps #3–#6 pending.
- ADR-0001 executed; MemoryDomain lives in L2.
- Default local model: gemma4. Unverified on real workloads.

================================================================
§DOCTRINE GROUNDING (hard rules still in force)
================================================================

- L5 single writer for side effects; embedding writes go through
  a capability (NEW, see §PHASE below).
- Rot guards != acceptance criteria.
- No raw-media persistence (embeddings are fine; source text is
  fine; image/audio bytes are not).
- Additive by default.
- Private assets stay out of public distributables.
- No new heavy dependencies unless the embedding provider
  genuinely needs one.

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

1. Vector index backend (sqlite-vec, lancedb, in-proc HNSW,
   flat-file). Design doc explicitly defers this to
   implementation time — propose, don't decide silently.
2. Embedding provider default (`gemma4` embedding, `bge-m3`,
   `all-MiniLM` via Ollama). Propose with measured pros/cons.
3. Any new capability variant name on `Capability` enum —
   propose, don't add silently. Candidate: `MemoryEmbed` or
   similar.
4. Any new `memory.json` field shape. Design §3 already has
   `embeddings: { enabled, provider }`; extending it needs
   coordinator review.
5. Doctrine-level decisions, layer boundaries, onboarding
   redesign, requirement IDs, etc. — unchanged from prior
   prompts.
6. `git push`.
7. Memory V2 step 7 (rot guard — Run 4).
8. Rolling back Gemma 4.

================================================================
§DELEGATED DECISIONS (you may decide)
================================================================

- Trait shape: `EmbeddingStore` in
  `packages/l2-memory/src/embeddings.rs` per ADR-0001 §Consequences.
- Module layout, test patterns, commit messages, execution
  reports.
- Whether to feature-gate the implementation behind a cargo
  feature (e.g. `embeddings`) — lean yes, mirrors
  `sqlite-backend`.

================================================================
§PHASE — Memory V2 step 6 (embeddings, opt-in)
================================================================

Design reference: `docs/MEMORY-V2-ARCHITECTURE.md` §§3, 8, 9.
`memory.json` already has `embeddings.enabled` + `embeddings.provider`.

### Scope

1. New L2 module: `packages/l2-memory/src/embeddings.rs`. Trait
   `EmbeddingStore` with `upsert`, `query`, `delete` (shape
   informed by design §9 but reviewed against what a local
   Ollama / llama.cpp embedding worker can actually do). Feature-
   gate behind `embeddings` cargo feature so the default build
   doesn't require a vector-index dep.
2. One concrete implementation (propose: an in-proc flat-file
   backed store so the default build stays minimal; real vector
   index is a future slice).
3. Shell wiring: when `memory.json::embeddings.enabled == true`
   AND a valid provider is named, every `memory_write` with an
   allowed decision produces an embedding row keyed by the
   `memory_id` the service already returns.
4. L5: add `MemoryEmbed` capability (propose the exact name +
   `AuditRecordEvent`-free design first — see reserved decision
   3). Route the embedding write through L5 so audit stays
   coherent.
5. Settings surface: a single toggle (off by default) in the
   Settings drawer's Memory section. No new panels.
6. Tests covering: off-by-default path produces no embedding
   rows; on-path produces an embedding per allowed write;
   provider mis-spelled ⇒ warn + no-op; opt-out mid-session
   stops new embeddings but leaves old rows alone (forget
   path clears them explicitly).
7. Update `MEMORY-V2-ARCHITECTURE.md` §10 item 6 from pending to
   shipped with pointers.

### Out of scope

- Retrieval wiring. Step 6 lands the write path + store; using
  the embeddings for re-ranking memory recall is a separate
  slice (step 6-adjacent or a follow-up).
- Step 7 rot guard.
- Any new UI beyond a single Settings toggle.
- Remote embedding providers (local-only in this session).

### Commit cadence

Two or three commits: L5 capability → L2 trait + default impl →
shell wiring + Settings toggle. Combine if small.

### Done when

- `cargo test --workspace` passes including new embedding tests.
- With `embeddings.enabled = false` (default), behaviour is
  byte-identical to today.
- With `embeddings.enabled = true` + a known provider id, each
  `memory_write` Allowed outcome produces an embedding row.
- L5 audit is coherent — one audit row per embedding write.
- `MEMORY-V2-ARCHITECTURE.md` §10 item 6 reflects reality.

================================================================
§CHECK MATRIX — run at session end, all green to ship
================================================================

(Same matrix as this handoff's §2. New crate / feature test
lines added inline.)

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix. All green.
2. Working tree clean.
3. One execution report:
   `MEMORY_V2_STEP6_EXECUTION_REPORT_2026-04-23.md` (or whatever
   date, pattern stays consistent).
4. New handoff `HANDOFF_2026-04-23_RUN_3_EMBEDDINGS.md` covering:
   - commit table, check matrix, subsystem status, risks,
     decisions #62 onward, next prompt for Run 4 (rot guard +
     doc flip — mirror Tier 2B).
5. Confirm the 2026-04-23 Run-1-plus-2 handoff's retired risks
   stay retired.

================================================================
§STANCE
================================================================

Small, scoped, opt-in. Don't let embeddings leak into the default
code path. Propose vector backend + provider default explicitly;
don't silently lock them in. Decision #32 still applies — if this
prompt contradicts the repo, trust the repo and update this
prompt.

Good luck.
````

---

(end of handoff)
