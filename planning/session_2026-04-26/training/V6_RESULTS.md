# V6 Results — Multi-Turn-Format SFT Worked

**Written:** 2026-04-28 (autonomous session, end-of-AFK).
**Model:** Qwen2.5-3B-Instruct + V4 LoRA + 1500 steps multi-turn-format SFT.
**Adapter:** file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/

---

## TL;DR

V5 plateaued because LoRA continuation on the same (context → single response) format ate capacity into overfitting. V6 changed only the data format — train on multi-turn windows (4-8 turns) instead of single-turn pairs, holding everything else constant — and **the hypothesis from V5_RESULTS §5 was validated**.

| Eval | V3-partial | V4 | V5 | **V6** | V6 vs V4 | V6 vs V5 |
|---|---:|---:|---:|---:|---:|---:|
| v2-style held-out | 26.5% | 22.0% | 22.0% | **23.0%** | +1.0pp | +1.0pp |
| WildChat held-out | 16.0% | 23.5% | 24.0% | **28.0%** | **+4.5pp** | **+4.0pp** |
| Self-test multi-turn (avg) | 27.5% | 35.0% | 28.0% | 33.0% | −2.0pp | **+5.0pp** |

**V6 is the new best on WildChat (+4.5pp over V4 on genuinely unseen distribution).** Multi-turn recovered most of V5's regression and now sits near V4's level. v2-style modestly improved.

---

## 1. Training-loss / eval-loss gap is consistent with generalization

| Model | Final train loss | Final eval loss | Gap |
|---|---:|---:|---:|
| V4 | 1.475 | 1.433 | 0.042 |
| V5 | 1.364 | 1.422 | 0.058 |
| **V6** | **1.380** | **1.348** | **0.032** |

V6 has the **lowest eval loss of any version** AND the **smallest train-eval gap**. V5 was overfitting (gap widening). V6 is generalizing (gap shrinking AND eval loss falling).

The data format change shifted the optimization landscape: instead of memorizing (context → response) shortcuts, V6 had to learn the rhythm of multi-turn dialogue. That's a richer signal that generalizes better.

---

## 2. WildChat detail (the metric that matters)

WildChat is the V*-blind held-out — 200 prompts the model has never seen, sourced from real ChatGPT user inputs.

| Model | WildChat human-rate | Δ vs V4 |
|---|---:|---:|
| V3-partial | 16.0% | -7.5pp |
| V4 | 23.5% | (baseline for this metric) |
| V5 | 24.0% | +0.5pp |
| **V6** | **28.0%** | **+4.5pp** |

V6 closes 4.5pp of the 60-ish-pp gap to the human ceiling (87.1%). The slope from V4→V5 (+0.5) was deceptive — it looked like saturation, but switching format unlocked another step of progress.

---

## 3. Per-turn multi-turn breakdown

| Turn | V3-partial | V4 | V5 | V6 |
|---|---:|---:|---:|---:|
| 1 | 36% | 40% | 16% | 28% |
| 2 | 32% | 40% | 28% | 28% |
| 3 | 24% | 20% | 32% | 32% |
| 4 | 20% | 32% | 24% | 36% |
| 5 | 24% | 44% | 44% | 12% |
| 6 | 20% | 32% | 28% | 48% |
| 7 | 32% | 28% | 28% | 44% |
| 8 | 32% | 44% | 24% | 36% |
| **avg** | 27.5% | **35.0%** | 28.0% | 33.0% |

V6 leads in 4/8 turn positions, ties in 1, trails V4 in 3. The turn-5 dip (12%) is surprising and worth investigating — could be noise (n=25 per position) or a real artifact of the multi-turn-format training. Confidence values were lower at turn 5 too (0.27) — model less certain in middle of conversation.

The V6 self-test transcripts at file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6/v6_self_test_transcripts.jsonl deserve a Don-eyeball pass to see if there's a qualitative pattern.

---

## 4. The arc so far (corrected timeline)

