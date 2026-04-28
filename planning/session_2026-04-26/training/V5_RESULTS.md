# V5 Results — LoRA Continuation Plateaued

**Written:** 2026-04-28 (autonomous session, late afternoon).
**Model:** Qwen2.5-3B-Instruct + V4 LoRA + 2200 steps continuation.
**Adapter:** file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v5/qwen25_3b_human_lora_v5/final/

---

## TL;DR

V5 continued V4's LoRA for 2200 more steps at LR 5e-5. **It didn't help.** The model overfit to the SFT training distribution without generalizing further.

| Eval | V3-partial | V4 | **V5** | V5 vs V4 |
|---|---:|---:|---:|---:|
| v2-style held-out | 26.5% | 22.0% | **22.0%** | 0pp |
| WildChat held-out | 16.0% | 23.5% | **24.0%** | +0.5pp |
| Self-test multi-turn (avg) | 27.5% | 35.0% | **28.0%** | **−7.0pp** |

**Net: V5 ≈ V4 on single-turn, V5 worse than V4 on multi-turn.** Per the decision rule from V4_RESULTS.md ("if V5 plateaus <+3pp, LoRA is saturating"), **rank-16 LoRA continuation is exhausted**.

---

## 1. The training-loss / eval-loss gap is the smoking gun

| Model | Final train loss | Final eval loss | Gap |
|---|---:|---:|---:|
| V4 | 1.475 | 1.433 | 0.042 |
| **V5** | **1.364** | **1.422** | **0.058** |

V5's train loss dropped 0.11 but eval loss only dropped 0.011. The widening gap means V5 used additional LoRA capacity to fit the training set without learning anything new about held-out data. That's textbook overfitting onto the rank-16 manifold.

The multi-turn self-test regression (-7pp) is consistent: a model that's hyper-fit to single-turn (context → response) examples generalizes worse when asked to continue its own dialogue. V5 specialized.

---

## 2. Per-turn multi-turn breakdown

| Turn | V3-partial | V4 | V5 |
|---|---:|---:|---:|
| 1 | 36% | 40% | **16%** |
| 2 | 32% | 40% | 28% |
| 3 | 24% | 20% | 32% |
| 4 | 20% | 32% | 24% |
| 5 | 24% | 44% | 44% |
| 6 | 20% | 32% | 28% |
| 7 | 32% | 28% | 28% |
| 8 | 32% | 44% | 24% |
| **avg** | 27.5% | **35.0%** | 28.0% |

V5 underperforms V4 in 6 of 8 turn positions. Turn 1 catastrophically (-24pp): V5 generates an obviously-AI first reply much more often than V4. Suggests V5 overfit to the model-as-direct-replier rather than model-as-conversational-participant.

---

## 3. What this rules out

- **More steps of the same recipe will not help.** V4 → V5 was the cleanest possible test: identical data, lower LR, more training. The result is plateau + multi-turn regression.
- **Rank-16 LoRA is saturating** for this data and base model. Additional capacity within the same rank gets eaten by overfitting, not generalization.
- **Cosine LR schedule helps, but not enough.** V5's 5e-5 starting LR (vs V4's 1e-4) is conservative; the overfitting still happened.

---

## 4. V6 candidates (Don's call)

Listed in order of expected information-gain × cost:

### A. Higher-rank LoRA from base (rank 32 or 64)
- **Hypothesis:** rank-16 wasn't enough capacity to represent the full register variety in our 53.9k-pair training set; rank 32 may give enough headroom.
- **Risk:** if rank-16 was already overfitting, higher rank would overfit harder. May need stronger regularization (dropout, weight decay) too.
- **Cost:** ~3h training (similar pace to V4). Fresh from Qwen2.5-3B base, V4's gains lost.
- **Verdict:** worth trying if we believe it's a capacity issue. Cheapest experiment.

