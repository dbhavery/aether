# Handoff — 2026-04-25 Milestone 2 Run 2 (partial — orchestrator ready, wiring pending)

**Written:** 2026-04-25 session end (continuation of the Run 1 marathon).
**Branch:** `dev`. Tip `9e6b8b0`. All commits pushed to `origin/dev`.
**Working tree:** clean.

Run 2 is ~80% done. All four ADR-0005 decisions land, enabler layer ships, the retrieval orchestrator passes 9 tests in isolation. Final step — wiring the orchestrator into `MemoryAwareRouter::dispatch` / `RoleTaggedOllamaRouter::dispatch` — is a small structural commit that deserves a fresh session.

---

## 1. Commit table (Run 2 so far)

| SHA | Subject |
| --- | --- |
| `5b96469` | docs(adr): add ADR-0005 — retrieval wiring design |
| `e2fd34f` | feat(l2,l5,l7): ADR-0005 enabler layer — RetrievalContext + fetch_one |
| `9e6b8b0` | feat(retrieval,l5): ADR-0005 orchestrator + RetrievalContext preset defaults |

Three commits, all pushed. (Ten commits in Milestone 2 total.)

---

## 2. What shipped

### ADR-0005 accepted
All four decisions locked:
- **#M2-01:** `Capability::RetrievalContext` (wire token `retrieval_context`).
- **#M2-02:** Sequential pipeline — intent → Memory V2 enrichment → retrieval_context → prompt build → model. 5-second bailout warn-and-continue.
- **#M2-03:** Score desc → recency tiebreak → top-K (default 5, configurable via `memory.json::retrieval.max_items`).
- **#M2-15:** `SessionMemoryStore::fetch_one(session_id, sequence)` trait extension.

See file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0005-retrieval-wiring.md.

### Enabler layer
- `Capability::RetrievalContext` variant added to L5 policy enum.
- `wave3.balanced` preset has `RetrievalContext` entry (Auto / Low).
- `default_risk_for(RetrievalContext) = Low`.
- `human_capability` in L7 trust maps to `"retrieval_context"` string.
- `SessionMemoryStore::fetch_one` trait method + impls on both InMemory and SQLite backends.
- +3 L2 integration tests covering `fetch_one`.

### Orchestrator
- New module file:///C:/Users/dbhav/Projects/aether/apps/desktop/src-tauri/src/retrieval.rs.
- `run_retrieval_context(state, session_id, utterance, max_items, deadline) -> Vec<RetrievalHit>` runs the embed → query_nearest → fetch_one → rank pipeline.
- L5 gate via `Capability::RetrievalContext`; policy deny returns `[]` + `warn!`.
- Coarse wall-clock deadline across phases (5s default); bailout returns `[]` + `warn!`.
- Stale embedding hits (`fetch_one` returns `Ok(None)`) drop silently with a `trace!`.
- `parse_memory_id` handles session ids with dashes (`mem-desktop-session-9` → `("desktop-session", 9)`).
- +9 retrieval tests covering parse round-trip, malformed ids, off-by-default, zero-K short-circuit, happy path, rank+K cap, stale-hit drop, bailout.

### Check matrix (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | 0 (pushed) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (2 pre-existing L1 warnings unchanged) |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | **23 / 23** (was 20; +3 fetch_one tests) |
| `apps/desktop/src-tauri cargo test --all-features` | **223 / 223** (was 214; +9 retrieval tests) |
| Python lint-memory-doc | OK 70 / 16 (unchanged) |
| Python lint-quality-doc | OK 60 / 19 (unchanged) |
| Python evals dry-run | 6 / 6 |

---

## 3. What's left in Run 2

One commit remains: wire `run_retrieval_context` into the turn-dispatch path so it actually runs on every real turn.

Two viable integration points:

**(a) Inside `MemoryAwareRouter::dispatch` / `RoleTaggedOllamaRouter::dispatch`.** Add an optional callback field (e.g. `retrieval: Option<Arc<dyn Fn(&str) -> Vec<RetrievalHit> + Send + Sync>>`) to each router. The shell constructs the router with a closure capturing an `Arc<AppState>`.

  - Clean encapsulation: retrieval becomes part of the router's recall story.
  - Catch: `AppState::build_active` currently takes `&self`, which can't clone `Arc<Self>`. Need to restructure so `build_active` receives the `Arc<AppState>` from the caller, or introduce a second construction path.

**(b) Inside `submit_turn` (commands.rs, around line 286).** Call `run_retrieval_context` in the command handler, then pass augmented prompt / context to the router.

  - Simpler plumbing — command handler already has the `AppState` and the utterance.
  - Less clean — splits "memory recall" across two layers (router for session recall, command for retrieval).

