# Handoff — 2026-04-27 → Next Optimized Training Session

**Written:** 2026-04-27 at session pause.
**Branch:** `dev`. Tip: `30faa33` (will be updated on commit).
**Status:** v3 paused at checkpoint-3000 (74% trained, 5h 45min wallclock burned). v3-partial evaluated against v2 discriminator. Eval methodology bottleneck identified.

---

## TL;DR

The "indistinguishable from human" goal can't be measured with the
current eval. Both v2 (SODA-heavy, 100% trained) and v3-partial
(real-human-heavy, 74% trained) score **100% classified-as-human**
against the v2 discriminator. The discriminator only learned
gemma4-specific tells; anything non-gemma4 → 100%. Without a stronger
eval, more training tells us nothing new.

**Recommendation: rebuild the eval methodology before doing more
training.** Specific plan in §4 below.

---

## 1. Where things stand

### 1.1 V2 (complete)
- 80k stratified samples, 32% real-human / 58% SODA / 10% UltraChat
- Qwen2.5-3B-Instruct + QLoRA, 5,000 steps, 9h 14min wallclock
- Final train loss 1.057, eval loss 1.595, eval token accuracy 65.3%
- Final adapter: `checkpoints_v2/qwen25_3b_human_lora/final/`
- **Discriminator score: 100% human-rate (vs 76.5% gemma4 baseline)**

### 1.2 V3 (paused at checkpoint-3000)
- 64.9k stratified samples, **84% real-human** / 6% SODA / 10% curated
- New corpora vs v2: Cornell Movie Dialogs, Reddit Casual, YouTube
  Podcasts, STEMM Podcasts. UltraChat dropped. SODA capped 10k.
- Qwen2.5-3B-Instruct + QLoRA, paused at step 3,000/4,058 (74%)
- Wallclock: 5h 45min before pause (step time degraded 7s→18s due
  to ollama VRAM contention in last hour)
- Adapter: `checkpoints_v3/qwen25_3b_human_lora_v3/checkpoint-3000/`
  also copied to `final_partial_3000/` for eval reuse
- **Discriminator score: 100% human-rate (same as v2)**

### 1.3 V2 discriminator
- DistilBERT trained on 5,400 samples (real human turns from
  normalized eval vs gemma4:e4b outputs with `think:false`)
- Eval accuracy 99.83%
- **Critical limitation:** trained on ONE AI distribution (gemma4).
  Anything not-gemma4 falls into the "human" class by default.

### 1.4 Sample output comparison (same eval prompts)

| Prompt context | V2 (SODA-heavy) | V3-partial (real-human) |
|---|---|---|
| ...about cooking | "Yeah, I'm a good cook. I was always told by my mom..." | "No, I'm not really good. I'm still working on it." |
| ...about acting hopes | "i have 2 children" | "i have three kids . i have a son and two daughters ." |
| ...about snakes | "I'm sure they would.  What kind of snakes do you have?" | "That would be a lot of fun. Do you have a snake?" |
| ...about cars | "that is nice. i have an old cadillac" | "I love Hondas, what is your favorite part of the car?" |

V3 outputs ask more follow-up questions and show some Cornell-movie
spaced-punctuation patterns ("i have three kids . i have a son..."),
but both are still strongly PersonaChat-register. Neither has the
register variety humans actually use across speech / writing /
internet / dramatic registers.

---

## 2. Why the current eval can't measure "indistinguishable from human"

The discriminator was trained on:
- **Class 1 (human):** sampled real turns from PersonaChat /
  BlendedSkill / TopicalChat / SODA / OASST2 / DailyDialog / etc.
  These ARE all texts written by humans (or written to imitate
  human conversation in the SODA case).
- **Class 0 (AI):** outputs from gemma4:e4b given the same prompt
  pool, with `think:false`.

What the discriminator actually learned: **a binary "is gemma4 / is
not gemma4"** classifier, not "is AI / is human." Specifically:
- gemma4 outputs heavy emoji usage (😂)
- gemma4 starts replies with "Haha,"
- gemma4 hedges with em-dashes and italics ("I'm not a *great* cook")
- gemma4 explains its reasoning ("makes you feel kinda sluggish when…")

When V2 or V3 fine-tuned Qwen2.5-3B outputs lack those gemma4-tells,
the discriminator routes them to the "human" class. Even if a
discerning human reader would call those outputs "obviously a chatbot
trained on PersonaChat," the discriminator can't see that.

