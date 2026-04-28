# Autonomous Session Handoff — Human-Indistinguishable Conversation Training

**Written:** 2026-04-27
**Branch:** `dev`. Tip: `e4ee91f`. All work pushed. Working tree clean.
**Authority for next session:** Don's call. This handoff is structured so a fresh Claude session can pick up cold without losing the thread.

---

## 0. The big-picture goal

### 0.1 What Aether is

Aether (private codename: Isabelle) is Don's personal AI assistant —
local-first, persistent, presence-aware. Architecture lives at
`packages/l1-*` through `packages/l6-persona/` with Memory V2,
retrieval-aware turn dispatch, vision+voice subsystems, and a
hand-authored persona ("Aurora") currently driven by **prompted**
gemma4:e4b via Ollama.

The five core subsystems shipped and rot-guarded as of 2026-04-23:
Vision, Voice, Presence, Memory V2, Quality-Eval V1. Milestone 1
closed. Milestone 2 ("retrieval-aware + user-facing") open.

### 0.2 End goal of the *project*

A private, local, persistent AI assistant that genuinely feels like
a person:
- Continuity of memory across sessions
- Presence-aware responsiveness (knows when Don is Away, Background, etc.)
- Voice + vision integration
- A conversational style indistinguishable from natural human speech
  — so that interaction feels effortless, not "talking to a chatbot"

Privacy-first means everything runs locally on Don's hardware (RTX
3090 Ti, 24 GB VRAM). No cloud APIs in the production path.

### 0.3 End goal of *this training initiative* (the "v1→v2→v3→v4" arc)

Replace or augment the **prompted-Aurora** approach with a
**fine-tuned model** whose conversational outputs are statistically
indistinguishable from real human dialog turns.

Concretely:
- Train an open-weight LLM (currently Qwen2.5-3B-Instruct via QLoRA)
  on diverse natural human conversation.
- Validate via a robust discriminator-based eval that the trained
  model's outputs cannot be reliably distinguished from human ones.
- Eventually: drop in as the Aurora backbone, replacing gemma4:e4b
  prompted with a model that's natively conversational without AI-tells.

The "indistinguishable from human" target is the persona-quality
axis. The retrieval, memory, and presence axes are handled by the
broader Aether architecture.

---

## 1. Where this session arc started and where it landed

### 1.1 Starting state (2026-04-26 morning)

Don asked: *"Can you spend the next 12 hours finding, collecting,
training, conversations, without stopping to get realistic results?"*

Acknowledged constraints:
- Single agent, can't literally run 12h autonomously, but can kick
  off long-running pipelines and check in periodically.
- Quality bar: "indistinguishable from a real human."
- Hardware: RTX 3090 Ti, 24 GB VRAM.

### 1.2 What we built across the arc

**v1 (12h budget, killed early):**
- Qwen2.5-7B-Instruct + QLoRA, max_length 2048
- 5 corpora: PersonaChat (extractor failed), BlendedSkill (6.8k),
  Topical-Chat (10.8k), Empathetic Dialogues (51k, NC eval-only),
  SODA (1.5M → 80k cap).
- 219k SFT pairs, training started but ETA ballooned to 27h due
  to eval cycle on full 25k eval set burning 3.5h/cycle.
- Killed at step 2,500 with loss healthy at 0.69.
- Lesson: eval set must be tiny + eval_steps must be sparse; 7B
  was overkill for chat-naturalness when sample exposure matters
  more than parameter count.

**v2 (8h budget, completed):**
- Qwen2.5-3B-Instruct (3x faster than 7B) + QLoRA + sdpa attention
- 8 corpora (added OASST2 + UltraChat + DailyDialog)
- 80k stratified SFT pairs, mix: 32% real-human / 58% SODA / 10% UltraChat
- 5,000 steps in 9h 14min, final loss 1.06, eval loss 1.59
- **Discriminator score: 100% classified-as-human** (vs 76.5% gemma4
  baseline). Delta +23.5pp.
- Lesson: 100% is suspect. Discriminator was trained on gemma4-vs-human
  only, so it learned gemma4-tells (emoji, "Haha,", italics-hedge),
  not "AI-vs-human" generally.

**v3 (8h budget, paused at 74%):**
- Same base model + config as v2
- 9 corpora (added Cornell Movie Dialogs, Reddit Casual Conversation,
  YouTube podcast transcripts, STEMM podcast transcripts)
- 64.9k stratified SFT pairs, mix: **84% real-human** / 6% SODA /
  10% curated. UltraChat dropped, SODA capped 10k.
- New batch reconstructors: Cornell movies (group by movieID,
  segment to 2-speaker chunks), YouTube podcasts (chunk transcripts
  into pseudo-turns), STEMM podcasts (split monologues into
  sentence chunks). Reddit casual extractor parses `@username:`
  format.