**Recommendation:** start with (b). Prove end-to-end with a shell test that flips `embeddings.enabled` on and asserts the prompt contains retrieved content. Then refactor to (a) in a follow-up if the split bothers anyone.

Additional small work that goes with the wiring commit:
- `memory.json::retrieval.max_items` config field (additive, default 5). ADR-0005 §Decision 3 specifies this. The orchestrator already accepts a `max_items` parameter; the command handler reads it from config.
- Shell tests: determinism (embeddings off → byte-identical), fallback (unreachable provider → warn + memory-only), happy path (hits reach the prompt).
- Doc update: `docs/MEMORY-V2-ARCHITECTURE.md` gains a retrieval section (or §10 grows a step 8).
- Rot-guard anchors: `retrieval` module file, `run_retrieval_context`, `RetrievalContext` L5 variant.

Estimated scope: ~100–200 LOC + tests + docs. One focused session.

---

## 4. Risks / alerts

### A. (NEW) Retrieval is wired up but not *live* on real turns.
Flipping `embeddings.enabled = true` today still produces no retrieval behaviour during a turn — the orchestrator only runs if something calls it. `submit_turn` does not yet. This is the single remaining gap.

### B. (CARRIED) gemma4:e4b + bge-m3 unverified on real hardware.
First `ollama pull …` + on-flag session validates both picks.

### C. (RETIRED) Run 2 decisions #M2-01 / #M2-02 / #M2-03 / #M2-15.
All resolved by ADR-0005.

### D. (RETIRED) Run 1 phases.
All three phases (ADR-0004 L2, shell routing, tests) shipped earlier in this session. Durable lane is fully operational.

### E. (CARRIED) Projects / Artifacts / Facts / Preferences still alias Session.
ADR-0005 / ADR-0006 territory. Fallback path emits a `warn!`.

### F. (NEW) `AppState::build_active` ownership pattern needs a small refactor if integration path (a) is chosen.
Call out: the method takes `&self`, so capturing `Arc<Self>` inside it requires either `Arc::clone(&arc_self)` passed from the caller or a separate constructor. Handle when writing the wiring commit.

---

## 5. Decisions log

Milestone 2:
- **#M2-01 / #M2-02 / #M2-03 / #M2-15** — RESOLVED by ADR-0005.
- **#M2-04 / #M2-05** — RESOLVED by ADR-0004 (Run 1).
- **#M2-06 / #M2-07 / #M2-08** — reserved (future runs — Gap #3 auth, CI ADR, CI blocking).
- **#M2-09..#M2-14** — shipped in Mini-Run 0.

No new numbered decisions in this commit sequence — ADR-0005 captures them as part of the ADR, and #M2-15 is the new fetch-method decision locked in §4 of the ADR.

---

## 6. Next session prompt — M2 Run 2 wiring (final)

Paste-verbatim block:

````md
You are Claude Code, finishing Milestone 2 Run 2 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should be `9e6b8b0` or later (verify
with `git log --oneline -10`).

SESSION TYPE
- Implementation. Final wiring commit for Milestone 2 Run 2 —
  make retrieval actually run during turns. The orchestrator
  (apps/desktop/src-tauri/src/retrieval.rs) is already tested in
  isolation; this session connects it to the turn-dispatch path.
- Scope: ~100–200 LOC + tests + doc + rot-guard anchor adds.
  One commit, possibly two if the config-field add splits
  naturally.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `python scripts/current_status.py`. Should surface
   `HANDOFF_2026-04-25_M2_RUN_2_PARTIAL.md`.
2. `git log --oneline -15`. Confirm 9e6b8b0, e2fd34f, 5b96469 in
   history.
3. Read in order:
   - `HANDOFF_2026-04-25_M2_RUN_2_PARTIAL.md` (this handoff — §3
     captures the two integration options + the recommendation).
   - `docs/adr/ADR-0005-retrieval-wiring.md` — §Decision 1 timing,
     §Decision 3 rank + config field.
   - `apps/desktop/src-tauri/src/retrieval.rs` — the existing
     orchestrator API.
   - `apps/desktop/src-tauri/src/commands.rs` around `submit_turn`
     (line ~286) — the recommended integration point.
   - `apps/desktop/src-tauri/src/memory_config.rs` — where the new
     `retrieval.max_items` field lands.

================================================================
§STATUS CORRECTION
================================================================

- All four ADR-0005 decisions accepted.
- Retrieval orchestrator ships isolated (9 tests green).
- Enabler layer (L5 variant + L2 fetch_one + preset default) ships.
- Run 1 (ADR-0004 Durable) complete and rot-guarded.
- Defaults: gemma4:e4b / bge-m3 (ADR-0003; unverified on real
  hardware).

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

- **#M2-06 / #M2-07 / #M2-08** — future runs.
- Git push, requirement IDs, Gemma rollback — unchanged.

