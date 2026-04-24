# Handoff — 2026-04-24 Milestone 2 Run 2 (COMPLETE)

**Written:** 2026-04-24 session end (final wiring session).
**Branch:** `dev`. Tip `5b3ad94`. All commits pushed to `origin/dev`.
**Working tree:** clean.

Run 2 is done. Retrieval is live on real turns when `embeddings.enabled = true`.

---

## 1. Commit table (Run 2 total)

| SHA | Subject |
| --- | --- |
| `5b96469` | docs(adr): add ADR-0005 — retrieval wiring design |
| `e2fd34f` | feat(l2,l5,l7): ADR-0005 enabler layer — RetrievalContext + fetch_one |
| `9e6b8b0` | feat(retrieval,l5): ADR-0005 orchestrator + RetrievalContext preset defaults |
| `3ba40fc` | docs: Run 2 partial handoff — orchestrator ready, wiring pending |
| `3167850` | feat(memory-config): add RetrievalConfig.max_items for ADR-0005 wiring |
| `9fad125` | feat(retrieval,commands): wire run_retrieval_context into submit_turn |
| `5b3ad94` | docs+test+rot(retrieval): close ADR-0005 — doc §10 step 8, anchors, e2e tests |

Seven commits, all pushed. Eleven commits in Milestone 2 Run 2 total (+4 this session).

See `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-24.md` for the full run-2-final breakdown.

---

## 2. What's live

- `submit_turn` → `run_retrieval_context(state, SESSION_ID, &text, cfg.retrieval.max_items, DEFAULT_RETRIEVAL_DEADLINE)` → `format_retrieval_block(&hits)` → `augment_utterance(block, text)` → `TurnRequest { utterance: router_utterance, ... }` → L1 engine → router → provider.
- `memory.json::retrieval.max_items` (default 5) gates the top-K cap. Zero disables injection without flipping `embeddings.enabled`.
- Memory records the ORIGINAL utterance via `user_record_raw`; `PendingTurn.original_utterance` keeps the approval-replay path drift-free.
- L5 gate at `Capability::RetrievalContext` still fires even when retrieval returns empty — one audit row per retrieval invocation.

---

## 3. Check matrix (post-session)

| Check | Result |
| --- | --- |
| `git status` | clean |
| Commits ahead of `origin/dev` | 0 (pushed) |
| `cargo fmt --all -- --check` | clean |
| `cargo check --all-features` (shell) | clean (2 pre-existing L1 warnings unchanged) |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings" --test sqlite_session` | 23 / 23 |
| `apps/desktop/src-tauri cargo test --all-features` | **230 / 230** (was 223; +7) |
| `cargo test --workspace` | all green |
| `python tools/lint-memory-doc/check.py` | **OK 79 / 19** (was 70 / 16) |
| `python tools/lint-quality-doc/check.py` | OK 60 / 19 |
| `tools/evals --dry-run` | 6 / 6 |

---

## 4. Risks / alerts

### A. (RETIRED) Retrieval live-on-turn gap.
Closed this session. `submit_turn` invokes the orchestrator on every real turn; tests pin determinism (off-path byte-identical) and happy path (on-path augments).

### B. (CARRIED) `gemma4:e4b` + `bge-m3` unverified on real hardware.
First `ollama pull gemma4:e4b && ollama pull bge-m3` + on-flag session validates both picks. Recommend pairing this with Run 3.

### C. (RETIRED) Run 2 decisions #M2-01 / #M2-02 / #M2-03 / #M2-15.
Shipped in code.

### D. (RETIRED) Run 1 phases.
Unchanged from prior handoff.

### E. (CARRIED) Projects / Artifacts / Facts / Preferences still alias Session.
ADR-0006 territory.

### F. (SIDESTEPPED) `AppState::build_active` ownership.
Chosen integration path (retrieval in `submit_turn`, not in the router) made this irrelevant. If Run 3 or later re-opens path (a), re-read §3 of the predecessor handoff.

### G. (NEW) Augmented utterance reaches the L1 audit trail.
Because retrieval composes the augmented string BEFORE `engine.handle_turn` and stuffs it into `TurnRequest.utterance`, any audit surface that logs raw request utterances sees the augmented form. Memory + transcript are protected (via `user_record_raw`), but a future L5 audit viewer would show the block. If that becomes a concern, widen `TurnRequest` with `retrieval_context: Option<String>` and have the router concatenate — a scoped L1 change.

---

## 5. Decisions log

Milestone 2:
- **#M2-01 / #M2-02 / #M2-03 / #M2-15** — RESOLVED by ADR-0005 (shipped).
- **#M2-04 / #M2-05** — RESOLVED by ADR-0004 (Run 1).
- **#M2-06 / #M2-07 / #M2-08** — reserved (future runs — Gap #3 auth, CI ADR, CI blocking).
- **#M2-09..#M2-14** — shipped in Mini-Run 0.

No new numbered decisions in Run 2 final — all delegated decisions (integration path, prompt format, config shape) are documented inline in `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-24.md` §1.

---

## 6. Next session prompt — M2 Run 3 (Embeddings Onboarding)

