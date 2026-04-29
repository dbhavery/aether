# V9 Sweep Results — 7B Base Wins on Held-Out, Pending Full Discriminator Eval

**Written:** 2026-04-29 PT (V9 sweep completed 14:46 PT after ~14.5 hr).
**Sweep:** 3 ablations covering D3 paths (rank-ceiling, continuation, base-swap).
**Adapters:**
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v9a/qwen25_3b_human_lora_v9a/final/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v9b/qwen25_3b_human_lora_v9b/final/
- file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/checkpoints_v9c/qwen25_7b_human_lora_v9c/final/

---

## TL;DR

V9 sweep tested three orthogonal levers from the V8 archive:

| Variant | Lever | Held-out loss | Held-out PPL | Train-eval gap | Verdict |
|---|---|---:|---:|---:|---|
| V8 (baseline) | rank-96 fresh-from-base, 1500 steps | 1.445 | 4.243 | −0.091 (under-fit) | archived negative |
| **V9a** | rank-128 fresh-from-base, same recipe | **1.410** | **4.097** | −0.121 (more under-fit) | marginal +0.035, capacity alone ≠ progress |
| **V9b** | V8 + 1500 more steps (continuation) | **1.431** | **4.182** | +0.045 (proper fit) | marginal +0.014 vs V8, continuation alone ≠ progress |
| **V9c** | **Qwen2.5-7B base, rank-32, same recipe** | **1.375** | **3.954** | −0.116 (under-fit) | **+0.070 vs V8, +0.062 vs V9b — base size is the real lever** |

**Held-out PPL ranking:** V9c (3.95) > V9b (4.18) ≈ V9a (4.10) > V8 (4.24).

**The story:** Within 3B, neither rank (V9a) nor continuation (V9b) closes the V8 → V6 gap at this step budget. The 7B base swap (V9c) shows a real held-out improvement of comparable magnitude to V6's WildChat jump — and does so under-fit, suggesting a longer V9c run would widen the lead further.

**Important caveat:** This sweep used `eval_v9_quick.py`, which captures held-out PPL + WildChat *generations* but **NOT** the multi-turn discriminator scoring that produced V4–V8's "human-rate" numbers. The cross-version table in V8_RESULTS.md §4 measures a different signal than the table above. To confirm V9c > V6 on the WildChat-human-rate metric, V9c needs a full V8-style eval pass.

**Verdict:** V9c is the only V9 variant that justifies a follow-up. Run it through the full discriminator eval before declaring it the new ceiling. V9a and V9b are archived as negative results — V8's lesson holds.

---

## 1. Held-out loss + PPL (the only quantitative signal this sweep produced)

| Version | Held-out eval loss | Held-out PPL | Δ vs V8 |
|---|---:|---:|---:|
| V8 | 1.445 | 4.243 | (baseline) |
| V9a | 1.410 | 4.097 | −0.035 |
| V9b | 1.431 | 4.182 | −0.014 |
| V9c | **1.375** | **3.954** | **−0.070** |

V9c's −0.070 held-out-loss improvement over V8 is roughly twice the V9a delta and five times the V9b delta. For reference, V6 → V8 was a +0.097 regression on held-out loss. V9c reverses about three-quarters of the V6 → V8 regression on this single signal.

**N for held-out:** 200 examples per variant, sampled from `sft_eval_v6.jsonl`. PPL = `exp(eval_loss)`.

---

## 2. Train-eval gap analysis (under-fit vs proper-fit)

| Version | Final train loss | Final eval loss | Gap | Reads as |
|---|---:|---:|---:|---|
| V6 | 1.380 | 1.348 | +0.032 | proper fit |
| V7 | 1.273 | 1.355 | +0.082 | overfitting |
| V8 | 1.536 | 1.445 | **−0.091** | under-fit |
| V9a | 1.532 | 1.410 | **−0.121** | **more** under-fit (more capacity, same budget) |
| V9b | 1.386 | 1.431 | +0.045 | proper fit (continuation closed the gap) |
| V9c | 1.491 | 1.375 | **−0.116** | under-fit (7B has more parameters to fill) |