No reserved decisions for THIS run — all of Run 2's decisions
closed in ADR-0005.

================================================================
§DELEGATED DECISIONS
================================================================

- Integration path: (a) router-callback vs (b) command-handler
  (this handoff recommends (b); override freely if (a) proves
  clean once you read the code).
- Shape of the `memory.json::retrieval` sub-object — mirror the
  `embeddings` field's additive-on-read semantics.
- How retrieved hits render into the prompt: prepend as a
  "Relevant context:" block, append, or interleave with session
  recall. Pick one; document in the prompt-builder comment.

================================================================
§PHASE — wiring
================================================================

Commit 1: config field.
- Add `retrieval: RetrievalConfig { max_items: u32 (default 5) }`
  to the `MemoryConfig` shape. Additive, default-safe on read.
- Update the serde round-trip test that lives alongside
  MemoryConfig.

Commit 2: wire run_retrieval_context into submit_turn.
- Call `run_retrieval_context(state, session_id, utterance,
  cfg.retrieval.max_items, DEFAULT_RETRIEVAL_DEADLINE)` at the
  right point in the turn pipeline — per ADR-0005 §Decision 1,
  AFTER memory recall and BEFORE prompt construction.
- When the hit vec is non-empty, prepend a deterministic block
  to the prompt the router receives. Format proposal:
  ```
  Relevant context (retrieval):
  [N1] <domain> <memory_id>: <content>
  [N2] ...
  ```
  (Exact format is a delegated decision — pick one, document,
  test the determinism.)
- When the vec is empty (embeddings off, bailout, no hits),
  behaviour must be byte-identical to `9e6b8b0`.

Commit 3 (maybe bundled): tests + doc + rot guard.
- Shell tests:
  * determinism — embeddings off → byte-identical window vs
    pre-wire behaviour.
  * fallback — unreachable provider → memory-only prompt + one
    warn! per turn.
  * happy path — hits seeded + embeddings on → prompt contains
    retrieved content in rank order.
- docs/MEMORY-V2-ARCHITECTURE.md gains a §11 (or §10 step 8)
  describing the retrieval path + the new `retrieval.max_items`
  field.
- tools/lint-memory-doc/check.py gains anchors:
  * file: `apps/desktop/src-tauri/src/retrieval.rs`
  * symbol: `fn run_retrieval_context`
  * symbol: `pub struct RetrievalHit`
  * string: `Capability::RetrievalContext`
  * file: `docs/adr/ADR-0005-retrieval-wiring.md`

================================================================
§DONE WHEN
================================================================

- A turn with embeddings.enabled=true + seeded Durable rows has
  retrieved content visible in the prompt the router forwards.
- A turn with embeddings.enabled=false is byte-identical to
  before this commit.
- Config field round-trips through memory.json serde.
- Rot guard passes with new anchors.
- All check matrix rows green.

================================================================
§SESSION-END DISCIPLINE
================================================================

1. Full check matrix.
2. Clean working tree.
3. Execution report:
   `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-26.md`.
4. Handoff `HANDOFF_2026-04-26_M2_RUN_2_COMPLETE.md` with commit
   table, retired risks (A from this handoff retires), next
   prompt for M2 Run 3 (Embeddings Onboarding).
5. `git push origin dev`.

================================================================
§STANCE
================================================================

The orchestrator is proven. You don't need to redesign it. Read
the two integration options in §3 of the predecessor handoff,
pick one, wire it, test it, ship it. Don't reopen ADR-0005.

Good luck.
````

---

## 7. Session totals (across the whole marathon)

Commits shipped this session across Run 1 + Run 2:

- Milestone 2 opening (planning artefacts): 090eecb
- Hygiene chore: 344fbcf
- Mini-Run 0 (ADR-0003): 4c0b364
- ADR-0004 accepted: d93b2f5
- Run 1 phase 1 (L2): 889e8cb
- Phase 1 handoff: 8d739b5
- Run 1 phase 2 (routing): 43f29cc
- Run 1 phase 3 (isolation tests): 827eea4
- Run 1 complete handoff: 3ffe105
- ADR-0005 accepted: 5b96469
- Run 2 enabler layer: e2fd34f
- Run 2 orchestrator: 9e6b8b0
- This handoff (upcoming commit)

13 commits. 214 → 223 shell tests (+9). 60/12 → 70/16 memory rot guard. Two ADRs shipped (0004, 0005). Milestone 2 roadmap amended + back on track.

---

## 8. Session-end gate

- [x] Retrieval orchestrator proven (9/9 tests).
- [x] L5 + L2 + L7 enabler layer shipped.
- [x] All ADR-0005 decisions accepted.
- [x] Three Run 2 commits pushed.
- [ ] Final wiring commit (next session).

---

(end of handoff)
