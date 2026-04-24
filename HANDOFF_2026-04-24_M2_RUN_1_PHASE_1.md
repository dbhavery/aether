# Handoff — 2026-04-24 Milestone 2 Run 1 Phase 1 (ADR-0004 L2 foundation)

**Written:** 2026-04-24 session end (long session — 4 commits shipped).
**Branch:** `dev`. Tip `889e8cb`. All commits pushed to `origin/dev`.
**Working tree:** clean.
**Session type:** planning + research + ADR + L2 execution. Mid-session scope
shifted to Mini-Run 0 (model defaults) after research revealed a cleaner
milestone kickoff, then to ADR-0004 execution when Don authorised "keep going".

---

## 1. Commit table

| SHA | Subject |
| --- | --- |
| `090eecb` | docs: open Milestone 2 — retrospective + roadmap + Run 1 prompt |
| `344fbcf` | chore: silence CRLF warnings + current_status reads newest handoff |
| `4c0b364` | feat(models): ADR-0003 — pin gemma4:e4b + swap embedding default to bge-m3 |
| `d93b2f5` | docs(adr): add ADR-0004 — Durable-domain store shape |
| `889e8cb` | feat(l2-memory,storage): execute ADR-0004 phase 1 — per-domain table parameterization |

Five commits this session, all pushed.

---

## 2. What shipped

### Milestone 2 opening (pre-lunch)
- Retrospective, roadmap, first run prompt — `090eecb`.
- Hygiene chore (`.gitattributes` + `current_status.py` newest-handoff fix) — `344fbcf`.

### Mini-Run 0 (research-driven model swap)
- ADR-0003 supersedes ADR-0002 Decision 1 only.
- Text default `gemma4` → `gemma4:e4b` (pin; avoids 31B Dense FA hang).
- Embedding default `nomic-embed-text` → `bge-m3` (+25-point retrieval accuracy).
- Ollama stays; no runtime pivot. See commit `4c0b364` + file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/project_aether_gemma4_adoption.md.

### ADR-0004 accepted
- Per-domain SQLite log tables. Parameterized `SqliteSessionMemoryStore`.
- Scope limited to Durable this run; Projects/Artifacts deferred to ADR-0005.
- Shell-side DomainStoreRegistry + routing is **phase 2** (next session).
- See commit `d93b2f5` + file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0004-durable-store-shape.md.

### ADR-0004 Phase 1 executed
- Migration `0005_durable_log.sql` (identical shape to `0004_conversation_log.sql`).
- `SqliteSessionMemoryStore::with_table(conn, config, retention, table_name)` — new constructor.
- All SQL in `sqlite_session.rs` re-templated to consume `self.table_name`; no hard-coded table strings.
- New exports: `DEFAULT_TABLE`, `DURABLE_TABLE`, `SessionAndDurableStores`.
- `DurableSessionStore::open_session_and_durable(path, config, session_retention, durable_retention)` opens both stores on a shared connection.
- +4 integration tests covering the parameterization, isolation, pairing, and per-table retention.
- Commit `889e8cb`.

---

## 3. Check matrix (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | 0 (pushed) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (2 pre-existing L1 warnings unchanged) |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-storage` | 3 / 3 (migration-runs tests include 0005) |
| `cargo test -p aether-l2-memory --lib --features "sqlite-backend embeddings"` | 33 / 33 |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | **20 / 20** (was 16; +4 ADR-0004 tests) |
| `apps/desktop/src-tauri cargo test --all-features` | 210 / 210 |
| `python tools/lint-memory-doc/check.py` | OK (60 anchors / 12 files) |
| `python tools/lint-quality-doc/check.py` | OK (60 anchors / 19 files) |
| `python tools/evals/__main__.py --dry-run` | 6 / 6 |
| `python tools/evals/test_session_log_import.py` | 14 / 14 |
| `scripts/current_status.py` | surfaces this handoff after next session's new handoff lands |

