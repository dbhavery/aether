# Handoff — 2026-04-25 Milestone 2 Run 1 complete (ADR-0004 shipped)

**Written:** 2026-04-25 (marathon session spanning 2026-04-24 afternoon → 2026-04-25).
**Branch:** `dev`. Tip `827eea4`. All commits pushed to `origin/dev`.
**Working tree:** clean.

Run 1 ("Durable Store") ships as three atomic phase commits on top of
Mini-Run 0 and the planning artefacts. Milestone 2 roadmap amended
run order holds: Durable Store before Retrieval Wiring.

---

## 1. Commit table (full Milestone 2 to date)

| SHA | Subject |
| --- | --- |
| `090eecb` | docs: open Milestone 2 — retrospective + roadmap + Run 1 prompt |
| `344fbcf` | chore: silence CRLF warnings + current_status reads newest handoff |
| `4c0b364` | feat(models): ADR-0003 — pin gemma4:e4b + swap embedding default to bge-m3 |
| `d93b2f5` | docs(adr): add ADR-0004 — Durable-domain store shape |
| `889e8cb` | feat(l2-memory,storage): execute ADR-0004 phase 1 — L2 parameterization |
| `8d739b5` | docs: session-end handoff — ADR-0004 phase 1 + next-session prompt |
| `43f29cc` | feat(shell): execute ADR-0004 phase 2 — route memory paths by domain |
| `827eea4` | test+docs(memory): ADR-0004 phase 3 — isolation tests, Durable sweep, rot-guard |

Eight commits, all pushed.

---

## 2. What Run 1 delivered (end-to-end)

**Durable domain is now a first-class memory lane.**

- Migration `0005_durable_log.sql` creates the `durable_log` table, shape-identical to `conversation_log`.
- `SqliteSessionMemoryStore::with_table(conn, config, retention, table_name)` — parameterized constructor. All SQL re-templated via `format!()` on `self.table_name`.
- `DurableSessionStore::open_session_and_durable` → returns `SessionAndDurableStores { session, durable, conn }`.
- Shell `AppState` gains `durable_memory: Arc<dyn SessionMemoryStore>`, `memory_for_domain(MemoryDomain)`, and `DOMAINS_WITH_STORE` constant.
- Every shell memory-service path (`perform_memory_write`, `memory_forget`, `perform_memory_forget_item`, `perform_memory_edit`, `run_retention_sweep`) routes through `memory_for_domain`.
- Retention sweep now prunes Durable independently with `retention_days.durable` (30-day default); Session + Durable each get their own prune pass.
- Embedding forget cascade on per-item Durable forget operates naturally (`delete_embedding` was already in place; it now sees real Durable rows).
- +4 shell tests lock the isolation contract (Durable ↔ Session isolation, Durable sweep, `memory_for_domain` routing, `DOMAINS_WITH_STORE` size).
- +4 L2 integration tests lock the parameterization contract.
- Rot-guard anchors: 70 across 16 files (was 60/12).

**What is NOT shipped (known, deferred by ADR-0004):**
- Projects / Artifacts / Facts / Preferences domains — still alias the Session store via the fallback-with-warn path. ADR-0005 closes this when a UX consumer appears.
- Whole-lane forget cascade for embeddings (`memory_forget(Durable, session_id)` does not iterate-and-delete paired embedding rows). Per-item Durable forget does cascade. Captured as a known limitation.
- Retrieval wiring (turn engine consuming `EmbeddingStore::query_nearest`) — this is Milestone 2 Run 2.

---

## 3. Check matrix (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | 0 (pushed) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (2 pre-existing L1 warnings unchanged) |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-storage` | 3 / 3 |
| `cargo test -p aether-l2-memory --lib --features "sqlite-backend embeddings"` | 33 / 33 |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | 20 / 20 (added +4 ADR-0004 tests in phase 1) |
| `apps/desktop/src-tauri cargo test --all-features` | **214 / 214** (was 210; +4 ADR-0004 isolation tests) |
| `python tools/lint-memory-doc/check.py` | OK (**70 anchors / 16 files**; was 60/12) |
| `python tools/lint-quality-doc/check.py` | OK (60 anchors / 19 files) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `scripts/current_status.py` | surfaces this handoff next session |

---

## 4. Subsystem status

- Vision V1, Voice V1, Presence V1 — CLOSED + rot-guarded. Unchanged.
- **Memory V2** — CLOSED + rot-guarded. **Durable lane now has a real backing store and honoured retention**. Retrieval consumption (turn engine) pending — Milestone 2 Run 2.
- Quality-Eval V1 — CLOSED + rot-guarded. Unchanged.
- Defaults: `gemma4:e4b` (text, ADR-0003) / `bge-m3` (embed, ADR-0003). Both unverified on real hardware — first `ollama pull … && pnpm tauri dev` validates.

---

## 5. Risks / alerts for next session

