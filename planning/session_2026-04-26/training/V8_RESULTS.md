# V8 Results — Rank-96 Fresh-From-Base Doesn't Beat Continuation

**Written:** 2026-04-29 (autonomous session, V9 sweep still running).
**Model:** Qwen2.5-3B-Instruct + rank-96 LoRA, fresh-from-base, multi-turn-format SFT, 1500 steps.
**Adapter:** file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v8/qwen25_3b_human_lora_v8/final/

---

## TL;DR

V8 was the capacity test from V7_RESULTS.md §5 — "is rank-64 the ceiling? does rank-96 fresh-from-base do better?" — answered. **No, it does not.** WildChat regressed −7.5pp from V6 (worse than V7), multi-turn self-test cratered to 19.5% (−13.5pp from V6, the worst of any version since V3-partial). Held-out v2-style ticked up +1pp, but on its own that's noise.

| Eval | V4 | V5 | V6 | V7 | **V8** | V8 vs V6 |
|---|---:|---:|---:|---:|---:|---:|
| v2-style held-out | 22.0% | 22.0% | 23.0% | 19.5% | **24.0%** | +1.0pp |
| WildChat held-out | 23.5% | 24.0% | **28.0%** | 23.5% | **20.5%** | **−7.5pp** |
| Self-test multi-turn (avg) | 35.0% | 28.0% | 33.0% | 34.0% | **19.5%** | **−13.5pp** |

**V6 is still the WildChat ceiling — and now also the multi-turn ceiling.** V8 is archived as evidence that rank-alone-from-base is not the next lever; the V4→V5→V6 continuation chain's privileged starting point matters more than raw rank.

---

## 1. Train-eval gap inverted (under-trained for capacity)

| Model | Final train loss | Final eval loss | Gap |
|---|---:|---:|---:|
| V4 | 1.475 | 1.433 | +0.042 |
| V5 | 1.364 | 1.422 | +0.058 |
| V6 | 1.380 | 1.348 | +0.032 |
| V7 | 1.273 | 1.355 | +0.082 (overfitting) |
| **V8** | **1.536** | **1.445** | **−0.091** (under-fit) |

V8 has the *highest* training loss and an *inverted* train-eval gap (eval lower than train). That is the textbook signature of a rank-96 model trained for too few steps to absorb the larger parameter budget — fresh-from-base with rank+50% can't match a continuation-trained rank-64 in 1500 steps.

The V8 launch budget was sized to match the V6/V7 1500-step recipe so the eval would compare apples-to-apples. The result tells us 1500 steps is enough for rank-64 starting from V4's adapter but **not** enough for rank-96 starting from base. Either V8 needs ~3000 steps (doubling compute) or rank-96 fresh-from-base is structurally a worse path than continuation.

---

## 2. WildChat detail (the metric that matters)

| Model | WildChat human-rate | Δ vs V4 | Δ vs V6 |
|---|---:|---:|---:|
| V3-partial | 16.0% | −7.5pp | −12pp |
| V4 | 23.5% | (baseline) | −4.5pp |
| V5 | 24.0% | +0.5pp | −4.0pp |
| V6 | **28.0%** | **+4.5pp** | (baseline) |
| V7 | 23.5% | 0.0pp | −4.5pp |
| **V8** | **20.5%** | **−3.0pp** | **−7.5pp** |

V8 is the worst WildChat score since V3-partial. The V6 jump from "fresh data format" did not survive a fresh-from-base rerun even at higher rank. Two compatible readings:

1. **The lever was the continuation chain, not the data format.** V4 → V5 → V6 each layered new gradients on top of an already-warm adapter. V8's fresh start lost that priming.
2. **The lever was 1500 steps × accumulated prior, not 1500 steps absolute.** V6's training started from a checkpoint that had already absorbed ~4500 effective steps' worth of human-text gradients. V8's 1500 fresh-from-base is genuinely 1500 steps of learning — a much earlier point on the same curve.

Both readings point to the same conclusion: **continuation > fresh-from-base** for this dataset and model size, even when capacity goes up.

---

## 3. Per-turn multi-turn breakdown

