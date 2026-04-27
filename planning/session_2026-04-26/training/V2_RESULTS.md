# V2 Training Results

**Run completed:** 2026-04-27
**Base model:** Qwen/Qwen2.5-3B-Instruct
**Adapter:** `checkpoints_v2/qwen25_3b_human_lora/final`

## Headline numbers

| Metric | Value |
|---|---|
| Train samples | 80,000 (stratified, 32% real-human / 58% SODA / 10% UltraChat) |
| Train steps | 5,000 (1 epoch, effective batch 16) |
| Wallclock | 9h 14min (~6.7 sec/step steady-state) |
| Final train loss | 1.057 |
| Final eval loss | 1.595 (held-out 500 samples) |
| Eval token accuracy | 65.3% |

## Discriminator-based human-likeness score

DistilBERT classifier trained on 5,400 samples (real human dialog
turns vs gemma4:e4b outputs). Eval accuracy: **99.83%** — meaning
the classifier reliably tells real-human from gemma4 outputs.

Then asked: how often does each model's output get classified as
human?

| Model | Classified-as-human rate |
|---|---|
| Baseline gemma4:e4b | **76.5%** |
| V2 fine-tuned (Qwen + LoRA) | **100.0%** |
| Delta | **+23.5 pp** |

## Reading the result honestly

100% is **suspiciously perfect** — and the reason matters.

The discriminator learned to identify *gemma4-specific* AI-tells:
emoji usage (😂), structured reply patterns, "Haha/" opener
frequency, hedging phrases. When V2's fine-tuned Qwen outputs lack
those gemma4 tells, the discriminator's only category for them is
"human" — even if a human reader would find them distinctively
"trained-on-PersonaChat-style," not naturally varied human prose.

In other words: the v2 model is **non-gemma4**, not necessarily
**indistinguishable from a discerning human reader**.

## Sample outputs (illustrative)

Same context: a chitchat continuation prompt.

**Baseline gemma4:e4b** (76.5% human-rate):
- "Oh, nice. What kind of acting do you like? Like theater, film, stuff?"
- "Haha, I wouldn't say I'm a *great* cook. More like I can follow a recipe and not set anything on fire? 😂 You're the expert!"
- "Haha, classic choice. Nothing beats a dependable ride, i guess."

**V2 fine-tuned** (100% human-rate):
- "i have 2 children"
- "that is nice. i have an old cadillac"
- "I do not like working out at all, I hate it so much"
- "I'm sure they would.  What kind of snakes do you have?"

V2 outputs: terse, lowercase, blunt. Strongly biased toward
PersonaChat/SODA register where short turns dominate. The
discriminator can't tell these from real PersonaChat humans — but
they don't represent the full register variety humans actually
show in spoken or naturalistic conversation.

## What V3 needs to improve

1. **Register variety.** v2's fine-tune is monoregister (short,
   chitchat). v3's broader corpus (Cornell movies = dramatic, Reddit
   = internet, podcasts = spoken) should expand this.
2. **A stronger discriminator.** Train it on outputs from MULTIPLE
   models (gemma + base Qwen + base Llama + finetuned variants) so
   it learns "AI in general" not "gemma4 specifically." Defer to v4
   eval methodology — keeping the v2 discriminator as a baseline
   gives us comparable v2-vs-v3 numbers.
3. **More naturalistic eval prompts.** v2 eval pulled prompts from
   the same corpus mix used for training. v3 should also eval
   against WildChat (real human prompts the model has never seen).

## Key learnings for v3 launch

- **gemma4:e4b is a reasoning model.** Always pass `think:false`
  in API calls or it spends all `num_predict` budget on the
  `thinking` field and returns empty content. Phase 6 first run
  was generating 1 negative every ~45 seconds because of this.
  Fixed → 0.87 sec/gen.
- **Discriminator quality scales with negative diversity.** The
  current discriminator is trivially separable because it learned
  gemma4-specific patterns. Multi-model AI negatives in v4 would
  raise the difficulty meaningfully.
- **Step time on 3090 Ti for QLoRA Qwen2.5-3B + max_length 768
  + grad_checkpointing is ~7s/step.** Faster than 7B (5s) was
  expected to be much faster (1.5-2s); 3B + bnb 4-bit overhead
  + grad_checkpointing closed most of the gap.
