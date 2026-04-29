# V7 Results — LoRA Continuation Plateaus on WildChat

**Written:** 2026-04-28 (autonomous session, while V8+V9 still running).
**Model:** Qwen2.5-3B-Instruct + V6 LoRA + 1500 steps multi-turn-format SFT continuation, adamw_8bit optimizer.
**Adapter:** file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v7/qwen25_3b_human_lora_v7/final/

---

## TL;DR

V7 was option A from V6_RESULTS.md §5 — "continue multi-turn-format from V6 with more steps" — answered. **It doesn't extend V6's gain. WildChat regressed −4.5pp from V6 (back to V4-tied), held-out v2-style regressed −3.5pp from V6, and only self-test multi-turn nudged up +1pp.** Adding adamw_8bit didn't change the dynamics meaningfully; the plateau V5 warned about returned.

| Eval | V4 | V5 | V6 | **V7** | V7 vs V6 |
|---|---:|---:|---:|---:|---:|
| v2-style held-out | 22.0% | 22.0% | 23.0% | **19.5%** | **−3.5pp** |
| WildChat held-out | 23.5% | 24.0% | 28.0% | **23.5%** | **−4.5pp** |
| Self-test multi-turn (avg) | 35.0% | 28.0% | 33.0% | **34.0%** | +1.0pp |

**V6 is still the best on WildChat.** V7 is now archived as evidence that grinding more multi-turn-format steps from V6's adapter is not the next axis.

---

## 1. Train-eval gap widened (overfitting recurred)

| Model | Final train loss | Final eval loss | Gap |
|---|---:|---:|---:|
| V4 | 1.475 | 1.433 | 0.042 |
| V5 | 1.364 | 1.422 | 0.058 |
| V6 | 1.380 | 1.348 | **0.032** |
| **V7** | **1.273** | 1.355 | **0.082** |

V7 has the lowest train loss of any version AND the largest train-eval gap. That's the textbook overfitting signature: the model is memorizing more without generalizing better. Eval loss actually crept up from V6 (1.348 → 1.355) despite the train loss falling 0.107.

V6 was the sweet spot in this arc. V7 walked past it.

---

## 2. WildChat detail (the metric that matters)

| Model | WildChat human-rate | Δ vs V4 | Δ vs V6 |
|---|---:|---:|---:|
| V3-partial | 16.0% | −7.5pp | −12pp |
| V4 | 23.5% | (baseline) | −4.5pp |
| V5 | 24.0% | +0.5pp | −4.0pp |
| V6 | **28.0%** | **+4.5pp** | (baseline) |
| **V7** | 23.5% | 0.0pp | **−4.5pp** |

V7 erases the V6→ gain entirely. The +4.5pp WildChat jump V6 booked from changing data format is gone after one more LoRA continuation pass. Two readings:

1. **Capacity-bound:** the V6 adapter is at the end of what rank-64 can express on this dataset. More steps can only memorize.
2. **Data-bound:** 29.4k multi-turn windows already saturated; the model has seen all the structure there is.

Either way, the next axis is NOT "more multi-turn-format on rank-64 from V6."

---

## 3. Per-turn multi-turn breakdown

| Turn | V4 | V5 | V6 | **V7** |
|---|---:|---:|---:|---:|
| 1 | 40% | 16% | 28% | 36% |
| 2 | 40% | 28% | 28% | 24% |
| 3 | 20% | 32% | 32% | **56%** |
| 4 | 32% | 24% | 36% | 40% |
| 5 | 44% | 44% | 12% | 20% |
| 6 | 32% | 28% | 48% | 32% |
| 7 | 28% | 28% | 44% | 32% |
| 8 | 44% | 24% | 36% | 32% |
| **avg** | **35.0%** | 28.0% | 33.0% | **34.0%** |

V7 has one striking outlier — turn 3 at 56% (highest single-turn-position score across all four versions). With n=25 per position this is well within sampling noise, but worth eyeballing in the transcripts to see whether turn 3 has a structural advantage.

The turn-5 dip persists across V6 (12%) and V7 (20%). That looks like a genuine pattern — something about mid-conversation context size or the format of windows being rendered makes the model's turn 5 generation systematically less convincing. Worth instrumenting in V8+ if multi-turn remains the eval signal.