Paste-verbatim block:

````md
You are Claude Code, opening Milestone 2 Run 3 for Aether.

Repo root: C:/Users/dbhav/Projects/aether/
Branch: dev. Session-start tip should be `5b3ad94` or later (verify
with `git log --oneline -10`).

SESSION TYPE
- Discuss → Plan → Execute for Run 3: Embeddings Onboarding.
  Run 2 shipped the wiring but `memory.json::embeddings.enabled`
  still defaults to `false` and there is no onboarding surface.
  Run 3 designs and ships the user-facing path for flipping it
  on: model pulls, readiness checks, per-domain backfill, and a
  Settings-drawer toggle.

================================================================
§MANDATORY FIRST STEPS
================================================================

1. `python scripts/current_status.py`. Should surface
   `HANDOFF_2026-04-24_M2_RUN_2_COMPLETE.md`.
2. `git log --oneline -15`. Confirm 5b3ad94, 9fad125, 3167850 in
   history.
3. Read in order:
   - `HANDOFF_2026-04-24_M2_RUN_2_COMPLETE.md` (this handoff — §4
     captures still-open risks and §7 captures the Milestone 2
     theme).
   - `RETRIEVAL_WIRING_EXECUTION_REPORT_2026-04-24.md` — notes on
     delegated decisions that may constrain Run 3 choices.
   - `docs/adr/ADR-0005-retrieval-wiring.md` — the wiring shipped.
   - `docs/adr/ADR-0003-...` — gemma4:e4b + bge-m3 defaults.
   - `apps/desktop/src-tauri/src/memory_config.rs` — the flag.
   - `apps/desktop/src-tauri/src/retrieval.rs` — what "on" means.

================================================================
§STATUS CORRECTION
================================================================

- Milestone 2 Run 1 (ADR-0004 Durable) complete and rot-guarded.
- Milestone 2 Run 2 (ADR-0005 Retrieval wiring) COMPLETE.
  Retrieval is live on turns when the flag is on.
- Run 2 Risk B is still open: `gemma4:e4b` + `bge-m3` unverified
  on real hardware. Run 3 is the natural home for that
  verification.

================================================================
§RESERVED DECISIONS (do NOT resolve autonomously)
================================================================

- **#M2-06 / #M2-07 / #M2-08** — future runs.
- Git push, requirement IDs, Gemma rollback — unchanged.

================================================================
§DELEGATED DECISIONS (pick, document, move on)
================================================================

Run 3 shape is genuinely open — follow the standard Discuss →
Plan → Execute cadence rather than jumping to implementation.
Expect to produce ADR-0006 (or similar) for the onboarding
surface.

================================================================
§PHASE — discuss
================================================================

Start with `/gsd-discuss-phase` on Run 3. Key gray areas the
discussion should surface:

- Model-pull UX: in-app button, CLI-only, or first-run wizard?
- Readiness check cadence: per-turn, per-session, per-boot?
- Backfill scope: "now only" vs "embed all existing Durable rows"
  vs "on-demand".
- Failure modes: what UX when pull fails / model missing / provider
  down?
- Telemetry: `memory_retrieval` kind exists (rot-guarded), but
  per-retrieval metrics (hit rate, avg score, bailout rate) aren't
  wired yet — are they Run 3 or Run 4?

================================================================
§DONE WHEN
================================================================

- ADR for onboarding accepted and rot-guarded.
- `memory.json::embeddings.enabled` can be flipped through the
  shell (not just by hand-editing JSON) without crashing the app
  on first turn under flag-on with no model installed.
- On-hardware verification of gemma4:e4b + bge-m3 complete OR
  clearly deferred to Run 4 with a written reason.

================================================================
§SESSION-END DISCIPLINE
================================================================

Usual drill: full check matrix, execution report, handoff with
commit table + next prompt, push.

================================================================
§STANCE
================================================================

Run 2 closed cleanly; Run 3 is not a continuation of wiring, it's
a new sub-problem (onboarding). Treat it as a fresh discuss/plan
cycle, not an implementation session. If the discuss phase
surfaces scope creep beyond ~1 session, split further.

Good luck.
````

---

## 7. Milestone 2 theme so far

"Retrieval-aware + user-facing."

- Mini-Run 0: gemma4:e4b + bge-m3 defaults (ADR-0003).
- Run 1: Durable lane — migration 0005, per-domain routing, retention sweep (ADR-0004). ✅
- Run 2: Retrieval wiring — capability, orchestrator, config, submit_turn integration (ADR-0005). ✅
- Run 3 (next): Embeddings onboarding.
- Run 4+: TBD during M2 mid-course check.

---

## 8. Session-end gate

- [x] Run 2 wiring commit shipped.
- [x] Retrieval live-on-turn invariant tested.
- [x] Doc §10 step 8 + rot-guard anchors landed.
- [x] 230/230 shell tests, 23/23 L2 sqlite, 79/19 memory rot-guard, 6/6 evals.
- [x] All commits pushed to origin/dev.
- [x] Execution report written.
- [x] Next-session prompt drafted.

---

(end of handoff)