V9b is the only V9 variant with a positive train-eval gap. This is what continuation does — it puts the model on a better-trained starting curve where 1500 more steps is enough to fit. V9b confirms continuation matters; V9b's modest held-out gain (vs V8) shows that continuation *alone* isn't the V6-jump lever — something specific to the V4 → V5 → V6 chain mattered beyond "starting from a warm adapter."

V9a and V9c are both under-fit. V9a's deeper inversion (−0.121) confirms V8's pattern: pushing rank up without budget bump deepens under-training. V9c's under-fit reads differently — the eval loss is the *best* of any variant despite the gap, suggesting 7B has so much head-room that even an under-trained run beats a proper-fit 3B run. **A V9c rerun at 3000 steps would likely widen the lead.**

---

## 3. WildChat generation samples — qualitative read

The eval pass generated 200 WildChat continuations per variant. These were NOT scored by the discriminator (that pass needs to be added back for an apples-to-apples WildChat human-rate number). Sampled the first 5 of each below.

### V9a (rank-128 fresh-from-base, 3B)

```
[0] "I am sorry, I don't know what 'Frito Patatoe chips' is. Please try searching on an internet search engine or providing more context for me to help you with."
[1] "King Creon's son, Haemon, killed himself after Antigone's death."
[2] "Given a medieval city with a population of 100k, the number of soldiers defending the walls and the citadel will depend on several factors..."
[3] "A magical city is surrounded by beautiful and tall magical trees..."
[4] "The first thing I wanted to do was get a job."
```

Mixed register. Sample [0] reads pure assistant. Samples [1]–[3] read as factual brief answers. Sample [4] reads as a fragment continuation.

### V9b (V8-continuation +1500 steps, 3B)

```
[0] "I will look into that for you."
[1] "In the Greek tragedy Antigone, King Creon's fate is that he becomes aware of his error and repents for his decision to execute Antigone..."
[2] "In this case, we'll assume that the total number of soldiers guarding the city is equal to half of the total number of inhabitants..."
[3] "Here's a prompt for StableDiffusion: A magical world in the anime style..."
[4] "I don't understand what you want me to generate. Can you clarify?"
```

**Worse register than V9a in this sample.** Heavy assistant-meta language ("I will look into", "Here's a prompt for...", "Can you clarify?"). V9b *deepens* V8's assistant-register failure mode — exactly the V8 → V7 pattern from V8_RESULTS.md §2 where continuation amplifies the dominant register rather than diversifying it.

### V9c (7B base swap, rank-32, 1500 steps)

```
[0] "I'm sorry, I am not able to provide you with nutrition information for those food items."
[1] "King Creon's son, Haemon, killed himself out of grief after Antigone died by hanging herself."
[2] "The population of your city is 100,000 people. A good portion of them are probably men of military age..."
[3] '"Create a prompt for stable diffusion that has a magical world anime style with a beautiful city surrounded by magical trees and it looks like it is all covered in poison."'
[4] "What?"
```

Most range of the three. Sample [0] still assistant. Sample [1] is more naturally phrased than V9a/V9b. Sample [2] is opinionated and conversational ("A good portion of them are probably..."). Sample [4] — `"What?"` — is the kind of short conversational reply real humans give that V4/V5/V6 sometimes produced. The 7B base appears to surface more of the human-text register when the dataset doesn't dominate it.

This is impressionistic. The discriminator pass would score it. The held-out PPL backs it up.

---

## 4. The arc, with V9 (held-out PPL only — see §1 caveat)

| Version | Key change | Held-out PPL | Take |
|---|---|---:|---|
| V4 | LoRA continuation + new corpora | n/a (no PPL run) | structural breakthrough |
| V5 | More LoRA steps, same data | n/a | plateau |
| V6 | Multi-turn-format SFT | n/a | new best on WildChat (per V8_RESULTS) |
| V7 | V6 + 1500 more, adamw_8bit | n/a | plateau confirmed; overfitting |
| V8 | rank-96 fresh-from-base | 4.243 | capacity hypothesis rejected |
| **V9a** | rank-128 fresh-from-base | **4.097** | rank alone — marginal |
| **V9b** | V8 + 1500 more steps | **4.182** | continuation alone — marginal |
| **V9c** | **Qwen2.5-7B + rank-32** | **3.954** | **base swap — real signal** |