**The eval's max sensitivity is "is this gemma4-tells-y or not."**
That's a useful but very narrow signal.

---

## 3. What we DO know (and don't)

### Confirmed by current eval
- ✓ Both V2 and V3-partial successfully *avoid gemma4-tells*. The
  fine-tune is doing real work to shed the gemma4 distribution.
- ✓ V3 with 84% real-human bias produces noticeably different
  *register* from V2's SODA-heavy training (more questions, different
  punctuation patterns).

### NOT yet measurable
- ✗ Whether V2 or V3 outputs are "indistinguishable from human" to a
  discerning judge.
- ✗ Which of V2 or V3 is actually closer to natural human speech.
- ✗ Whether the corpus-mix differences (Cornell movies, podcasts,
  Reddit) translated to actual register variety in outputs.

---

## 4. Recommended optimizations for the next session

### 4.1 [HIGH] Rebuild the discriminator with multi-model AI negatives

Train DistilBERT (or a stronger classifier) to distinguish human from
**multiple** AI distributions, not just gemma4. Concretely:

**Negative classes (AI):**
- gemma4:e4b outputs (~3000)
- qwen3:8b outputs (~3000)
- Qwen2.5-3B-Instruct base (no LoRA) outputs (~3000)
- A free-tier open-weight Llama-3.x-8B-Instruct outputs if available
  (~3000)
- V2 fine-tuned outputs (~3000) — this is critical: trains the
  classifier to see PersonaChat-register patterns as "AI"
- V3-partial outputs (~3000)

**Positive classes (human):**
- Real turns from each of the 8 v3 corpora (sampled, ~12000 total)

Total: ~30k samples, ~10 min training. Discriminator should now be
forced to learn "is this naturally varied human prose" rather than
"does this have gemma4 quirks."

When V4 fine-tune is evaluated against this stronger discriminator,
the score will be meaningful: low if the model still has any AI-tells,
high only if the outputs genuinely match human distribution.

### 4.2 [HIGH] Held-out eval prompts the model has never seen

Current eval prompts are sampled from the same normalized eval pool
that overlaps the training distribution. This lets the fine-tune
"learn the test." Fix:

- Source eval prompts from **WildChat** (already on disk, eval-only).
  Real users typing real prompts to ChatGPT — distribution the
  model has never seen.
- Sample 200 prompts where the user-side context is 3-6 turns and
  ends with a clear next-turn opening.
- Optionally also sample from Switchboard or AMI-style transcripts
  (real recorded human speech turns) for spoken-register testing.

### 4.3 [MEDIUM] Add three more naturalistic data sources

Already discovered, ready to download in v4:

| Source | Volume | Why |
|---|---|---|
| `ghomasHudson/muld_OpenSubtitles` (English `input` field) | Massive | Real movie/TV subtitles, scripted spoken |
| `alankent/ordinary_screenplays` | 10s of episodes with structured `dialog: [{speaker, lines, mood}]` | Real screenplay dialog with speaker labels |
| Re-mined Lex Fridman parquet (already on disk, 800k Whisper segments) | Lots | Aggregate consecutive segments into 6-10 turn conversations using long-pause heuristic for speaker change detection |

Plus the v3 sources already cached: Cornell, Reddit, YouTube podcasts,
STEMM podcasts.

### 4.4 [MEDIUM] Better stratification — multi-register balanced

V3's 84% real-human is good but stemm_podcast over-represents one
register (STEM scientific podcast monologue). Better balance:

- Cornell movie (dramatic):    20%
- DailyDialog (everyday):       15%
- Lex Fridman re-mined (intellectual spoken): 15%
- OpenSubtitles (TV/film):     12%
- Reddit casual (internet):    10%
- BlendedSkill (chitchat):     10%
- TopicalChat (curated):        8%
- OASST2 (human-curated):       5%
- ordinary_screenplays:         5%

Total ~50-65k samples for 6-8h budget.

### 4.5 [LOW] Speed improvements

- Pre-tokenize the train pool (cache as parquet of input_ids) so
  re-runs skip ~3min of tokenization overhead.
- Watchdog to kill stray Ollama processes before training (v3 was
  slowed by ollama spinning back up mid-run).
- Consider attn implementation `flash_attention_2` if installable on
  Windows (likely not without WSL; sdpa is the working path).

### 4.6 [DEFER] Multi-epoch on smaller higher-quality set

