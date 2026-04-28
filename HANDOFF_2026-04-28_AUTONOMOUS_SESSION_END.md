# Handoff — 2026-04-28 Autonomous Session End

**Written:** 2026-04-28 at session close.
**Branch:** `dev`. Tip: `8940c8e`. All commits pushed. Working tree clean.
**Session profile:** ~18-hour single-agent autonomous arc with one parallel terminal (Term 2) used for verification + scope-audit correction.
**Agent posture:** Don was AFK twice (16h + 9h windows). Full delegated authority including model training, eval methodology rebuilds, scope-audit corrections, and intermediate decisions inside locked goal corridors.

This document is the comprehensive consolidation. Read it cold to take over the project at the start of the next session.

---

## 0. Project vision — what Aether is and is becoming

### 0.1 Who it's for

Aether (private codename: Isabelle) is **Don's personal AI assistant** — singular user, singular maintainer. Architecture decisions optimize for one person's experience, not a market. This is a deliberate choice; it's why the trust drawer is content-rich rather than minimal, why the persona is hand-authored rather than RLHF'd, why the codebase is a layered Rust/TS monorepo rather than a thin SaaS shell.

### 0.2 End-product goal

A private, local, persistent AI assistant that genuinely feels like a person:

- **Continuity of memory across sessions.** The assistant remembers what was discussed yesterday, last week, last month, with the same accuracy and recall that a human friend would.
- **Presence-aware responsiveness.** Knows when Don is at-keyboard vs Away vs in-Background-mode, and modulates its own behavior accordingly. Doesn't initiate when Don is mid-flow; surfaces when Don is in interrupt-friendly state.
- **Voice + vision integration.** Can see what Don sees (camera + screen frames via Ollama or llama.cpp vision providers). Can speak with a particular voice (Zonos voice cloning live in QuickGrid TTS sibling project; Aether voice surface deferred).
- **Conversational style indistinguishable from natural human speech.** This is the V*-arc training goal. The assistant should not feel like talking to a chatbot. Talking to it should feel as effortless as talking to someone who knows you.

Privacy-first means **everything runs locally on Don's hardware** (RTX 3090 Ti, 24 GB VRAM). No cloud APIs in the production path. No data leaves the box.

### 0.3 The seven layers

```
L7  trust + UI surface     (Tauri React frontend, Trust drawer)
L6  persona ("Aurora")     (hand-authored character, persona schema)
L5  policy engine          (capability gating, audit, single side-effect writer)
L4  router                 (model selection, retrieval-aware dispatch)
L3  presence               (away / background / engaged detection)
L2  memory                 (Memory V2: ephemeral + durable lanes, embeddings)
L1  reflex layer           (sub-150ms barge-in, repair, attention)
```

`packages/l1-*` through `packages/l6-persona/` plus `apps/desktop/` (Tauri shell). Cross-layer rule: **no direct sibling imports.** Communication is via `event-bus` or typed L5/L6 outputs. Policy is the single writer for side effects.

### 0.4 Philosophy