---

## 4. Post-session subsystem status

- Vision V1, Voice V1, Presence V1 — CLOSED + rot-guarded. Unchanged.
- **Memory V2** — CLOSED + rot-guarded. **Default embedding model now `bge-m3` (ADR-0003)**. L2 storage surface now supports per-domain tables via `with_table` constructor. Durable lane has a backing migration but NO shell routing yet — runtime behaviour for `MemoryDomain::Durable` writes is still "lands in Session store with a warn-worthy note" pending phase 2.
- Quality-Eval V1 — CLOSED + rot-guarded. Default eval model now `gemma4:e4b`.
- 70 Milestone 1 decisions carry. Milestone 2 decisions: #M2-01..#M2-08 reserved for later runs (Retrieval Wiring, CI); #M2-09..#M2-14 shipped in Mini-Run 0 (ADR-0003); **#M2-04 and #M2-05 resolved by ADR-0004**.

---

## 5. Risks / alerts for next session

### A. (NEW) Phase 2 is shell-side plumbing — largest remaining Run 1 surface.
The Durable table exists, the L2 surface supports it, but the shell still funnels every `memory_write` into the Session store regardless of domain (the existing known-limitation from M1). Phase 2 must:
1. Build a `DomainStoreRegistry` (or equivalent) in `apps/desktop/src-tauri/src/state.rs`.
2. Open the paired store at startup via `DurableSessionStore::open_session_and_durable`.
3. Route `perform_memory_write`, `memory_forget`, `memory_forget_item`, `memory_edit`, and the recall path through the registry.
4. Extend `retention.rs` (or its equivalent) to walk Durable with `memory.json::retention_days.durable` (30-day default).
5. Wire the embedding forget cascade: on per-item Durable forget, call `EmbeddingStore::delete(Durable, memory_id)`.
6. Shell tests covering each of the above (~8–12 new tests).
7. Doc update: `docs/MEMORY-V2-ARCHITECTURE.md` §10 step 5 coverage note.
8. Rot-guard anchors on `tools/lint-memory-doc/check.py` for new symbols.

### B. (CARRIED from Mini-Run 0) gemma4:e4b + bge-m3 unverified on real hardware.
First `ollama pull gemma4:e4b && ollama pull bge-m3 && pnpm tauri dev` validates both picks. Pre-swap 768-dim nomic embedding rows (if any) are silently skipped — delete `<data_dir>/embeddings/*.jsonl` once to clean.

### C. (RETIRED) ADR-0004 store-shape decision.
Resolved + executed phase 1. Phase 2 is mechanical shell plumbing on top of the now-frozen L2 surface.