### A. (NEW) Durable lane empty at first session start.
Before Run 2 (Retrieval Wiring) ships, no code writes `MemoryDomain::Durable` — today's call sites all write `Session` or `Facts`. The Durable lane is provisioned but dormant until a writer exists. Not a bug; just a calibration for the first time someone inspects `durable_log`.

### B. (NEW) Retrieval wiring can proceed against real storage.
Run 2 will query `EmbeddingStore::query_nearest` for Durable/Projects/Artifacts. Durable embeddings DO get written today when `embeddings.enabled = true` and a Durable write happens. Projects/Artifacts embeddings are also written (per ADR-0002 §5) but stored only in the flat-file embedding store with no backing row in a dedicated SQL table — they continue to work because the embedding flat-file is keyed on `memory_id`, not on a SQL FK. Retrieval against Projects/Artifacts will return hits even before ADR-0005 lands.

### C. (CARRIED) gemma4:e4b + bge-m3 unverified on real hardware.
Same as Mini-Run 0's Risk E. No behavioural change this run; still a first-pull validation away.

### D. (RETIRED) ADR-0004 execution.
All three phases shipped. The M2 Run 1 prompt in `HANDOFF_2026-04-24_M2_RUN_1_PHASE_1.md` §7 is now historical.

### E. (CARRIED) Whole-lane Durable forget does not cascade embeddings.
Known limitation from ADR-0004 §7. Add to the "future refinement" pile — ADR-0005 or a follow-up can iterate-and-delete when a UX need appears.

### F. (CARRIED) Projects / Artifacts / Facts / Preferences still alias Session.
ADR-0005 territory. Fallback path emits a `warn!` so this won't go silently.

---

## 6. Decisions log

Milestone 2 tally:
- **#M2-01 / #M2-02 / #M2-03** — Retrieval Wiring decisions. STILL RESERVED. Run 2 scope.
- **#M2-04** — RESOLVED (ADR-0004 Option b).
- **#M2-05** — RESOLVED (defer Projects/Artifacts/Facts/Preferences to ADR-0005).
- **#M2-06 / #M2-07 / #M2-08** — reserved (Gap #3 auth, CI ADR, CI blocking).
- **#M2-09..#M2-14** — shipped in Mini-Run 0 (commit `4c0b364`).

No new numbered decisions this phase — ADR-0004 §6 already captured the `DOMAINS_WITH_STORE = [Session, Durable]` choice as part of the accepted ADR.

Milestone 1's 70 decisions unchanged.

---

## 7. Next session prompt — Milestone 2 Run 2 (Retrieval Wiring)

Paste the fenced block below verbatim:

````md
You are Claude Code, starting Milestone 2 Run 2 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should be `827eea4` (verify with
`git log --oneline -5`).

SESSION TYPE
- Implementation. M2 Run 2 (originally Run 1 before the ADR-0004
  reorder): retrieval wiring. Turn engine consumes
  `EmbeddingStore::query_nearest` for Durable / Projects / Artifacts
  recall when embeddings are enabled; soft-fallback to
  `SessionMemoryStore::recent` when not.
- Durable now has a real backing store (ADR-0004 shipped), so this
  run can land cleanly — retrieval finally has rows to query.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (Windows fallback:
   `python scripts/current_status.py`). Paste the output. Should
   surface `HANDOFF_2026-04-25_M2_RUN_1_COMPLETE.md`.
2. `git log --oneline -20`. Confirm the full Milestone 2 chain
   (090eecb → 344fbcf → 4c0b364 → d93b2f5 → 889e8cb → 8d739b5 →
   43f29cc → 827eea4) is present.
3. Read, in order:
   - `HANDOFF_2026-04-25_M2_RUN_1_COMPLETE.md` (this handoff).
   - `ROADMAP_2026-04-24_MILESTONE_2.md` amendment banner + the
     original §Run 1 (Retrieval Wiring) section — now Run 2.
   - `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md`
     (trait surface).
   - `docs/adr/ADR-0003-model-defaults-supersession.md` (bge-m3 is
     the default).
   - `docs/adr/ADR-0004-durable-store-shape.md` (Durable storage
     shape + `DOMAINS_WITH_STORE`).
   - `packages/l2-memory/src/embeddings.rs` — `EmbeddingStore`,
     `EmbeddingProvider`, `query_nearest` signature, `SimilarityHit`.
   - `apps/desktop/src-tauri/src/memory_router.rs` — both
     `MemoryAwareRouter::dispatch` and `RoleTaggedOllamaRouter::dispatch`
     currently call `self.store.recent(&self.session_id)` — this is
     where retrieval wires in.
   - `apps/desktop/src-tauri/src/state.rs::AppState::memory_for_domain`
     — the helper you'll use for Durable recall.

================================================================
§STATUS CORRECTION
================================================================