Captured across 19 numbered planning docs (file:///C:/Users/dbhav/Projects/aether/planning/00_VISION_AND_GUARDRAILS.md through `18_model_router_spec.md`) and a growing ADR series. The five pillars:

1. **Indistinguishable-from-human bar applies to every modality.** Voice, text, presence, retrieval-as-recall — they all serve the impression that the user is talking to a person who remembers.
2. **Calibrated confidence > overconfident wrongness.** Hedge when the model isn't sure.
3. **Don't lie to the user.** Any UI showing what the system is doing must match what the system is actually doing. (Provider-display fix this arc was the canonical instance.)
4. **Surface resource pressure; never silently absorb.** Best-effort + visible warning posture (ADR-0007 §Decision 1).
5. **Atomic small commits, ratify ADRs as you implement them.** A commit that touches an ADR's behavior should also flip the ADR's status from Proposed → Accepted.

---

## 1. Where things stand at session close

### 1.1 Branch and check matrix

```
Branch: dev
Tip:    8940c8e
Status: clean
Pushed: yes (origin/dev = local dev)
```

This session's commits, in order:
```
8940c8e training(v6): RESULTS — multi-turn-format SFT validated; WildChat 28% (+4.5pp over V4)
8a14e49 training(v5): RESULTS — LoRA continuation plateaued; V4 remains best
06a9889 training(v4): RESULTS — V4 +7.5pp on real generalization signals (WildChat, multi-turn)
e2f4ed8 training(v4): pipeline scripts — corpora pull, SFT build, train, eval, self-test
d13a298 planning: STATE_2026-04-28 + ADR-0011 unblock memo (Term 2)
c03b3e3 planning(scope-audit): corrected — M2 Run 2 already closed, stale handoff caught (Term 2)
6e4a509 planning(scope-audit): full project audit + consolidated todo list
252eca6 training: gitignore trainer state dirs and *.pt/*.pth
a8dc58f training(v4-prelaunch): STEP 2E + STEP 3 — multi-model discriminator + V4_PRELAUNCH_EVAL.md
c178e54 training(v4-prelaunch): STEP 2A-D — generate 5x AI negatives + 10k human positives
76af152 training(v4-prelaunch): STEP 1 — raw Qwen2.5-3B base scores 100% on v2 discriminator
```

### 1.2 Subsystem status

| Subsystem | State | Last verified |
|---|---|---|
| L1 reflex | Closed + rot-guarded | 2026-04-23 |
| L2 memory (Memory V2) | Closed + rot-guarded | 2026-04-23 |
| L3 presence | Closed + rot-guarded | 2026-04-23 |
| L4 router (with vision providers) | All 7 vision-track commits on dev | 2026-04-28 |
| L5 policy | Closed | 2026-04-25 (security pass) |
| L6 persona ("Aurora") | Live, hand-authored | ongoing |
| L7 UI / Trust drawer | Live; backfill UI + media filter shipped | 2026-04-26 |
| Quality-Eval V1/V2 | Live; 3-of-6 PASS pending Don 2-min items | 2026-04-26 |

### 1.3 Milestones

- **Milestone 1** — closed 2026-04-23.
- **Milestone 2 — "retrieval-aware + user-facing"** — closed 2026-04-26 (M2 Run 2 wiring landed in `9fad125`, hardened through `66fb51a`). All four ADR-0005 decisions ratified. Production turn-dispatch invokes `run_retrieval_context → format_retrieval_block → augment_utterance` at apps/desktop/src-tauri/src/commands.rs:337–346.
- **Milestone 3** — not yet themed. Awaits Don's call (see §3.4).

### 1.4 V*-arc training (this session's main work)

**V6 is the new best model** for the indistinguishability axis.

| Version | What changed | WildChat | Multi-turn | Eval loss |
|---|---|---:|---:|---:|
| V3-partial (2026-04-26) | 84% real-human, paused at 74% | 16.0% | 27.5% | — |
| V4 (this session) | LoRA continuation + new corpora | 23.5% | 35.0% | 1.433 |
| V5 (this session) | Same recipe, more steps | 24.0% | 28.0% | 1.422 |
| **V6 (this session)** | **Multi-turn-format SFT** | **28.0%** | 33.0% | **1.348** |
| Real human ceiling | (sanity) | 87.1% | — | — |

V6 closes 12pp of the gap to humans on WildChat across the V*-arc. Adapter at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/.

### 1.5 Test counts (last verified during M2 Run 2 close)

- `cargo test --all-features` (apps/desktop/src-tauri): 293/293
- `cargo test --workspace`: green
- `vitest run` (apps/desktop): 232/232
- `python tools/lint-memory-doc/check.py`: OK 122/28
- `python tools/lint-quality-doc/check.py`: OK 60/19
- `python tools/lint-policy-doc/check.py`: OK 34/9
- `python tools/evals __main__.py --backend ollama`: 3/6 PASS (2 blocked on §3.1 items)

These counts have not been re-run since `8940c8e` because this session's work was confined to file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/ (no source-tree changes). They should be revalidated on next-session-start.

---

## 2. Consolidated TODOs from the past several sessions

This is the union of open items across HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md, HANDOFF_2026-04-26_NEXT_AUTONOMOUS_SESSION.md, the V4/V5/V6 training arc, and the vision-track CONTINUE_COMPANION series, with the corrected-audit verifications applied. Items marked **[CLOSED]** are kept here for traceability so future audits don't resurrect them; **[OPEN]** items are real work.

### 2.1 Don 2-minute items

| # | Item | Status | Source |
|---|---|---|---|
| 2.1.1 | Set `OLLAMA_FLASH_ATTENTION=false` permanently in Windows env | **[OPEN]** | HANDOFF_2026-04-26 §3.1 / STATE_2026-04-28 |
| 2.1.2 | Commit `tools/evals/fixtures/fridge_open.jpg` | **[OPEN]** | HANDOFF_2026-04-26 §3.1 |
| 2.1.3 | Decide 10th-paraphrase variant for `memory_appropriateness` (add or leave as canary) | **[OPEN]** | HANDOFF_2026-04-26 §3.2 |
| 2.1.4 | Optional outreach: comment on https://github.com/ollama/ollama/issues/13572 with workaround verification (text drafted in OLLAMA_UPSTREAM_BUG_REPORT.md) | **[OPEN, optional]** | HANDOFF_2026-04-26 §3.1 |
| 2.1.5 | Push `dev` to `origin/dev` | [CLOSED — pushed this session at `8940c8e`] | continuous |

### 2.2 Quality-Eval V2

| # | Item | Status | Source |
|---|---|---|---|
| 2.2.1 | 3 scenario expectations broadened to match Aurora persona (`aacee22`) | [CLOSED 2026-04-25] | HANDOFF_2026-04-25 |
| 2.2.2 | Composition-aware skip for `--backend ollama` (false-fail elimination) | [CLOSED 2026-04-25] | HANDOFF_2026-04-25 |
| 2.2.3 | Aurora-strict canary suite (parallel literal-token tests, non-gating) | [CLOSED `100a36f`] | HANDOFF_2026-04-26 §3.2 |
| 2.2.4 | Re-run eval after 2.1.1 + 2.1.2 + 2.1.3 are done; expect 5 or 6/6 PASS | **[OPEN, blocked on Don items]** | derived |

### 2.3 ADR-0009 / audit row v2

| # | Item | Status |
|---|---|---|
| 2.3.1 | TurnRequest split (`original_utterance` + `model_input_utterance`) | [CLOSED] |
| 2.3.2 | Audit row schema v2 with `original_utterance`, `retrieval_provenance`, `schema_version`; v1 backward-compat deserialize | [CLOSED] |
| 2.3.3 | TrustDrawer v1-badge + v2-expandable rendering | [CLOSED] |
| 2.3.4 | `audit_seal::canonical_bytes` schema-version branch (preserves v1 hash chain) | [CLOSED] |
| 2.3.5 | E2E test asserting `original_utterance` survives `submit_turn → audit_recent` (`66fb51a`) | [CLOSED] |
| 2.3.6 | Code review #2 e2e replaced with true integration test (when Tauri test scaffolding matures) | **[DEFERRED]** | HANDOFF_2026-04-26 §3.3 |

### 2.4 ADR-0010 / cross-encoder rerank

| # | Item | Status |
|---|---|---|
| 2.4.1 | Empirical bake-off: Option A (recency-weighted combine) vs Option B (bge-reranker-v2-m3) | [CLOSED — Option B Accepted, A Rejected] |
| 2.4.2 | ADR-0010 ratified Proposed → Accepted with empirical proof | [CLOSED `88fdaed`] |
| 2.4.3 | ADR-0011 cross-encoder production wire | **[DEFERRED — see ADR_0011_UNBLOCK_MEMO.md]** |

ADR-0011's prior unblock condition ("wait for real conversation data") was invalidated by the real-corpus bench: lexical-reuse ground truth on real transcripts systematically penalizes good semantic retrieval, making any retrieval-recall benchmark an adversarial yardstick. New unblock condition: **downstream-task quality signal from real Aether usage** (multi-turn correctness, fact recall, `tier:changed` correction-rate). This requires Aether-in-actual-use, not more bench data.

### 2.5 Backfill / Ollama F-series

| # | Item | Status |
|---|---|---|
| 2.5.1 | F1 — retry-on-500 with exponential backoff + recovered_failures counter | [CLOSED] |
| 2.5.2 | F2 — UI failure surface (chip strip + toast branches) | [CLOSED] |
| 2.5.3 | F3 — `OLLAMA_FLASH_ATTENTION=false` workaround verified 65/65 | [CLOSED — workaround confirmed] |
| 2.5.4 | F3 — set the env var permanently | **[OPEN — see 2.1.1]** |
| 2.5.5 | F3 — comment on ollama#13572 with workaround | **[OPEN, optional — see 2.1.4]** |
| 2.5.6 | Async backfill spawn (Phase 4D) — `tokio::spawn_blocking` + cancel | [CLOSED] |

### 2.6 HF embedder + provider hot-swap

| # | Item | Status |
|---|---|---|
| 2.6.1 | Path X persistent Python helper (`tools/hf_embed_helper/embed.py`) | [CLOSED] |
| 2.6.2 | `HfEmbeddingProvider` with `hf:` prefix in `swap_embedding_provider_for_config` | [CLOSED] |
| 2.6.3 | `bge-small-en-v1.5` loadable as Spark default per ADR-0007 D7 | [CLOSED] |
| 2.6.4 | Provider hot-swap (runtime + boot) — UI now matches actual active provider | [CLOSED] |

### 2.7 UX + chrome

| # | Item | Status |
|---|---|---|
| 2.7.1 | Header responsive at 1024px (`deb0c3a`) | [CLOSED] |
| 2.7.2 | Trust drawer focus trap + Escape close (`2c18a5e`) | [CLOSED] |
| 2.7.3 | AuditList chevron hidden when `block_present:false` (`3ca3df1`) | [CLOSED] |
| 2.7.4 | Live UX QA pass with 8 screenshots → NEEDS-POLISH verdict | [CLOSED — 3 findings landed] |
| 2.7.5 | Test coverage gap audit identified 49/52 Tauri commands lacking name-level tests, 14/28 components without test files | **[OPEN — backlog]** | HANDOFF_2026-04-26 §2.8 |

### 2.8 Vision track (companion build)

All commits referenced in CONTINUE_COMPANION_BUILD handoffs are on `dev`. Treat the vision track as **shipped**.

| # | Item | Status |
|---|---|---|
| 2.8.1 | `analyze_frame` vision-capable (Ollama vision provider) `cdf31f8` | [CLOSED] |
| 2.8.2 | Tauri capability + media security model docs `b94a613` | [CLOSED] |
| 2.8.3 | Trust drawer media-only filter `3f3ba95` | [CLOSED] |
| 2.8.4 | llama.cpp HTTP vision adapter `4ae9a13` | [CLOSED] |
| 2.8.5 | Vision provider registry + runtime swap `6257bd5` | [CLOSED] |
| 2.8.6 | Per-panel cue history `3f19678` | [CLOSED] |
| 2.8.7 | Vitest harness + cue/media-turn tests `bd51e65` | [CLOSED] |
| 2.8.8 | Per-provider model discovery in vision dropdown `e50a8f1` | [CLOSED] |
| 2.8.9 | Vision-provider annotation in Trust drawer History `fd400c2` | [CLOSED] |

### 2.9 V*-arc training (this session)

| # | Item | Status |
|---|---|---|
| 2.9.1 | Multi-model discriminator (5 AI sources × 2k + 10k human) | [CLOSED — 79.8% acc] |
| 2.9.2 | V4 prelaunch eval (raw base 6.5%, V2 21.5%, V3-partial 26.5% on v2-style) | [CLOSED] |
| 2.9.3 | V4 LoRA continuation + new corpora | [CLOSED — WildChat 23.5%] |
| 2.9.4 | V5 LoRA more-steps test (plateau hypothesis) | [CLOSED — confirmed plateau] |
| 2.9.5 | V6 multi-turn-format SFT test | [CLOSED — WildChat 28%] |
| 2.9.6 | V3 baseline fills on WildChat + multi-turn (apples-to-apples for V4) | [CLOSED] |
| 2.9.7 | Self-test multi-turn convos (8 turns × 25 seeds) for V4/V5/V6 | [CLOSED] |
| 2.9.8 | V7 candidates documented in V6_RESULTS §5 | **[OPEN — Don's call]** |

### 2.10 Process + governance

| # | Item | Status |
|---|---|---|
| 2.10.1 | Worktree-per-agent recommendation in repo CLAUDE.md | **[OPEN]** | HANDOFF_2026-04-26 §6 |
| 2.10.2 | Adopt `git commit -o <pathspec>` not `git add .` for parallel-agent runs | **[OPEN — convention only, not enforced]** | HANDOFF_2026-04-26 §5 |
| 2.10.3 | Audit corrections: handoffs ≠ ground truth; future audits must diff handoff against `git log` + filesystem | [CLOSED — process note added to STATE_2026-04-28.md] |

### 2.11 Anthropic job loop (project_anthropic_apps_ratelimited.md)

Memory entry says: 23-app loop killed 2026-04-21, 180-day cooldown to ~2026-10-21. **No more Anthropic apps in this window.** Pivot: warm-intro / cold-outreach / portfolio-first only. Listed here only so it's visible in the cross-project context.

---

## 3. What's next

### 3.1 Highest leverage — Don 2-min items

Three items, fifteen minutes total. Each unblocks something downstream:

1. **`OLLAMA_FLASH_ATTENTION=false` permanent env.** Setx in Windows. Without this, F1 retry catches the failures but adds latency; with it, the failures stop happening at the source. Future training pipelines and Aether's normal operation both inherit it.
2. **Commit `tools/evals/fixtures/fridge_open.jpg`.** Any representative still — fridge interior, open door, ideally with food visible. Unblocks `vision_response_quality` scenario, which is otherwise wired and ready.
3. **10th-paraphrase decision.** Add the variant or leave as canary. Both are fine. Just needs a pick.

After all three: re-run `python tools/evals __main__.py --backend ollama` and expect 5 or 6 of 6 PASS.

### 3.2 V7 path — the V*-arc continuation

V6 is the current best. V6_RESULTS.md §5 lists five candidates. The strongest matches for V6's specific evidence are:

**A. Continue multi-turn-format from V6 with 1500–2200 more steps (~3h).**
Hypothesis: V6 was only 1500 steps, and the eval-loss / train-loss gap (0.032) is small enough that more training could continue helping rather than overfit. Cheapest experiment; modest expected payoff (+1-3pp WildChat if anything).

**B. Larger multi-turn windows (8–12 turns) (~3.5h).**
Hypothesis: V6 used 4-8 turn windows. Larger windows might teach more conversational structure. Cost: needs `max_length=1536+`, which forces smaller batch and slower steps.

**C. Higher-rank LoRA (rank 32) trained on multi-turn data from base (~3.5h).**
Hypothesis: combine the format win (V6) with capacity increase. Risk: starts from raw base, loses V4/V6 accumulated weights. Bigger swing but cleaner experiment.

**D. Ship V6 to Aurora — convert training gain into product capability.**
This is the **highest product impact** move. V6 is +12pp WildChat over V3-partial — a real, measurable improvement. Wire V6 into Aurora's persona backbone (currently driven by prompted gemma4:e4b via Ollama; replace with V6 via `transformers`-backed local provider OR convert V6 to GGUF and serve via llama.cpp HTTP adapter). Touches `packages/l6-persona/` and the model router. Likely needs a new ADR.

**E. Train multi-turn discriminator (~1h).**
The current discriminator was trained on single-turn outputs only. Self-test scoring against it is weakly calibrated (treating each generated turn as independent loses the multi-turn-specific signal). Train a new discriminator that takes 2–3 turn windows. Improves the eval signal for whatever V7+ ends up being.

**Recommendation: D and E in parallel sessions.** D ships V6's gain into actual user-visible capability. E strengthens future iteration's measurement. Both fit in single sessions.

If Don wants more iteration before shipping: **A** is the cheapest validation that V6 isn't already saturated.

### 3.3 Process improvements — Tier 3

These are not blocking anything but would compound across future sessions:

- **2.10.1:** Add a "When using parallel agents" section to the repo CLAUDE.md pointing at `superpowers:using-git-worktrees`. Five working-tree contamination incidents on 2026-04-25's autonomous run argue for it.
- **2.10.2:** Convention: never `git add .` in autonomous runs. Always `git add <named paths>` or `git commit -o <pathspec>`. This session followed the convention manually; documenting it makes it inheritable.

### 3.4 Milestone 3 themes (not yet locked)

Milestone 1 closed core subsystems. Milestone 2 closed retrieval-aware turn dispatch. **Milestone 3** is not yet themed. Candidates Don has signaled interest in across past handoffs:

- **"Aurora becomes V6"** — replace prompted gemma4:e4b with V6 LoRA-on-Qwen2.5-3B as Aurora's backbone. Touches L4/L6. Needs ADR-0012-style design + integration test plan. This is §3.2 option D writ as a milestone.
- **"Voice presence"** — Zonos voice cloning is live in QuickGrid TTS sibling project (per memory). Aether's voice-output surface deferred. M3 could ship the voice integration.
- **"Persona pack 2.0"** — formalize the persona schema (`planning/17_persona_pack_schema.md`) into a swappable pack format, with V6 + Aurora's literal expectations as the first complete pack.
- **"Downstream-task quality signal"** — build the in-product eval bus that ADR-0011 needs to unblock. Multi-turn correctness, fact recall on later turns, `tier:changed` correction-rate aggregation. Closes the ADR-0011 deferral.

Don's call. The four are not mutually exclusive; "Aurora becomes V6" + "Downstream-task signal" pair particularly well because shipping V6 generates the data that unblocks ADR-0011.

### 3.5 Deferred (explicit, with trigger condition)

- **ADR-0011 cross-encoder production wire** — trigger: real downstream-task signal source exists.
- **V7 full SFT** — trigger: V7 LoRA experiments (A/B/C above) plateau.
- **7B base model swap** — trigger: 3B-based V7 candidates plateau and/or persona-conditioning needs more capacity than 3B affords.
- **Persona-conditioning V7+ training** — trigger: post-V6 single-blended-register goal achieved or explicitly abandoned.

---

## 4. Recurring lessons (should bias next-session behavior)

### 4.1 Stale-prompt drift is the most common failure mode

Three times this arc, an authoritative-looking handoff document was wrong because it was written before later commits landed:

1. The starting-prompt for this session (Don's paste) referenced HANDOFF_2026-04-25_M2_RUN_2_PARTIAL.md as the source of truth for "what's open." Term 2 caught that the wiring described as pending had landed weeks earlier in `9fad125`.
2. The original SCOPE_AUDIT_2026-04-28.md (mine) reproduced the same staleness because it was written from handoffs, not from `git log` + filesystem. Term 2's CORRECTED audit caught three stale workstreams (B, C, F).
3. The V*-arc starting prompt instructed not to redo completed work — and we caught two near-misses where the agent was about to redo something already shipped.

**Rule (now in repo memory):** Repo beats prompt when status disagrees. Refuse to redo completed work. Verify handoff claims against `git log` and filesystem before acting on them. Future audits should diff handoff against actual repo state before publishing.

### 4.2 Data format > more steps (V*-arc lesson)

V5 confirmed that grinding on the same recipe doesn't help. V6 confirmed that changing how examples are structured (multi-turn windows vs single-turn pairs) unlocked another step of progress without any other change. The most leveraged variable in this arc was data structure, not training time, not LoRA capacity, not learning rate.

Carry this into future iterations: when the loss plateaus, ask first whether the data format is constraining what the model can learn, before reaching for more compute or capacity.

### 4.3 Eval methodology is the primary bottleneck for AI-quality work

The V3-partial → V4 narrative looked like regression on the v2-style discriminator and only revealed itself as a +12pp generalization gain when WildChat held-outs were added. A weak eval makes a real gain invisible. A wrong eval makes any gain unmeasurable.

Carry: invest eval methodology before investing more training compute. The V4 prelaunch eval (multi-source discriminator + held-out WildChat + multi-turn self-test) was more valuable than any single training run.

### 4.4 Sources of truth: git log > planning docs > handoffs > memory

When in doubt about state:
1. `git log --oneline -20` and `git status`
2. Read the source files referenced
3. Then read the planning doc
4. Handoffs are useful narrative but stale fast
5. Memory is a compressed pointer index, not authoritative for current state

---

## 5. File index for the next session (read these in order)

### 5.1 Session-start orientation (15 min cold-read)

1. **This file** — overview of where everything is.
2. file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/STATE_2026-04-28.md — Term 2's verified rolling state.
3. file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V6_RESULTS.md — V*-arc final state and V7 candidates.
4. `git log --oneline -10` — confirm tip `8940c8e` and recent context.
5. `git status` — confirm clean.

### 5.2 Project doctrine (read when context calls for it)

- file:///C:/Users/dbhav/Projects/aether/planning/00_VISION_AND_GUARDRAILS.md
- file:///C:/Users/dbhav/Projects/aether/planning/01_product_doctrine.md
- file:///C:/Users/dbhav/Projects/aether/planning/02_product_family.md
- file:///C:/Users/dbhav/Projects/aether/planning/03_vision_and_thesis.md
- file:///C:/Users/dbhav/Projects/aether/CLAUDE.md (repo rules)

### 5.3 ADRs ratified this milestone cycle

- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0005-retrieval-wiring.md (Accepted; M2 Run 2 implementation)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0006-hardware-tier-model.md (§6 amended)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0007-embeddings-onboarding.md (D7 amended)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0008-tier-detection.md (Accepted)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md (Accepted)
- file:///C:/Users/dbhav/Projects/aether/docs/adr/ADR-0010-rank-function-recency-weighted-combine.md (Accepted, Option B)

### 5.4 Training arc this session

- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V4_PRELAUNCH_EVAL.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V4_RESULTS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V5_RESULTS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V6_RESULTS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/AUTONOMOUS_HANDOFF.md (the prior session's exit point)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/HANDOFF_2026-04-27_OPTIMIZATION_RECS.md (the V4 plan source)

### 5.5 Models on disk

- V6 (current best, multi-turn format): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/
- V4 (prior best, single-turn format): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v4/qwen25_3b_human_lora_v4/final/
- V5 (plateau result): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v5/qwen25_3b_human_lora_v5/final/
- V3-partial (74% trained): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v3/qwen25_3b_human_lora_v3/final_partial_3000/
- V2 (initial finetuned): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v2/qwen25_3b_human_lora/final/
- Multi-discriminator: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v4/discriminator_multi/final/
- V2 discriminator (gemma4-only, deprecated): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v2/discriminator_distilbert/final/

### 5.6 Eval data

- v2-style heldout prompts: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v2/eval_prompts.jsonl
- WildChat heldout prompts: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v4/wildchat_holdout_prompts.jsonl
- Discriminator training corpus: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v4/ (gen_*.jsonl + human_positives.jsonl)
- All `eval_v{2,3,4,5,6}/*.json` files for direct numerical comparison.

### 5.7 Sibling session work (Term 2 outputs, parallel terminal)

- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/SCOPE_AUDIT_2026-04-28.md (original, has stale claims, kept as history)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/SCOPE_AUDIT_2026-04-28_CORRECTED.md (Term 2's verification)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/STATE_2026-04-28.md (Term 2's consolidated state — the single source of truth for "what's open")
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/M2_RUN_2_VERIFIED_CLOSED.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/ADR_0011_UNBLOCK_MEMO.md

### 5.8 Memory entries written this session

- file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/project_aether_v_arc_2026-04-28.md
- MEMORY.md "Aether project state (current)" section updated to reflect V6 best + M2 Run 2 closed.

---

## 6. Wallclock summary across the session

| Phase | Wallclock |
|---|---:|
| Initial orientation + V*-arc starting reads | ~15 min |
| V4 prelaunch eval (raw base test, multi-discriminator build, generations, training, scoring, writeup) | ~3.5 h |
| Scope audit + Term 2 corrections + STATE consolidation | ~1 h |
| V4 corpora pull + restratify + train + eval + self-test + writeup | ~3.5 h |
| V5 training + eval + writeup | ~2.7 h |
| V6 data prep + train + eval + writeup | ~2.5 h |
| Memory updates + this handoff | ~30 min |
| **Total** | **~14 h** |

Active GPU time: ~9 hours (V*-arc training + eval + discriminator training).

---

## 7. Standing instructions for the next agent

1. **Read this file first.** It supersedes prior handoffs as the "where things stand" snapshot.
2. **Verify before acting.** `git log -10`, `git status`, file existence. Don't trust the handoff narrative when it conflicts with the repo.
3. **Don's three Don-only items** (§3.1) unblock visible work — do them first if Don is around. Otherwise document blocking.
4. **For V7**, see V6_RESULTS §5 + this doc §3.2. Default to D + E if nothing else is specified; A is the cheapest single experiment.
5. **For Milestone 3 theming**, see §3.4. Probably wait for Don to pick.
6. **Commit discipline**: named paths only, `git pull --rebase` before push, atomic commits with paragraph-explanation messages.
7. **Memory hygiene**: when project state changes materially, write a memory entry; don't bloat MEMORY.md beyond ~150 chars per line.

---

## 8. Closing observation

This session was an unusually rich autonomous arc — not just three model versions but also a methodological rebuild (multi-discriminator), a scope-audit correction with Term 2, and a handoff staleness analysis that's now baked into the rules. The V*-arc itself is the headline (V6 is +12pp over V3-partial on WildChat, the metric that matters), but the methodology improvements may compound more over the long run. Future sessions should be able to ship faster because the discriminator + eval setup is reusable and the lessons in §4 are documented.

The hardest part of "build an AI assistant indistinguishable from a human friend" continues to be deciding what to measure and trusting the measurement. Everything else is execution.

(end of handoff)