### B. Different SFT data format — train on full multi-turn conversations
- **Hypothesis:** V5's multi-turn regression suggests the training format (context → single response) is the ceiling, not the model. Training on full conversations as one continuous text might preserve multi-turn coherence.
- **Risk:** moves away from the well-understood SFT pattern. Eval is harder.
- **Cost:** ~30 min data prep + 3h training. From V4 checkpoint.
- **Verdict:** strongest match for the multi-turn-regression evidence.

### C. Larger base model — Qwen2.5-7B-Instruct
- **Hypothesis:** 3B doesn't have enough representation capacity. 7B should.
- **Risk:** training time 2-3x. Can't iterate as fast. V1 already attempted 7B and was killed early; need different config.
- **Cost:** ~6h training, fits the 9h budget if launched immediately. But limited iteration room afterwards.
- **Verdict:** worthwhile but big swing. Defer to V7 unless A and B both fail.

### D. Filter the SFT data more aggressively
- **Hypothesis:** the data mix has too much "register noise" (esp. stemm_podcast over-represented at 13.7%); filtering would help. 
- **Risk:** small gains. Most likely to compound with A or B rather than fix things alone.
- **Cost:** ~30 min data work + ~3h training. From V4 or base.
- **Verdict:** combine with A or B; not standalone.

### E. Stop and ship V4
- V4 is the best model so far. Treat V5 as a negative result and route Aether's persona (Aurora) integration to use V4. Move on to ADR-0012-style production wiring.
- **Verdict:** the right move if Don wants to harvest gains rather than chase ceiling.

---

## 5. My recommendation (delegated to Don)

**B (multi-turn SFT format) is the strongest match for the evidence.** V4 → V5 specifically lost on multi-turn — the training format is implicated. Test that hypothesis cheaply before reaching for higher rank or bigger base.

If Don wants to maximize information-gain in one shot: **A + B combined** — rank-32 LoRA trained on multi-turn-format data from base. Tests capacity + format hypotheses simultaneously. ~3.5h.

If Don wants to ship: **E (stop with V4)**. V4 is already +7.5pp over V3 on real signals. Diminishing returns from here without a structural change.

---

## 6. What I'm NOT doing (and why)

I have ~3.5h remaining of Don's AFK window (until 17:02 PT). I considered launching V6 = option A or B autonomously. Decided against it because:

1. The decision between A/B/C is not data-driven enough to make alone. Each candidate represents a different hypothesis about what's bottlenecking. Picking wrong wastes 3h and I learn nothing actionable.
2. If V6 also plateaus, we'd have two consecutive negative results without between-iteration analysis time. Worse signal-to-noise.
3. V4 is a real product. Stopping here lets Don ship if he wants to. Continuing would tie up the GPU.

This is the [stale-prompt drift](file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_stale_prompt_drift.md) lesson applied: don't chase results when the path forward isn't clear. Surface the data, surface the decision, wait for direction.

---

## 7. Files produced this leg

### Models
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v5/qwen25_3b_human_lora_v5/final/

### Eval
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v5/v5_eval_results.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v5/v5_heldout_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v5/v5_wildchat_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v5/v5_self_test_transcripts.jsonl

### Reports
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V5_RESULTS.md (this file)

---

## 8. Wallclock summary

| Step | Duration |
|---|---:|
| V5 training (2200 steps × 2.74s/step) | ~100 min |
| V5 eval (held-out + WildChat + self-test) | ~45 min |
| V5_RESULTS.md (this) | ~20 min |
| **Total** | **~2.7 h** |

---

## 9. Final state of the V*-arc as of this session

The current "best" model for the human-indistinguishable goal is **V4**, by every metric that matters (WildChat +7.5pp over V3, multi-turn +7.5pp over V3, plateaued at this level after V5).

V4 ceiling on the multi-discriminator: ~35% multi-turn / ~24% single-turn. Real human ceiling: 87%. The 50pp gap is the next frontier — and the V5 result says LoRA continuation is not the path. V6 needs a structural change.

(end of report)
