# Aether Full-Scope Audit — 2026-04-28

**Written:** 2026-04-28 (mid-autonomous session, after V4 prelaunch eval landed).
**Purpose:** Don asked for a full project audit to rewrite the todo list. Pulls together open work across every active workstream so we can prioritize, not just keep going on training.

**Branch:** `dev` at `252eca6`. Working tree clean. Pushed.

---

## 1. Workstream snapshot

| # | Workstream | State | Owner of next move |
|---|---|---|---|
| A | Conversation training (V1→V4) | V4 prelaunch eval **shipped**; V4 LoRA training queued | Claude (autonomous) |
| B | M2 Run 2 — retrieval orchestrator wiring | 80% — orchestrator built + 9/9 tests; **submit_turn wiring pending** | Claude or Don |
| C | Vision track (companion build) | 3 vision providers + registry + cue history shipped per CONTINUE handoffs (commits not yet on this branch) | Don decision |
| D | Quality-Eval V2 + Aurora discipline | 3/6 PASS; **fridge fixture** + 10th-paraphrase decision blocking 2 more | Don 5-min items |
| E | Backfill / Ollama hardening | FLASH_ATTENTION workaround **verified**; needs permanent env set | Don 5-min |
| F | Retrieval calibration at real-conv scale | 150-passage baseline only; 500-1000 synthetic-corpus run **queued** | Claude (autonomous) |
| G | ADR-0011 cross-encoder production wire | Deferred until real conversation data exists | Future |
| H | Aurora-strict canary suite | Defensive, ~1-2h; **landed in commit `100a36f`** ✓ | Done |

---

## 2. Workstream A — Conversation training (most active)

### Where we are
- V1 killed (7B + bad eval cadence).
- V2 done (32% real-human, 100% trained, naive eval).
- V3 paused at 74% (84% real-human; new corpora: Cornell, Reddit, podcasts).
- **V4 prelaunch eval landed today.** New multi-model discriminator (5 AI sources vs 10k humans, 79.8% accuracy). Held-out scoring confirms fine-tuning IS doing real work: V3-partial 26.5% human-rate vs raw base 6.5% vs gemma4 1.0%; humans 87.1% ceiling. Detail at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V4_PRELAUNCH_EVAL.md.
- Don's decisions locked just now:
  - Q1 → option B (match human distribution, not just fool snippets)
  - Q2 → V4 single blended register; persona-conditioning deferred to V5
  - Q3 → LoRA continuation from V3 checkpoint-3000

### Open V4 work (this session)
1. Pull §4.3 corpora (OpenSubtitles, screenplays, re-mined Lex Fridman) — ~1h.
2. Normalize + restratify per §4.4 — ~30min.
3. Train V4 LoRA continuation from V3 checkpoint-3000 — ~5h.
4. Eval V4 against multi-discriminator + WildChat held-outs — ~30min.
5. Self-test multi-turn convos (since real human panel unavailable) — ~1h.

### Decision rule for V5
- If V4 → V3-partial gain is ≥+10pp on multi-discriminator: stay on LoRA.
- If <+5pp: move to full SFT for V5.
- Persona-conditioning unlocks in V5 regardless.

---

## 3. Workstream B — M2 Run 2 wiring (PRODUCTION-PATH BLOCKER)

The retrieval orchestrator (`apps/desktop/src-tauri/src/retrieval.rs`) is built, tested 9/9, and ratified by ADR-0005. **It is not yet called on real turns.** That means everything we've built for retrieval-aware turn dispatch sits dormant until one of two integration paths lands:

- **Path (a):** add retrieval callback to MemoryAwareRouter / RoleTaggedOllamaRouter (~half day; needs AppState plumbing).
- **Path (b):** call `run_retrieval_context` from `submit_turn` directly (~hour; less encapsulated).

Per HANDOFF_2026-04-25_M2_RUN_2_PARTIAL.md §3, Don's recommendation was to do this in a fresh session.

**This is the highest-leverage non-training item right now.** Every subsequent retrieval-quality decision (calibration, cross-encoder, backfill payoff measurement) is meaningless until orchestrator runs in production path.

---

## 4. Workstream C — Vision track (status unclear)

Per HANDOFF_2026-04-27/04-28/04-29 (CONTINUE_COMPANION series), three vision-track features were built:
- Vision-capable `analyze_frame` (Ollama + llama.cpp)
- Vision provider registry + runtime swap
- Per-panel cue history + Trust drawer media filter
- Vitest harness (41 tests)

**Caveat:** these handoffs were written 2026-04-25 to 2026-04-27 across three sessions, but the commits referenced (e.g. `cdf31f8`, `4ae9a13`, `dfb815b`) are **not on the current `dev` branch tip.** Either:
- They live on a different branch / fork
- They were rolled back
- The handoffs document planned-but-not-shipped work

Don should clarify before the next session decides whether to advance vision or treat it as already-done.

---

## 5. Workstream D — Quality-Eval V2 + Aurora discipline

3/6 scenarios PASS. Two more would PASS with manual items:

| Scenario | Blocker | Action |
|---|---|---|
| `vision_response_quality` | Missing `tools/evals/fixtures/fridge_open.jpg` | Don commits the fixture (~2 min) |
| `memory_appropriateness` | Aurora produced "Got it. Let's leave that out of it." — 10th paraphrase variant outside the 9 documented | Decision: add 10th, or leave as canary (recommended) |