---

## 4. The arc so far (updated)

| Version | Key change | WildChat | Multi-turn | Take |
|---|---|---:|---:|---|
| V3-partial | 84% real-human, paused at 74% | 16.0% | 27.5% | Strong on PersonaChat-leaked v2; weak elsewhere |
| V4 | LoRA continuation + new corpora | 23.5% | 35.0% | Structural breakthrough |
| V5 | More LoRA steps, same data | 24.0% | 28.0% | Plateau + multi-turn regression |
| V6 | Multi-turn-format SFT | **28.0%** | 33.0% | New best on WildChat |
| **V7** | **V6 + 1500 more steps, adamw_8bit** | **23.5%** | 34.0% | **Plateau confirmed; V6 was the ceiling for this rank+data** |

V5 told us "more steps on same data ≠ more progress." V7 reaffirmed the lesson with a stricter test: even multi-turn-format data with a different optimizer can't push rank-64 LoRA past V6.

The lever has to change. Three structural axes remain:
- **Capacity** (higher LoRA rank — V8 tests this at rank-96)
- **Base** (different base model — V9c tests Qwen2.5-7B)
- **Method** (RLHF / DPO instead of SFT — not yet on the roadmap)

---

## 5. What V8 and V9 are testing

V8 launched while V7 eval was running (concurrent design). V9 sweep launched after that.

### V8 — fresh-from-base rank-96 LoRA (~3.5h train, in progress)

- Tests whether rank-96 unlocks more capacity than rank-64.
- Starts from raw base, not V6's adapter — clean comparison.
- If V8 ≥ V6 on WildChat: capacity was the bottleneck; rank-96+ becomes the recipe.
- If V8 < V6 on WildChat: V6's adapter was a privileged starting point; rank alone isn't enough.

### V9 sweep — three variants in series (queued behind V8)

- **V9a:** rank-128 capacity ceiling test (push rank past V8 to find diminishing returns)
- **V9b:** V8 + 1500 step continuation (does V8's recipe extend?)
- **V9c:** Qwen2.5-7B base swap with V6's data recipe (does base size dominate rank?)

The V9 results will give Don a 3-axis grid: rank (V6 64 vs V8 96 vs V9a 128), continuation-on-V8 (V9b), and base-swap (V9c). Together with V7 they fully bracket the structural choices.

---

## 6. Recommendation (delegated to Don)

**V6 is still the recommended ship.** V7 doesn't change that — if anything it strengthens the case that V6 is at a local optimum for the rank-64+multi-turn-format recipe.

**Don't ship V7** in any persona pack or eval comparison except as a negative result. The +1pp self-test gain is within noise, and the WildChat regression is real.

**Wait for V8+V9 before re-deciding the V*-arc trajectory.** If V8 or V9c outperforms V6, the next ship candidate updates. If neither does, V6 is the plateau and the project should pivot to either RLHF or persona-conditioning experiments instead of more SFT iteration.

---

## 7. Files produced this leg

### Models
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v7/qwen25_3b_human_lora_v7/final/

### Scripts
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/train_pipeline_v7.py
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v7.py

### Eval
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v7/v7_eval_results.json
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v7/v7_heldout_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v7/v7_wildchat_outputs.jsonl
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/eval_v7/v7_self_test_transcripts.jsonl

### Logs
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/v7_train.log (1500 steps, ~100 min)
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/logs_v7/v7_eval.log (held-out + WildChat + self-test)

### Reports
- This file: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V7_RESULTS.md
- Companion read: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V7_CONVERSATIONS.md (sample transcripts)

---

## 8. Wallclock summary (V7 leg)

| Step | Duration |
|---|---:|
| V7 training (1500 steps × 4.0s/step, adamw_8bit) | ~100 min |
| V7 eval — held-out (200 prompts) | ~18 min |
| V7 eval — WildChat (200 prompts) | ~31 min |
| V7 eval — self-test (25 seeds × 8 turns) | ~12 min |
| V7 writeup (this) | ~15 min |
| **Total** | **~3 h** |

V8 launched concurrent with V7 eval; V9 sweep queued behind V8. The
3.5h V7 wallclock did not delay the V8+V9 sequence.

(end of report)