### D. (RETIRED) Milestone 1 retrospective §3 items 1+2.
`current_status.py` newest-by-commit-time fix (`344fbcf`) and `.gitattributes` are both working — verified mid-session (`current_status.py` correctly surfaced `HANDOFF_2026-04-24_MILESTONE_2_PLAN.md` after Mini-Run 0's code commit; staging produced zero CRLF warnings).

### E. (CARRIED) Projects / Artifacts domains still unbacked.
ADR-0004 deliberately scoped to Durable only. Projects/Artifacts writes continue to hit the Session store. ADR-0005 in a future run closes this.

---

## 6. Decisions log

Milestone 2 tally after this session:
- **#M2-01 / #M2-02 / #M2-03** — Retrieval Wiring decisions (still reserved; belong to the renamed Run 2).
- **#M2-04** — RESOLVED. ADR-0004 Option (b): per-domain SQLite log tables.
- **#M2-05** — RESOLVED. Defer Projects/Artifacts to ADR-0005.
- **#M2-06 / #M2-07 / #M2-08** — still reserved (Gap #3 auth, CI ADR, CI blocking).
- **#M2-09..#M2-14** — shipped in Mini-Run 0 (`4c0b364`).

70 Milestone 1 decisions unchanged.

---

## 7. Next session prompt — ADR-0004 Phase 2 (shell routing)

Paste the fenced block below verbatim:

````md
You are Claude Code, continuing Milestone 2 Run 1 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should be `889e8cb` (verify with
`git log --oneline -5`).

SESSION TYPE
- Implementation. Phase 2 of ADR-0004 execution — shell-side routing
  for the Durable domain. The L2 foundation is already in place
  (see `HANDOFF_2026-04-24_M2_RUN_1_PHASE_1.md` §2).
- Scope: DomainStoreRegistry + perform_memory_* routing + retention
  sweep extension + embedding forget cascade + shell tests + doc
  update. Commit cadence: 3–4 commits.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `./scripts/current_status.sh` (Windows fallback:
   `python scripts/current_status.py`). Paste the output. Fix from
   commit 344fbcf means this now surfaces the correct newest handoff.
2. `git log --oneline -15`. Confirm these are in history:
   - `889e8cb` ADR-0004 phase 1 (L2 parameterization)
   - `d93b2f5` ADR-0004 doc
   - `4c0b364` ADR-0003 model defaults
   - `344fbcf` hygiene chore
   - `090eecb` Milestone 2 plan
3. Read, in order:
   - `HANDOFF_2026-04-24_M2_RUN_1_PHASE_1.md` (this handoff —
     foundation complete).
   - `docs/adr/ADR-0004-durable-store-shape.md` §§3, 4, 6, 7 (the
     decisions phase 2 consumes).
   - `packages/l2-memory/src/sqlite_session.rs` the new
     `with_table` / `open_session_and_durable` surface.
   - `apps/desktop/src-tauri/src/state.rs` — where
     `self.memory: Arc<dyn SessionMemoryStore>` lives today.
   - `apps/desktop/src-tauri/src/memory_service.rs::perform_memory_write`
     + `memory_forget` + `memory_forget_item` + `memory_edit` —
     the five paths to route.
   - `apps/desktop/src-tauri/src/memory_service.rs::maybe_embed_on_write`
     + forget-cascade surface.
   - Retention sweep owner (grep `prune_before` or
     `retention_tick` in `apps/desktop/src-tauri/src/`).

================================================================
§STATUS CORRECTION
================================================================

- Five subsystems CLOSED + rot-guarded. Memory V2 has per-domain
  storage in L2 but not yet in the shell.
- Default models: gemma4:e4b (text), bge-m3 (embed). Both unverified
  on real hardware; not a blocker for phase 2 (no Ollama traffic in
  phase 2 scope).
- 76 decisions total. #M2-04 and #M2-05 resolved; others reserved.

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

- **#M2-01 / #M2-02 / #M2-03** — Retrieval Wiring. Belong to Run 2,
  NOT this run. Hold.
- **#M2-06 / #M2-07 / #M2-08** — future runs. Hold.
- Git push. Requirement IDs. Gemma rollback. Unchanged.

================================================================
§DELEGATED DECISIONS (you may decide)
================================================================

- Where exactly the DomainStoreRegistry lives (new file in
  `apps/desktop/src-tauri/src/` vs. fields on AppState).
- Whether retention.rs sweeps all domains in one tick or schedules
  per-domain ticks — lean single tick, mirrors the existing sweep
  shape in `a1e9028`.
- Naming for new shell telemetry (keep the existing
  `memory_forgotten` kind; don't invent new ones).
- Aggregated-vs-per-item telemetry policy for Durable sweeps —
  Decision #56 (aggregated) should continue to apply; don't reopen.

================================================================
§PHASE — ADR-0004 Phase 2
================================================================

Commit 1 — DomainStoreRegistry + startup wiring.
- Build the registry (either struct or a field cluster on AppState
  holding `Arc<dyn SessionMemoryStore>` per domain).
- At startup, call `DurableSessionStore::open_session_and_durable`
  and populate the registry with Session + Durable entries.
- The existing `self.memory` field becomes the Session entry of
  the registry (or keep it named `memory` and add `memory_durable`).

Commit 2 — Route the five memory paths.
- `perform_memory_write`, `memory_forget`, `memory_forget_item`,
  `memory_edit`, and the recall path resolve their target store
  from the registry.
- Fallback: if a domain has no registry entry (Projects/Artifacts
  today), continue routing to Session with a `warn!` citing the
  known limitation. Do NOT silently drop writes.

Commit 3 — Retention sweep extension + embedding forget cascade.
- Retention sweep walks every domain with a registry entry and
  prunes with `memory.json::retention_days.<domain>` TTL. Session
  keeps existing behaviour; Durable picks up the 30-day default.
- Aggregated `memory_forgotten` telemetry extends to Durable (one
  row per domain per sweep when >0 rows evicted).
- `memory_forget_item` on a Durable row also calls
  `EmbeddingStore::delete(Durable, &MemoryId::new(&memory_id))`
  best-effort after the primary remove succeeds.

Commit 4 (maybe bundled with 3) — Shell tests + doc update.
- Tests covering: Durable write lands in durable_log (verify via
  direct SQL), Durable recall returns only Durable rows, Session
  write still lands in conversation_log, retention sweep prunes
  Durable-age rows without touching Session, embedding forget
  cascade on per-item Durable forget.
- `docs/MEMORY-V2-ARCHITECTURE.md` §§5, 10 updated to reflect
  Durable coverage.
- Rot-guard anchors on `tools/lint-memory-doc/check.py` gain entries
  for: `DomainStoreRegistry` (or equivalent), `open_session_and_durable`
  usage in state.rs, Durable-lane sweep symbol.

### Out of scope (defer)

- Retrieval wiring (Run 2).
- Projects/Artifacts routing (ADR-0005).
- Any UI surface — Memory tab changes are Run 6.
- Any pnpm eval / CI work.

================================================================
§DONE WHEN
================================================================

- `cargo test --workspace` clean, including new shell tests.
- A write with `MemoryDomain::Durable` persists a row in
  `durable_log` (verified by a test that inspects SQLite via
  `rusqlite::query_row`). Session writes stay in `conversation_log`.
- Durable recall returns rows written via Durable only.
- Retention sweep honours per-domain TTL; Session ≠ Durable ttl
  behaviour.
- Embedding forget cascade tested.
- `python tools/lint-memory-doc/check.py` passes after anchor adds.
- `apps/desktop && pnpm typecheck && pnpm test && pnpm build`
  clean. No UI change expected.

================================================================
§CHECK MATRIX
================================================================

Same shape as this handoff's §3. New shell test count in the
"apps/desktop/src-tauri cargo test" row (expect +6 to +10).

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix. All green.
2. Clean working tree.
3. Execution report:
   `DURABLE_ROUTING_EXECUTION_REPORT_2026-04-25.md`.
4. Handoff `HANDOFF_2026-04-25_M2_RUN_1_PHASE_2.md` with commit
   table, check matrix, decisions log, next prompt for Run 2
   (Retrieval Wiring).
5. `git push origin dev`. Milestone 1 retrospective §3 item 3
   made "push after every run" doctrine.

================================================================
§STANCE
================================================================

The L2 foundation (commit 889e8cb) is frozen. Phase 2 is mechanical
shell routing on top of it. Keep the DomainStoreRegistry a small
struct — don't over-abstract. Every routed path is a single
`registry.get(domain)` call. Mirror existing patterns, don't invent
new ones.

Good luck.
````

---

## 8. Session-end gate

- [x] Five commits landed, all pushed.
- [x] Rot guards pass.
- [x] Full check matrix green.
- [x] Memory (auto) updated: Aether state snapshot + gemma4 adoption files reflect new defaults.
- [x] `origin/dev` at `889e8cb`.

---

(end of handoff)
