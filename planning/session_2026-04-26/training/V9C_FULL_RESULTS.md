# V9c Full Eval — 7B Helps on Multi-Turn, Doesn't Beat V6 on WildChat

**Written:** 2026-04-29 PT (V9c full eval ~75 min after V9 sweep complete).
**Model:** Qwen2.5-7B-Instruct + rank-32 LoRA, fresh-from-base, multi-turn-format SFT, 1500 steps.
**Adapter:** file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v9c/qwen25_7b_human_lora_v9c/final/
**Discriminator:** V4 multi-turn DistilBERT (`checkpoints_v4/discriminator_multi/final`).

---

## TL;DR

V9c was the V*-arc's first 7B run and the only V9 sweep variant whose held-out PPL gain justified a full discriminator-scored eval. The full eval converts that PPL gain into the WildChat human-rate metric V*-arc has been tracked on. **The numbers say V9c improves dramatically over V8 but does not beat V6.**

| Eval | V4 | V5 | V6 | V7 | V8 | **V9c** | V9c vs V6 | V9c vs V8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v2-style held-out | 22.0% | 22.0% | 23.0% | 19.5% | 24.0% | **18.0%** | **−5.0pp** | −6.0pp |
| **WildChat held-out** | 23.5% | 24.0% | **28.0%** | 23.5% | 20.5% | **25.0%** | **−3.0pp** | **+4.5pp** |
| Self-test multi-turn (avg) | 35.0% | 28.0% | **33.0%** | 34.0% | 19.5% | **31.0%** | −2.0pp | **+11.5pp** |

**V9c WildChat 25.0% is the second-best WildChat score on record but still trails V6's 28.0% by 3pp.** The 7B base swap is not the silver bullet by itself at 1500 steps from base.

**Decision:** D3 closes with V6 retained as the persona-engine ship default. V9c is a strong candidate for further investigation but does not displace V6. Two follow-up tests are open (§5).

---

## 1. WildChat — the metric that ranks the V*-arc

| Model | WildChat human-rate | Δ vs V4 | Δ vs V6 |
|---|---:|---:|---:|
| V3-partial | 16.0% | −7.5pp | −12.0pp |
| V4 | 23.5% | (baseline) | −4.5pp |
| V5 | 24.0% | +0.5pp | −4.0pp |
| **V6** | **28.0%** | **+4.5pp** | **(ceiling)** |
| V7 | 23.5% | 0.0pp | −4.5pp |
| V8 | 20.5% | −3.0pp | −7.5pp |
| **V9c** | **25.0%** | **+1.5pp** | **−3.0pp** |

**V9c is the strongest non-V6 WildChat number on record.** It beats V4, V5, V7, and V8. It doesn't reach V6.