- Paused at step 3,000/4,058 (74% trained, 5h 45min wallclock burned).
- **V3-partial discriminator score: 100% — IDENTICAL to v2.**
- Sample outputs visibly different register from v2 (more follow-up
  questions, Cornell-movie spaced punctuation), but discriminator
  can't measure it.

### 1.3 The diagnostic finding

The v2 discriminator only learned **"is gemma4 vs is not gemma4."**
Both v2 and v3-partial outputs lack gemma4-tells, so both score 100%
even though they're trained on very different distributions (58%
synthetic vs 84% real-human). The discriminator is the eval bottleneck.

This is captured in detail in `HANDOFF_2026-04-27_OPTIMIZATION_RECS.md`.

---

## 2. Current artifact inventory

### 2.1 Models / adapters

| Path | What | Status |
|---|---|---|
| `checkpoints_v2/qwen25_3b_human_lora/final/` | V2 final LoRA adapter (Qwen2.5-3B base) | usable |
| `checkpoints_v2/discriminator_distilbert/final/` | V2 discriminator (gemma4 vs human, 99.83% accuracy on its own task) | usable but NARROW |
| `checkpoints_v3/qwen25_3b_human_lora_v3/checkpoint-3000/` | V3 paused at 74% training | resumable |
| `checkpoints_v3/qwen25_3b_human_lora_v3/final_partial_3000/` | Copy of checkpoint-3000 named for eval reuse | usable as-is |
| `checkpoints_v2/qwen25_7b_human_lora/checkpoint-2000/` | V1 partial reference (7B, killed early) | reference only |

### 2.2 Datasets (cached on disk)

`data/` contains:
- v2-era: `personachat`, `blended_skill`, `topical_chat`, `soda`,
  `oasst2`, `ultrachat`, `daily_dialog`, `empathetic`, `wildchat`
- v3-added: `cornell_movie`, `cornell_movie_v2`, `reddit_casual`,
  `yt_podcast`, `stemm_podcast`
- Normalized: `normalized_train_v3.jsonl` (377k convos),
  `normalized_eval_v3.jsonl`, `sft_train_v3.jsonl` (currently
  stratified to 64.9k for v3 8h budget — re-stratify for v4),
  `sft_eval_v3.jsonl`

V2-era normalized files (`*_v2.jsonl`, `sft_*_v2.jsonl`) preserved
for the v2 results to remain reproducible.

### 2.3 Eval results

| File | Content |
|---|---|
| `eval_v2/scores.json` | V2 baseline 76.5% / V2 finetuned 100% / delta +23.5pp |
| `eval_v2/baseline_outputs.jsonl` | 200 gemma4:e4b continuations |
| `eval_v2/finetuned_outputs.jsonl` | 200 V2 fine-tuned continuations |
| `eval_v2/eval_prompts.jsonl` | 200 eval prompts (reused for v3-partial too) |
| `eval_v3/scores_partial_3000.json` | V3-partial 100% — same as v2 |
| `eval_v3/v3_partial_3000_outputs.jsonl` | 200 V3-partial continuations |

### 2.4 Pipeline scripts

| File | What |
|---|---|
| `train_pipeline.py` | v1 driver (Qwen2.5-7B path, partially working) |
| `train_pipeline_v2.py` | v2 driver (Qwen2.5-3B, 8 corpora, eval inline) |
| `train_pipeline_v3.py` | v3 driver (9 corpora, batch reconstructors for Cornell/YT/STEMM) |
| `eval_v3_partial.py` | One-off script that scored v3-partial vs v2 discriminator |

### 2.5 Documentation

| File | What |
|---|---|
| `OPTIMIZATION_NOTES.md` | v2 design rationale (3B vs 7B, eval set sizing, etc.) |
| `V2_RESULTS.md` | Full v2 writeup with sample outputs |
| `HANDOFF_2026-04-27_OPTIMIZATION_RECS.md` | Detailed v4 recommendations (this is the action plan) |
| `AUTONOMOUS_HANDOFF.md` | This file — the orientation doc |

---

## 3. Lessons learned (cross-arc)

### 3.1 About training
- **Sample exposure > parameter count for chat naturalness.**
  Going 7B → 3B was a strict speedup with no observable quality
  cost on this task.
- **Eval set must be ≤500 and eval_steps ≥2500.** v1's 25k eval
  every 500 steps was the single biggest budget killer.
- **gemma4:e4b is a reasoning model.** Always pass `think:false`
  in API calls or it spends all `num_predict` budget on the
  internal `thinking` field and returns empty content. v2 phase 6
  was generating 1 negative every ~45s before this fix → 0.87s after.