- Five subsystems CLOSED. Durable lane populated on writes via
  ADR-0004. Default embedding model: bge-m3 (ADR-0003).
- No shell UI changes today — retrieval is back-end only.
- Decisions #M2-04, #M2-05, #M2-09..#M2-14 shipped. #M2-01..#M2-03
  reserved (this run's decisions).

================================================================
§RESERVED DECISIONS (propose; wait for Don)
================================================================

1. **#M2-01** — Capability name for retrieval-augmented reads.
   Propose: reuse existing `MemoryRead` (Low/Auto). Only introduce
   `MemoryRetrieve` if auditor surface genuinely needs to
   distinguish. Inline proposal + rationale; wait for Don's reply
   before writing router code.
2. **#M2-02** — Retrieval timing: block the turn, or run in
   parallel with prompt compilation? Propose: parallel with a
   250 ms timeout + silent fallback to `SessionMemoryStore::recent`.
   Include timeout rationale.
3. **#M2-03** — Union / rank strategy for embedding + session
   results. Propose: interleave by recency + similarity score,
   cap N via a new `memory.json::retrieval.max_items` field with
   sensible default. Don decides the default.

================================================================
§DELEGATED DECISIONS (you may decide)
================================================================

- Module layout: where the retrieval orchestrator lives
  (`apps/desktop/src-tauri/src/retrieval.rs` new file, or inline in
  `memory_router.rs`).
- Deterministic tie-breaker for equal similarity scores.
- Whether to embed the inbound utterance synchronously or to
  spawn an async task (constrained by #M2-02).
- `memory.json` schema additions (if any) — add them additive
  per the existing doctrine.

================================================================
§PHASE — Retrieval Wiring
================================================================

Commit 1 — Propose + lock the three reserved decisions (ADR or
short design note; no code yet). Wait for Don's approval on each
before any router code lands.

Commit 2 — Orchestrator: given an incoming utterance, embed it
via the active `EmbeddingProvider`, query every embed-eligible
domain's `EmbeddingStore::query_nearest`, union with
`SessionMemoryStore::recent`, and return a `RecentMemoryWindow`
extended with retrieved rows. Respect the timing + rank decisions
from commit 1.

Commit 3 — Wire `memory_router.rs` to consume the orchestrator.
`MemoryAwareRouter::dispatch` (and the role-tagged variant) call
the new path when `memory_config.embeddings.enabled` is true and
a valid provider is configured; silently fall back to `recent`
when not.

Commit 4 — Tests + doc update.
- Determinism: embeddings off → byte-identical window to
  `827eea4`.
- Fallback: embeddings on + provider unreachable → session-only
  window + one `warn!` per turn (not per query).
- Happy path: embeddings on + matching Durable rows → turn prompt
  has access to them; ordering matches #M2-03.
- `docs/MEMORY-V2-ARCHITECTURE.md` §10 or a new §11 captures the
  retrieval path.
- Rot-guard anchors updated.

### Out of scope

- UI feedback for recalled items (M2 Run 6 Memory Tab Polish).
- Onboarding flow (M2 Run 3).
- ADR-0005 / Projects / Artifacts stores (deferred).
- CI (M2 Run 5).

================================================================
§DONE WHEN
================================================================

- `cargo fmt --all -- --check`, `cargo check --workspace`,
  `cargo test --workspace` all clean.
- With `embeddings.enabled = false` (default), turn output is
  byte-identical to `827eea4`.
- With embeddings on + unreachable provider, fallback works and
  emits exactly one `warn!` per turn.
- With embeddings on + real Durable rows + a matching utterance,
  the retrieved rows land in the prompt in the #M2-03 ordering.
- `python tools/lint-memory-doc/check.py` passes after anchor
  updates.
- Shell typecheck / build / test all clean (no UI change).

================================================================
§CHECK MATRIX
================================================================

Same shape as §3 above. Add: retrieval-orchestrator test count
(expect +4 to +8).

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix, all green.
2. Working tree clean.
3. Execution report:
   `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-25.md` (or whatever
   date).
4. Handoff `HANDOFF_2026-04-25_M2_RUN_2.md` with commit table,
   decisions (#M2-01..#M2-03 closed), risks (A/B from this
   handoff retire), next prompt for M2 Run 3 (Embeddings
   Onboarding).
5. `git push origin dev`.

================================================================
§STANCE
================================================================

Propose the three reserved decisions up front. Don't invent
capability names or timeout values silently. The Durable lane is
ready to be queried (Run 1 shipped that); your job is to query it.

Good luck.
````

---

## 8. Session-end gate

- [x] Run 1 functionally complete across three phases.
- [x] All eight Milestone 2 commits pushed.
- [x] 214 shell tests pass, 20 L2 sqlite tests pass, 70-anchor rot guard green.
- [x] Memory V2 architecture doc reflects Durable coverage.
- [x] Session-end handoff written + next-session prompt embedded.

---

(end of handoff)