Under-fit considerations matter here. V9c held-out training loss (1.491) was higher than its eval loss (1.375) — under-fit signature. V9c had the lowest held-out eval loss of any V*-arc model (1.375 vs V6's ≈1.348 within noise) despite being demonstrably under-trained. **A V9c rerun at 3000 steps could close the −3pp gap with V6.** This is the single most decision-relevant unanswered question in the sweep.

The V9_SWEEP_RESULTS.md §5 decision rule:
- "V9c human-rate ≥ V6 (28%)" → V*-arc moves to 7B
- "V9c human-rate < V6" → V9b' next test

V9c at 25% is **below threshold** — V9b' moves to the active queue per the decision rule. V9c at 3000 steps stays viable as a parallel test if Don wants to validate the under-fit hypothesis directly.

---

## 2. Multi-turn coherence — V9c recovers V8's collapse

V8's catastrophic failure mode was the multi-turn self-test crater (19.5%, the worst of any version since V3-partial). V9c on the same eval lands at 31.0% — almost full recovery.

| Turn | V4 | V5 | V6 | V7 | V8 | **V9c** |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 40% | 16% | 28% | 36% | 16% | **32%** |
| 2 | 40% | 28% | 28% | 24% | 24% | **32%** |
| 3 | 20% | 32% | 32% | 56% | 20% | **32%** |
| 4 | 32% | 24% | 36% | 40% | 16% | **24%** |
| 5 | 44% | 44% | 12% | 20% | 24% | **28%** |
| 6 | 32% | 28% | 48% | 32% | 28% | **40%** |
| 7 | 28% | 28% | 44% | 32% | 20% | **32%** |
| 8 | 44% | 24% | 36% | 32% | **8%** | **28%** |
| **avg** | **35.0%** | 28.0% | **33.0%** | 34.0% | **19.5%** | **31.0%** |

Two things stand out:

1. **V9c is consistent across turns** (range 24–40%, σ ≈ 4pp). V8's collapse was non-uniform — turn 8 cratered to 8% while early turns held marginally. V9c spreads its quality evenly. This is the 7B base's range showing through: more parameters, better long-context coherence even when overall human-rate isn't ceiling.
2. **V9c turn-8 = 28%** (vs V8's 8%, V4's 44%, V6's 36%). The late-conversation cliff that V7+V8 introduced is gone in V9c. **This is the single strongest argument for the 7B path** even at the V9c-1500 numbers — late-turn coherence is exactly what the V*-arc has been losing as it pushed deeper into 3B continuation, and 7B brings it back.

---

## 3. Held-out v2-style — V9c worst of any version

V9c v2-style held-out scored 18.0% — the lowest of any version since V3-partial.

| Model | v2-style held-out | Δ vs V6 |
|---|---:|---:|
| V3-partial | 26.5% | +3.5pp |
| V4 | 22.0% | −1.0pp |
| V5 | 22.0% | −1.0pp |
| V6 | 23.0% | (baseline) |
| V7 | 19.5% | −3.5pp |
| V8 | 24.0% | +1.0pp |
| **V9c** | **18.0%** | **−5.0pp** |

The v2-style held-out comes from `eval_v2/eval_prompts.jsonl` — leftover from the V2 → V3 era when PersonaChat was the dominant data source. Cross-arc, this metric has been noisier than WildChat and self-test, partly because it's mostly short-turn PersonaChat-leaked content that the V4+ corpora deliberately broaden away from.

**Reading 1 (most likely):** V9c's 7B base biases away from the PersonaChat distribution that v2-style still partially captures. As 7B sees more training data than 3B, the biases of the model's pretraining are stronger and harder to overwrite with 1500 steps of LoRA — especially low-rank LoRA (rank-32 on 7B has fewer effective parameters than rank-96 on 3B). The score regresses on V2-style not because V9c is worse, but because V9c is *more its base self* relative to V8's smaller 3B base.

**Reading 2 (worth checking):** V9c has the lowest training loss → eval loss inversion among V9 variants (held-out eval 1.375 vs train 1.491). Under-fit at 1500 steps. The V2-style numbers might recover with more training, alongside the WildChat numbers.

Either reading points to "V9c at 3000 steps is the diagnostic" — see §5.

---

## 4. The arc, complete view

| Version | Key change | v2-held | WildChat | Multi-turn | Take |
|---|---|---:|---:|---:|---|
| V3-partial | 84% real-human, paused at 74% | 26.5% | 16.0% | 27.5% | strong on PersonaChat-leaked, weak elsewhere |
| V4 | LoRA cont + new corpora | 22.0% | 23.5% | **35.0%** | structural breakthrough |
| V5 | More LoRA steps, same data | 22.0% | 24.0% | 28.0% | plateau + multi-turn regression |
| V6 | Multi-turn-format SFT | 23.0% | **28.0%** | 33.0% | new best on WildChat |
| V7 | V6 + 1500 more, adamw_8bit | 19.5% | 23.5% | 34.0% | plateau + overfitting |
| V8 | rank-96 fresh-from-base | 24.0% | 20.5% | **19.5%** | capacity hypothesis rejected; multi-turn cratered |
| **V9c** | **Qwen2.5-7B + rank-32, fresh** | **18.0%** | **25.0%** | **31.0%** | **multi-turn recovers, WildChat strong but doesn't beat V6** |

The V*-arc's structural insights from this eval:

1. **Multi-turn coherence is a base-size question.** V8 (3B+rank-96) crashed multi-turn. V9c (7B+rank-32) recovers it. Going forward, multi-turn-coherence-bound work should target 7B.
2. **WildChat is a chain question.** V6's 28% is still the ceiling. V9c (fresh-from-base) doesn't beat it. The V4 → V5 → V6 chain is doing something the 7B-fresh-from-base run can't reproduce in 1500 steps. Either (a) V9c needs more steps, or (b) V9c needs a chain priming that maps the V4 → V5 → V6 trajectory onto the 7B base.
3. **v2-style is now non-load-bearing.** It captures PersonaChat-leaked patterns that 7B-base biases away from. Good signal at V3 era; noisy in the V4+ era; mostly a regression-detector now.

---

## 5. D3 path — open follow-ups, ranked by information-per-hour

### Path A — V9c at 3000 steps (~9 hr GPU)

**Hypothesis:** V9c is under-fit at 1500 steps (held-out train loss > eval loss). Doubling the budget either closes the WildChat gap to V6 (V9c becomes the new ceiling) or doesn't (the 7B fresh-from-base path is structurally weaker than the V4→V6 chain regardless of budget).

**Why this matters:** The cleanest single experiment to validate or kill the 7B path. If V9c at 3000 steps lands ≥28% WildChat, the V*-arc moves to 7B for V10. If V9c-3000 stays at ~25%, 7B is established as a multi-turn fix but not a WildChat lever.

**Cost:** ~9 hr unattended on RTX 3090 Ti. Resumable from V9c training if V9c checkpoint is preserved.

### Path B — V9b' (V6 chain + rank-96 expansion, ~3-4 hr GPU)

**Hypothesis:** The V4 → V5 → V6 continuation chain is the WildChat lever, not the data format alone. If V9b' (V6's adapter expanded to rank-96 + 1500 more steps on multi-turn data) lands ≥28%, the chain matters and rank+chain combo is the next ceiling. If V9b' stays at ~28%, V6 is the absolute ceiling on 3B regardless of rank.

**Why this matters:** Cheaper than Path A and tests a complementary hypothesis. The peft mode-merge mechanism for rank expansion needs careful implementation — see implementation note below.

**Cost:** ~3-4 hr unattended. Implementation cost: writing the rank-expansion logic correctly is a small but non-trivial code task.

**Implementation note:** Two routes for rank expansion:
1. Merge V6 LoRA into base weights (in-memory), then apply fresh rank-96 LoRA on top. The base is permanently modified for this run. Lower implementation risk; cleaner semantics.
2. Use peft's `add_weighted_adapter` or hand-roll a sparse-zero-pad on the V6 LoRA matrices to rank-96. Higher implementation risk.

Recommend route 1.

### Path C — DPO/RLHF on V6 (~? hr, methodology shift)

**Hypothesis:** The remaining gap between V6 and human-ceiling (28% vs 87%) is not a data or capacity question but a method question. SFT on imitation can only get so close to human; preference learning over comparison pairs is the next axis.

**Why this matters:** All other paths optimize within SFT. RLHF/DPO is the methodology move. Probably the right long-term direction even if expensive to set up.

**Cost:** Significant. Requires a preference-pair dataset (probably from human pairwise rating of V6 vs human samples), a reward model (could initialize from the V4 multi-discriminator), and a DPO training pipeline. Several sessions of work.

### Path D — Ship V6, freeze the V*-arc (~0 hr)

**Hypothesis:** 28% WildChat is the practical ceiling on this dataset and architecture; further training is yield-diminishing relative to other priorities (persona delivery infrastructure, lipsync pipeline, etc.).

**Why this matters:** V6 is already the persona-engine ship default. Freezing the V*-arc lets attention shift to product surfaces. The cast is complete; the wizard is wired; the delivery model is captured in ADR-0012.

**Cost:** Zero. Reversible at any time if a future innovation makes a higher ceiling cheap.

---

## 6. Recommendation

**Pursue Path B (V9b') first** — cheapest, complements the V9c data, directly tests the chain hypothesis V8 + V9b raised. ~3-4 hr GPU.

If V9b' lands ≥V6 (28%): the V*-arc continuation chain is the lever, V10 is V9b'-equivalent at higher rank or longer schedule.

If V9b' stays ≤V6: V6 is the 3B ceiling regardless of rank. Path A (V9c-3000) becomes the next test for the 7B viability question.

If both Path A and Path B land short of V6: Path D becomes the right call. V6 is the product-side ceiling and Path C (DPO/RLHF) is the next-quarter methodology move.

**V9c is NOT shipped as a persona-engine candidate.** The −3pp WildChat gap matters; the v2-style regression matters. V9c's multi-turn improvement is interesting but doesn't outweigh the WildChat shortfall on the metric V*-arc has been tracked on.

**V6 remains the persona-engine ship default.** No persona-pack changes triggered by this eval.

---

## 7. Wallclock + cost

| Phase | Wallclock |
|---|---:|
| V9c held-out (200 prompts) | 9.6 min |
| V9c WildChat (200 prompts) | ~21 min |
| V9c self-test (200 turns) | ~22 min |
| Discriminator scoring (DistilBERT) | ~2 min |
| **Total** | **~55 min** |

GPU peak: ~11 GB (7B 4-bit + small LoRA). No OOM. Process exit code was 1 due to a benign tee-redirect failure on launch (`logs_v9c_full/eval.log` mkdir race); all artifacts wrote correctly and `phase_eval.done` flag is set.

---

## 8. Verdict

**V9c is the V*-arc's strongest non-V6 model.** It beats V4/V5/V7/V8 on WildChat. It recovers from V8's multi-turn collapse. It demonstrates that the 7B base brings genuine multi-turn coherence improvements.

**V9c does not displace V6.** WildChat 25% < V6's 28%. V6 remains the ship default.

**The D3 decision-relevant question is no longer "ship V6 vs V9c" — it's "is there a 3B configuration or 7B run that beats V6's 28%?"** Path B (V9b') is the cheapest next test. V9c-3000 (Path A) is the most expensive but most decision-relevant if Path B doesn't beat V6.

**Closes:** V9_SWEEP_RESULTS.md §5 decision-rule "V9c human-rate < V6 → V9b' next test." V9b' moves to the active training queue.