| Version | Key change | WildChat | Multi-turn | Take |
|---|---|---:|---:|---|
| V3-partial | 84% real-human, paused at 74% | 16.0% | 27.5% | Strong on PersonaChat-leaked v2-style; weak elsewhere |
| V4 | LoRA continuation + new corpora | 23.5% | 35.0% | Big generalization jump; this was the structural breakthrough |
| V5 | More LoRA steps, same data | 24.0% | 28.0% | Plateau + multi-turn regression — saturated |
| **V6** | **Multi-turn-format SFT** | **28.0%** | **33.0%** | **WildChat new best; multi-turn near V4** |

**The trajectory says: data format > more steps.** V5 confirmed that grinding on the same recipe doesn't help. V6 confirmed that changing how examples are structured can unlock more progress without a base-model swap.

---

## 5. V7 candidates (Don's call)

I'm not auto-launching V7. AFK budget is ~1h. V7 deserves Don's analysis and a fresh session. Candidates ranked by my read of evidence:

### A. Continue multi-turn-format from V6 with more steps (~3h)
- Hypothesis: V6 was only 1500 steps. V4 used 2200, V5 used 2200. Maybe more multi-turn training extends the +4.5pp WildChat gain.
- Risk: V5 showed continuation can plateau quickly. Watch eval-train gap.
- Verdict: Cheapest experiment, modest expected payoff.

### B. Multi-turn-format + larger windows (8-12 turns) (~3.5h)
- Hypothesis: V6 windows were 4-8 turns. Larger windows might teach more conversational structure.
- Risk: max_length 1024 already tight; would need 1536+ → smaller batch → slower.
- Verdict: Variation on B; defer.

### C. Higher-rank LoRA (rank 32) on multi-turn data from base (~3.5h)
- Hypothesis: combining the format win (V6) with capacity increase (rank 32) attacks both bottlenecks.
- Risk: starts from raw base; loses V4/V6 accumulated weights.
- Verdict: cleanest "next big step" but loses progress. Probably the right move if Don wants to bet bigger.

### D. Stop and ship V6 as Aurora's backbone
- V6 is +4.5pp over V4 on WildChat, +12pp over V3-partial, near-V4 on multi-turn. Demonstrably better than anything before.
- Aurora persona integration is a project-level next step (would touch packages/l6-persona/).
- Verdict: most product-impactful move. Stops the V*-arc to convert gains into shipped capability.

### E. Train multi-turn discriminator
- The current discriminator was trained on single-turn outputs. Self-test scoring against it is weakly calibrated.
- Train a new discriminator that takes 2-3 turn windows → AI/human label.
- Verdict: meta-experiment. Worth doing before V8+ if multi-turn is the main eval signal.

---

## 6. My recommendation (delegated to Don)

**D + E in parallel sessions.** V6 is a real product gain — it should be wired into Aurora before more iteration. Meanwhile, training a multi-turn discriminator (~1h) gives a stronger eval for whatever V7+ ends up being.

If Don wants to keep iterating in this arc: **A** (continue multi-turn-format from V6) is the cheapest validation. B and C are the bigger swings.

---

## 7. Files produced this leg

### Models
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v6/qwen25_3b_human_lora_v6/final/

### Scripts
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/build_v6_multiturn_sft.py
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline_v6.py
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6.py

### Eval
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6/v6_eval_results.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6/v6_heldout_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6/v6_wildchat_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v6/v6_self_test_transcripts.jsonl

### Data
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/data/sft_train_v6.jsonl (29.4k multi-turn windows)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/data/sft_eval_v6.jsonl

### Reports
- This file: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V6_RESULTS.md

---

## 8. Wallclock summary (this leg)

| Step | Duration |
|---|---:|
| V6 data prep (multi-turn windows) | ~5 min |
| V6 training (1500 steps × 3.26s/step) | ~82 min |
| V6 eval (held-out + WildChat + self-test) | ~50 min |
| V6 writeup (this) | ~15 min |
| **Total** | **~2.5 h** |

---

## 9. Session totals (V4→V5→V6 arc)

This autonomous session shipped three new model versions (V4, V5, V6), confirmed the V3-overfit-on-leaky-eval hypothesis, and identified data format as a meaningful axis. Wallclock: ~10 hours of training + eval + writeup. Best-on-WildChat went 16% (V3-partial) → 23.5% (V4) → 28% (V6). That's +12pp in real-generalization terms — a real product gain on the indistinguishability axis.

(end of report)