- **Step time on 3090 Ti for QLoRA Qwen2.5-3B + max_length 768
  + bnb 4-bit + grad_checkpointing is ~7s/step.** Less than 7B
  (5s wait what?) — actually 7B was bottlenecked elsewhere; 3B at
  these settings is the practical floor without flash-attn-2 (which
  doesn't reliably build on Windows).
- **VRAM contention from stray Ollama processes will degrade step
  time 2-3x.** Always kill ollama before training; v3 second half
  slowed 7s→18s/step because ollama auto-respawned mid-run.

### 3.2 About data
- **Most of the obvious "conversation" datasets are synthetic
  (SODA, UltraChat) or human-AI (WildChat, LMSYS).** Real
  human-human at scale is harder to find; v3's mix had to combine
  Cornell movies + Reddit + podcasts + a handful of curated chat
  corpora to reach 84% real-human.
- **DailyDialog and EmpatheticDialogues are CC BY-NC.** Eval-only
  for any shippable model. SODA, OASST2, BlendedSkill, TopicalChat,
  Cornell, Reddit (per the alpaca-lora reupload), STEMM/YT podcasts
  are shippable.
- **Source caps matter for stratification.** stemm_podcast generated
  408k convos from 25k rows because each row is a long monologue
  that the chunker split into 6-sentence pseudo-conversations. Need
  to cap aggressively or it dominates.
- **Speaker name stripping matters for SODA.** Without it, the model
  learns to emit "Veda: ..." prefixes during generation.

### 3.3 About eval methodology
- **A discriminator trained on ONE AI distribution learns to detect
  THAT distribution's tells, not "AI in general."** Both v2 and
  v3-partial scored 100% against the gemma4-trained discriminator
  even though their training data and output styles differ
  substantially.
- **Eval prompts must be held-out** from the training distribution.
  V2 eval prompts came from the same normalized eval pool as
  training data, which lets the fine-tune leak info into the test.
- **A multi-model discriminator (gemma4 + qwen3 + base Qwen + V2
  fine-tuned + V3 fine-tuned, all vs human) would force the
  classifier to learn "varied human prose" vs "AI patterns
  generally," not just one model's quirks.**

### 3.4 About session orchestration
- **Setx Windows env vars don't propagate to running shells.**
  PYTHONUTF8=1 must be `export`-ed in the bash shell *or* prefixed
  on each python call. Set permanently in HKCU\Environment via
  `setx PYTHONUTF8 1` for new sessions only.
- **Background bash tasks survive until session-end.** They are
  real Windows processes; killing the Claude Code session doesn't
  reliably kill them. Use `taskkill /F /PID` to be sure.
- **Atomic commits per phase** make resumption safe. The v1/v2/v3
  drivers use on-disk done markers (`logs_*/phase_*.done`) so
  re-running the script skips completed phases.

---

## 4. Recommended next session plan (the v4 arc)

Detailed in `HANDOFF_2026-04-27_OPTIMIZATION_RECS.md`. Summary:

| Order | Item | Time | Priority |
|---|---|---|---|
| 1 | Sanity: eval raw Qwen2.5-3B-Instruct (no LoRA) vs v2 discriminator | 5 min | DEFER (but cheap) |
| 2 | Build multi-model discriminator (5 AI sources + V2 + V3 outputs) | 1.5 h | **HIGH** |
| 3 | Re-eval V2 + V3-partial + raw base against new discriminator | 30 min | **HIGH** |
| 4 | Pull 3 more naturalistic corpora (OpenSubtitles, screenplays, re-mined Lex) | 1.5 h | MED |
| 5 | Rebalance stratification (stemm_podcast over-represented in v3) | 30 min | MED |
| 6 | Pre-tokenize cache + ollama watchdog | 1 h | LOW |
| 7 | Train V4 with new mix | 6 h | core |
| 8 | Eval V4 against new discriminator + WildChat held-outs | 1 h | core |

**Total: ~12 h sequential.** Steps 1-3 produce immediately useful
results (a real comparison of v2 vs v3 vs base) without committing
to a full training run. Steps 7-8 are the new training session
itself.

---

## 5. Open questions blocking V4 launch

1. **Goal definition.** Fool an unaware reader on short snippets,
   or genuinely match the human distribution to a discerning judge
   over multi-turn conversation? The first is largely achieved
   already; the second requires §4.1 + §4.2 of the recs minimum.
2. **Single blended register, or persona-conditioned switching?**
   Training on 9 corpora produces a blended register. If you want
   selectable "casual chitchat" vs "Cornell-movie-dramatic" vs
   "podcast-intellectual" modes, we need persona conditioning
   during training (system prompt as feature).
3. **Continue from V3 LoRA or full SFT from base?** Full SFT lets
   the model genuinely shift its output distribution, but is slower
   and more invasive. LoRA is faster but caps how far we can move
   from the Qwen2.5-3B-Instruct prior.
4. **Should the trained model eventually replace gemma4:e4b in
   Aether's production path?** That's the broader project goal but
   has implications for ADR-0003 (the gemma4 + bge-m3 baseline).
   Likely deferred until V4 results validate the approach.

---

## 6. How a fresh session resumes

### 6.1 Quick orientation (5 min)

```bash
cd C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training

# 1. Read this file (AUTONOMOUS_HANDOFF.md)
# 2. Read HANDOFF_2026-04-27_OPTIMIZATION_RECS.md for the v4 plan
# 3. Confirm tip
git log --oneline -3   # should include e4ee91f or later
git status             # should be clean
```

### 6.2 Quick state checks

```bash
# What pipelines have run, what's saved?
ls logs_v2/*.done
ls logs_v3/*.done
ls checkpoints_v2/qwen25_3b_human_lora/final/   # v2 final
ls checkpoints_v3/qwen25_3b_human_lora_v3/      # v3 paused

# Last eval scores
cat eval_v2/scores.json
cat eval_v3/scores_partial_3000.json
```

### 6.3 Resuming v3 (if you change your mind)

```bash
cd C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training
PYTHONUTF8=1 python train_pipeline_v3.py
# Auto-resumes from checkpoint-3000, finishes phases 5/6/7/8.
# Expected ~5h to full completion.
```

### 6.4 Starting V4 (after Don answers §5 open questions)

Build:
1. `train_pipeline_v4.py` — copy of v3 with multi-model discriminator
   in phase 6, WildChat held-out prompts in phase 7, added corpora,
   rebalanced stratification.
2. Run sanity check first (raw base eval).
3. Build new discriminator.
4. Re-eval all existing models against it.
5. Then launch the 6h V4 training.

### 6.5 Memory paths (for the project-intelligence agent)

If the next session uses Don's auto-memory system:

- Session memory root:
  `C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/`
- Aether project state:
  `project_aether_state_2026-04-23.md` (now stale — this handoff is the
  newer state)
- Repo CLAUDE.md: `C:/Users/dbhav/Projects/aether/CLAUDE.md`

---

## 7. Things deliberately NOT done (and why)

- **Did not try unsloth.** Tried once; pulled torch back to CPU,
  broke the stack. Reverted. Speed gains came from smaller base +
  attention impl + batch tuning instead.
- **Did not request LMSYS-Chat-1M access.** Gated dataset; would
  need Don to accept terms on HF. Skipped for this arc; consider
  for v5+.
- **Did not implement persona-conditioned training.** Would let the
  model produce different registers on demand. Deferred to v5+
  pending Don's call on §5.2.
- **Did not finish v3 to completion.** V3-partial scoring identical
  to v2 confirmed the discriminator is the eval bottleneck. Burning
  3-4 more hours to hit step 4,058 wouldn't change the conclusion.
- **Did not build a human blind-judge UI.** The strongest possible
  eval would be Don himself (or a small panel) blind-rating
  outputs. Deferred until automated eval is rigorous enough to
  meaningfully rank candidates.

---

## 8. Reference paths (everything that exists)

### Models
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v2/qwen25_3b_human_lora/final/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v2/discriminator_distilbert/final/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v3/qwen25_3b_human_lora_v3/checkpoint-3000/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v3/qwen25_3b_human_lora_v3/final_partial_3000/

### Eval results
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v2/scores.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v2/baseline_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v2/finetuned_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3/scores_partial_3000.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3/v3_partial_3000_outputs.jsonl

### Documentation
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/OPTIMIZATION_NOTES.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V2_RESULTS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/HANDOFF_2026-04-27_OPTIMIZATION_RECS.md
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/AUTONOMOUS_HANDOFF.md (this file)

### Pipelines
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline.py (v1)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline_v2.py (v2 — completed)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline_v3.py (v3 — paused)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v3_partial.py (one-off eval)

---

## 9. Final summary in one paragraph

Across this arc, we ran three iterations of fine-tuning Qwen2.5
models on conversational data, escalating from 5 corpora (v1) to 8
(v2) to 9 (v3) and shifting the data mix from 32% real-human (v2)
to 84% real-human (v3, with new sources: Cornell movies, Reddit,
YouTube + STEMM podcasts). V2 completed; V3 paused at 74%. Both
score 100% against our discriminator, which we discovered is too
narrow (only learned gemma4-vs-human, not "AI-vs-human" generally).
The next session's most valuable work is rebuilding the
discriminator with multi-model AI negatives plus held-out eval
prompts from WildChat — that produces a meaningful eval signal,
which finishing V3 wouldn't. Detailed v4 plan in
`HANDOFF_2026-04-27_OPTIMIZATION_RECS.md`. Three open questions
for Don to answer before V4 launch: goal definition (fool-unaware
vs match-distribution), register handling (single vs persona-
conditioned), and training mode (LoRA continuation vs full SFT).

(end of handoff)