Aurora-strict canary suite landed (`100a36f`). Drift detector active.

---

## 6. Workstream E — Backfill / Ollama hardening

**FLASH_ATTENTION=false workaround empirically confirmed** (65/65 on previously-failing rows). Without it, F1 retry helps but can't kill the content-deterministic NaN bug.

Action: set `OLLAMA_FLASH_ATTENTION=false` permanently in startup env. ~5 min. Don's call.

Optional: comment on https://github.com/ollama/ollama/issues/13572 with workaround verification (paste-ready text in `OLLAMA_UPSTREAM_BUG_REPORT.md`).

---

## 7. Workstream F — Retrieval calibration at real-conv scale

The 2026-04-24 validation Block 5 used 150 passages — representative but small. At realistic Aether scale (500-2000 conversation turns over a few months), rank quality may degrade.

GPU-heavy queue item. Per HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION §3A:
1. Generate 50-100 synthetic conversation threads with cross-thread referential structure
2. Embed with bge-m3 (Flame default)
3. Re-run `bench_long_context.py`
4. Measure recall@1/3/5/10/20, MRR
5. If recall craters, ADR-0011 (cross-encoder) becomes urgent and the rank function may need recency-weighted combine

**Defer until M2 Run 2 wiring is done** — calibration without orchestrator-in-prod-path measures the wrong thing.

---

## 8. Workstream G — ADR-0011 cross-encoder

Per ADR-0010 D-018: Option B (bge-reranker-v2-m3 cross-encoder) gave +2.8pp recall@1 on synthetic corpus, but per-query rerank latency cost is real.

Deferred until: Aether has real conversation data to measure against. Synthetic-corpus rank evolution may not predict real-world impact.

When it lands, scope around *which* retrieval calls get rerank (audit-search vs everyday turns), not global enable.

---

## 9. Cross-cutting: process incidents from prior session

5 working-tree contamination incidents from parallel-agent index races (D-008, D-011, D-012). Required mitigations for any future autonomous run with parallel agents:
- Use `git commit -o <pathspec>` not `git add . && git commit`
- OR worktree-per-agent via `superpowers:using-git-worktrees`
- OR serialize `planning/` writes through one agent at a time

Single-agent autonomous runs (like this one) bypass this risk.

---

## 10. Consolidated todo list — priorities

Ranked by leverage × time-to-value × current-session-fit:

### Tier 1 — autonomous-run targets (this session, 12h budget remaining)

1. **V4 LoRA training arc** (training session continuation)
   - Pull new corpora (~1h)
   - Restratify (~30min)
   - Train V4 LoRA continuation (~5h)
   - Eval against multi-discriminator + WildChat (~30min)
   - Self-test multi-turn convos (~1h)
   - **Total: ~8h.** Fits.

2. **Real-corpus retrieval calibration** (parallel candidate)
   - 50-100 synthetic conversation threads, 500-1000 passages
   - Bench against `run_retrieval_context` orchestrator (in-isolation, since prod-path wiring is not done)
   - **Total: ~2h.** Could fit in parallel slots while V4 trains.
   - **Risk:** measuring without prod-path wiring may not represent real recall behavior. Limited value vs cost — defer.

### Tier 2 — Don decisions (5 min each, can be queued before AFK ends)

3. Set `OLLAMA_FLASH_ATTENTION=false` permanently
4. Commit `tools/evals/fixtures/fridge_open.jpg` to unblock vision_response_quality eval
5. Decide 10th-paraphrase: add to expectations, or leave as canary
6. Clarify workstream C status (are the vision-track CONTINUE_COMPANION commits real or planned?)

### Tier 3 — next-session work (not this session)

7. **M2 Run 2 wiring** (orchestrator into submit_turn) — requires fresh session per Don's prior recommendation; AppState plumbing requires care.
8. **Comment on ollama#13572** — optional outreach.
9. **Aurora-strict canary suite** — already landed (`100a36f`); maintenance only.

### Tier 4 — deferred (await trigger)

10. **ADR-0011 production wire** — wait for real conversation data.
11. **Retrieval calibration at real-conv scale** — wait for orchestrator wiring (item 7) so measurement reflects production path.
12. **V5 (full SFT or persona-conditioning)** — wait for V4 results.

---

## 11. Recommendation for the rest of this session

**Execute Tier 1 item 1 (V4 LoRA training arc) end-to-end.** Reasoning:

- Don explicitly authorized "keep training" + "self test convos" before asking for the audit.
- V4 is the highest-leverage thing I can do alone (no Don decisions blocking).
- M2 Run 2 wiring needs a fresh-session AppState refactor that's risky to start with 12h left and a long-running training job in flight.
- Real-corpus retrieval calibration without orchestrator-in-prod-path measures the wrong thing.

After V4 training completes:
- Write V4_RESULTS.md with eval numbers + self-test transcripts
- Surface results + clear recommendation for V5 direction
- Wait for Don

If V4 finishes early (under 8h), candidate fillers in priority order:
- Generate/curate seed prompts for V5 persona-conditioning data prep
- Triage open vision-track question (workstream C clarification)
- Doc sweep: update V4_PRELAUNCH_EVAL.md with V4 results

(end of audit)