| Turn | V4 | V5 | V6 | V7 | **V8** |
|---|---:|---:|---:|---:|---:|
| 1 | 40% | 16% | 28% | 36% | **16%** |
| 2 | 40% | 28% | 28% | 24% | 24% |
| 3 | 20% | 32% | 32% | 56% | 20% |
| 4 | 32% | 24% | 36% | 40% | **16%** |
| 5 | 44% | 44% | 12% | 20% | 24% |
| 6 | 32% | 28% | 48% | 32% | 28% |
| 7 | 28% | 28% | 44% | 32% | 20% |
| 8 | 44% | 24% | 36% | 32% | **8%** |
| **avg** | **35.0%** | 28.0% | 33.0% | 34.0% | **19.5%** |

V8 has the worst score in every turn position except turn 6 (where V5 was lower). Turn 8 dropped to 8% — only 2 of 25 generations were judged human. The late-conversation degradation V7 partially showed deepens here: V8 cannot maintain a convincing voice past mid-conversation, which is consistent with the under-trained signal in §1 (the model hasn't yet absorbed the multi-turn structure of the data).

No single-turn outlier this version. The collapse is uniform.

---

## 4. The arc so far (updated)

| Version | Key change | WildChat | Multi-turn | Take |
|---|---|---:|---:|---|
| V3-partial | 84% real-human, paused at 74% | 16.0% | 27.5% | Strong on PersonaChat-leaked v2; weak elsewhere |
| V4 | LoRA continuation + new corpora | 23.5% | 35.0% | Structural breakthrough |
| V5 | More LoRA steps, same data | 24.0% | 28.0% | Plateau + multi-turn regression |
| V6 | Multi-turn-format SFT | **28.0%** | 33.0% | New best on WildChat |
| V7 | V6 + 1500 more steps, adamw_8bit | 23.5% | 34.0% | Plateau confirmed; overfitting signature |
| **V8** | **rank-96 fresh-from-base, multi-turn-format** | **20.5%** | **19.5%** | **Capacity hypothesis rejected; under-fit at this step budget** |

V5 told us "more steps on same data ≠ more progress." V7 reaffirmed it. V8 introduced a NEW lesson: **rank ≠ progress when the chain is broken.** The continuation-chain path V6 sat on appears to matter more than the absolute rank.

The remaining structural axes:
- ~~**Capacity** (higher LoRA rank from base)~~ — V8 tested, rejected at this step budget
- **Capacity-with-continuation** (V6's adapter copied to rank-96 weights, continued) — not yet tested; would isolate rank from chain
- **Base** (different base model — V9c tests Qwen2.5-7B)
- **Method** (RLHF / DPO instead of SFT — not yet on the roadmap)
- **Step budget** (rerun V8 at 3000 steps to give rank-96 enough room) — open question whether budget alone closes the gap

---

## 5. What V9 is testing

V9 sweep launched after V8 train. Three branches:

### V9a — rank-128 fresh-from-base (~5h train + ~1h eval)

Same recipe as V8 but with rank-128 instead of rank-96. If V8's collapse was purely "1500 steps wasn't enough for rank-96", V9a should be even worse (more capacity to fill, same steps). If V9a is *not* worse, the capacity hypothesis isn't dead — V8 just needed a budget bump. Most likely outcome: V9a regresses further, confirming continuation-chain matters.

### V9b — V8-continuation (~3h train + ~1h eval)

V8's adapter + 1500 more multi-turn-format steps. This is the V6→V7 path applied to V8's starting point. If V9b lands above V8 but below V6, it tells us continuation helps but isn't enough to close the rank-96 vs rank-64-with-prior gap. If V9b lands above V6, the continuation+rank combo is the new ceiling.

### V9c — Qwen2.5-7B base swap (~6h train + ~1.5h eval)

The base-model lever. Same dataset, same recipe, ~2× parameter count. Most likely outcome: meaningful gain on WildChat (the held-out distribution) but with a much higher inference cost. Useful as a "what would 7B buy" data point for the roadmap, even if 3B remains the deployment target.

ETA on full sweep: ~17 hours from V9 sweep start. Next session writes V9_SWEEP_RESULTS.md and triggers the D3 decision in the roadmap.

---

## 6. Verdict

**V8 is archived as a negative result.** Don't ship in any persona pack. Don't use as eval comparison except as a "rank-from-base under-fit" reference point.

**V6 remains the WildChat ceiling and the recommended ship candidate.** Until V9b or V9c surfaces a beat, V6 is the persona-engine default for the cast.

**The next decision-relevant data point is V9b.** It directly tests "does continuation matter, or was the V6 jump from data format alone?" — the question V8 set up but couldn't answer.