PPL is not the metric V4–V8 were judged on (those used WildChat human-rate via the multi-turn discriminator). Cross-row PPL → human-rate mappings are not 1:1. This row reads "V9c held-out PPL beats every other 3B run by a margin worth chasing, but doesn't yet prove V9c > V6 on the human-rate metric."

---

## 5. D3 decision (RLHF / 7B base swap / ship V6 / continue V*-arc)

The V9 sweep was designed to inform the D3 path call. With these results:

### Eliminated paths

- **"Ship V6 and stop training"** — V9c shows enough held-out signal to justify another round.
- **"Continue V*-arc on 3B with rank/budget tweaks"** — V9a + V9b confirm the 3B ceiling is real. Neither lever alone (rank up, more steps from V8) closes the gap.

### Promising paths

- **"Swap to 7B base for V10"** (the V9c lead). Held-out PPL says this is the strongest signal in the sweep. Confirmation needs:
  1. V9c re-eval with the V8-style multi-turn discriminator pipeline (~2 hr) — produces apples-to-apples WildChat human-rate.
  2. If V9c human-rate ≥ V6 (28%), the path is real. Run V9c at 3000 steps (~10 hr) and check if the under-fit signal converts to a meaningful additional gain.
- **"V9b architecture + V6 starting point"** — the unanswered question: does the V*-arc continuation chain transfer to higher rank? V9b started from V8 (fresh-from-base), not from V6 (the warm adapter). A V9b' run starting from V6 → expanded to rank-96 (mode-merge or continued training with rank lift) is the cleanest test. ~3 hr.

### Open paths (not tested, still on the table)

- **RLHF / DPO** — the method lever. Not yet on the roadmap; would require a preference-pair dataset and a reward model. Probably deferred until a 7B SFT ceiling is established.
- **Different data mix** — V6's data format was the V4 → V6 lever. A new format (e.g. longer windows, different filtering) is untouched.

### Recommendation

1. **Re-eval V9c with the V8-style discriminator pipeline** to convert held-out PPL into a WildChat human-rate number directly comparable to V6's 28%. This is the single highest-information-per-hour next step. If it lands ≥ V6, the V*-arc moves to 7B for V10.

2. **If V9c human-rate < V6** (held-out PPL gain doesn't translate to WildChat human-rate), 7B is held-out-friendly but not human-rate-friendly — V*-arc stays on 3B and the D3 next move is V9b' (rank-96 from V6 chain).

3. **V9a is archived.** Capacity-from-fresh-base is conclusively the wrong axis at this step budget. Don't rerun.

4. **V9b is archived but informative.** It confirmed "continuation closes the train-eval gap" and "continuation alone is not the V6 jump." Its negative result is useful for the roadmap, not for shipping.

---

## 6. Wallclock + cost

| Phase | Wallclock | Notes |
|---|---:|---|
| V9 sweep waiting for V8 | ~4.2 hr (00:17 PT trigger) | polling V8 phase_eval.done |
| V9a train | 5.4 hr | rank-128, 3B, batch-1+ga-16 |
| V9a eval | 0.5 hr | held-out + WildChat gen |
| V9b train | 3.2 hr | V8 continuation, batch-2+ga-8 |
| V9b eval | 0.4 hr | |
| V9c train | 4.6 hr | 7B, rank-32, batch-1+ga-16, max_len 768 |
| V9c eval | 0.4 hr | |
| **Total under-load** | **~14.5 hr** | well inside Don's 21 hr budget |

GPU was RTX 3090 Ti (24 GB). No OOM, no orchestrator failures. Sweep finished cleanly. `sweep_complete.done` flag set.

---

## 7. Verdict

**V9a archived (negative).** Rank-from-fresh-base alone is not the lever even at rank-128.

**V9b archived (negative-but-informative).** V8 continuation closes the train-eval gap but doesn't recover V6's signal — confirms the V6 jump came from the V4 → V5 → V6 chain specifically, not from continuation in general.

**V9c is the only candidate worth chasing.** Held-out PPL improvement is real. Pending full discriminator eval, V9c is the proposed V10 architecture. Decision-gate is "does V9c WildChat human-rate ≥ V6's 28%?" — answer in ~2 hr of eval compute.

**V6 remains the persona-engine ship default until V9c is confirmed.** No persona-pack changes triggered by this sweep.