Instead of 1 epoch over 65k diverse samples, try 2 epochs over a
top-quality 25-30k subset (filter by length variance, exclude very
short or very long turns, exclude high-repetition examples). May give
better fit per minute of GPU. Defer until 4.1-4.3 are in place.

### 4.7 [DEFER] Compare against the unfine-tuned base

Before fine-tuning v4, run the discriminator-eval on **raw Qwen2.5-3B-Instruct** (no LoRA at all). If raw Qwen2.5-3B already scores 100%
against the v2 discriminator, then fine-tuning isn't even helping
on this metric — the gemma4-tells absence comes for free from the
base model. This is a 5-minute test that validates whether
fine-tuning is doing useful work at all.

---

## 5. Suggested launch sequence for the next session

1. **(5 min)** Run §4.7 — eval raw Qwen2.5-3B-Instruct against v2
   discriminator. If 100%: confirms fine-tuning didn't help by this
   metric. If <100%: gives us a real baseline.
2. **(1.5 h)** Build §4.1 multi-model discriminator. Generate AI
   negatives in parallel from gemma4 + qwen3:8b + Qwen2.5-3B-base +
   v2-finetuned + v3-partial. Train DistilBERT.
3. **(30 min)** Re-eval V2, V3-partial, and Qwen2.5-3B-base against
   the new discriminator. Get rigorous numbers.
4. **(1.5 h)** Add §4.3 data: pull OpenSubtitles, ordinary_screenplays,
   re-mine Lex Fridman. Normalize.
5. **(30 min)** Build §4.4 stratified mix.
6. **(6 h)** Launch V4 training session.
7. **(1 h)** Eval V4 against the new multi-model discriminator + the
   §4.2 WildChat held-out prompts.

Total: ~11 h sequential, but steps 1-3 give immediately meaningful
results without committing to a full training run.

---

## 6. Files for the next session

### Preserved
- `checkpoints_v2/qwen25_3b_human_lora/final/` — V2 final adapter
- `checkpoints_v2/discriminator_distilbert/final/` — V2 discriminator
- `checkpoints_v3/qwen25_3b_human_lora_v3/checkpoint-3000/` — V3 paused
- `checkpoints_v3/qwen25_3b_human_lora_v3/final_partial_3000/` — V3 partial copy for eval
- `eval_v2/scores.json`, `eval_v2/baseline_outputs.jsonl`,
  `eval_v2/finetuned_outputs.jsonl` — v2 results
- `eval_v3/scores_partial_3000.json`, `eval_v3/v3_partial_3000_outputs.jsonl` — v3 partial results
- `data/normalized_*_v3.jsonl` and `data/sft_*_v3.jsonl` — v3 corpus

### To create for V4
- `train_pipeline_v4.py` — copy of v3 with §4.1 multi-model
  discriminator, §4.2 WildChat eval prompts, §4.3 added corpora,
  §4.4 rebalanced stratification, §4.5 pre-tokenized cache.
- `data/cornell_movie_v3` (rename or extend), `data/opensubtitles`,
  `data/ordinary_screenplays`, `data/lex_fridman_chunked`
- `checkpoints_v4/`, `eval_v4/`, `logs_v4/`

---

## 7. Open questions for Don

1. **Is the goal "fine-tuned model that fools an unaware reader"
   or "fine-tuned model that genuinely matches human distribution"?**
   The first is achievable with the current setup. The second
   requires §4.1+§4.2 minimum.
2. **Is "human" a single distribution, or do you want register
   selectability?** A model trained on 9 corpora produces a blended
   register. If you want it to switch between "casual chitchat" and
   "Cornell-movie-dramatic" and "podcast-intellectual" on demand,
   we need persona conditioning during training.
3. **Should V4 train Qwen2.5-3B from scratch (no LoRA, full SFT) or
   continue from V3's LoRA?** Full SFT is more invasive and slower
   but lets the model genuinely shift its distribution. LoRA is
   faster but caps how much we can move the model.

Awaiting Don's call on these before V4 launch.

---

## 8. Quick reference

```bash
# Resume V3 to completion (if you change your mind):
cd C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training
PYTHONUTF8=1 python train_pipeline_v3.py
# Auto-resumes from checkpoint-3000.

# Eval anything against v2 discriminator:
PYTHONUTF8=1 python eval_v3_partial.py
# (Edit LORA_DIR at the top to point at any other adapter.)

# Status:
PYTHONUTF8=1 python train_pipeline_v3.py --status
```

(end of handoff)
