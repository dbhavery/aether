# V2 Pipeline Optimization Notes

**Date:** 2026-04-26
**Status:** Ready to launch (phase 5 train_lora is the trigger).

## Why v2

V1 ran QLoRA on Qwen2.5-7B-Instruct with 140k SFT samples and a 25k
eval set running every 500 steps. Two issues surfaced:

1. **Eval dominated training.** Each eval cycle on the full 25k eval
   set burned ~3.5h. With eval_steps=500 and ~8.7k train steps
   planned, eval would have consumed 17h+ on top of training time.
2. **Volume + variety were too thin.** SODA was 78% of training data
   after format_sft because most other sources are smaller.

V1's checkpoint-2000 is preserved as a partial reference but is no
longer the path forward.

## Design changes

| Axis | v1 | v2 | Rationale |
|---|---|---|---|
| Base model | Qwen2.5-7B-Instruct | Qwen2.5-3B-Instruct | ~3x faster; chat naturalness benefits more from sample exposure than parameter count |
| Per-device batch | 4 | 8 | 3B fits 8 in 24GB at max_length 768 |
| Grad accum | 4 | 2 | Effective batch 16 unchanged |
| max_length | 1024 | 768 | Dialog turns rarely exceed 512 tokens; cuts attention compute |
| Attention impl | eager | sdpa | Faster on Ampere+ GPUs |
| LR scheduler | linear | cosine | Smoother plateau at end of run |
| Save_steps / eval_steps | 500 / 500 | 1000 / 2500 | Less interruption |
| Eval set | 25k full | 500 sampled | Eval was the bottleneck |
| Save_total_limit | 3 | 3 | unchanged |
| Corpora — train | 3 (SODA, blended, topical) | 6 (+ OASST2 + UltraChat + DailyDialog) | More variety, more real-human sources |
| Corpora — eval | 1 (empathetic) | 2 (+ WildChat-1M sample) | WildChat = real human prompts |
| Quality filters | length+ASCII | + dedup + repetition + speaker prefix strip | Cleaner gradients |
| Source mix | 78% SODA (synthetic) | 58% SODA / 32% real-human / 10% UltraChat | "Indistinguishable from human" needs human samples |

## Source mix (v2 stratified)

After phase 4 (format_sft) + manual stratification:

| Source | Samples | % | Type |
|---|---|---|---|
| SODA | 180,000 | 58.4% | GPT-3.5 synthetic narrative dialog (Apache, Allen AI) |
| TopicalChat | 39,956 | 13.0% | Curated knowledge-grounded chat (CDLA-Sharing) |
| UltraChat | 30,000 | 9.7% | GPT-3.5 multi-turn (MIT) |
| BlendedSkillTalk | 25,268 | 8.2% | Real human-human chitchat (MIT) |
| DailyDialog | 24,103 | 7.8% | Real human everyday dialog |
| OASST2 | 9,024 | 2.9% | Real human-curated prompts/responses (Apache) |
| **Total train** | **308,351** | | |

Eval-only (NC license / real-human distribution):
- empathetic_dialogues v2 (~51k convos)
- WildChat-1M sample (30k convos, English-filtered)

## Speed expectation

| | Step time | Steps for 12h | Effective batch | Samples in budget |
|---|---|---|---|---|
| v1 (7B) | ~5s | 8,640 | 16 | 138k |
| v2 (3B) | ~1.5-2s | 21,600-28,800 | 16 | 346k-460k |

v2 sized to 308k samples → expected wallclock ≈ 9-12h depending on
actual step time. SDPA + bf16 + smaller batch dimensions should keep
it on the lower end.

## What's left before launch

1. ✅ Phases 1-4 (setup, download, normalize, format_sft) — DONE.
2. ⏳ Phase 5 (train_lora) — config locked, awaiting Don's go-ahead.
3. ✅ Phases 6 (discriminator) and 7 (eval) — implemented inline,
   will run automatically after phase 5 if invoked without `--phase`.
4. Optional pre-launch sanity: 50-step micro-run to verify actual
   step time on this hardware before committing to the full 12h.

## Launch command

When Don gives the go:

```bash
cd C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training
PYTHONUTF8=1 python train_pipeline_v2.py
# or for just phase 5:
PYTHONUTF8=1 python train_pipeline_v2.py --phase train_lora
```

The driver is idempotent — phases 1-4 will skip; phase 5 starts fresh
(no v2 checkpoints exist yet); phases 6-7-8 follow if launched without
`--phase`.

## Known limitations / risks

- **Unsloth not used.** Tried; pulled torch back to CPU, broke the
  stack. Reverted. Speed-up came from smaller base + batch tuning.
- **SODA still 58% of mix.** Even rebalanced, synthetic dominates.
  More real-human conversational corpora would help further (e.g.
  if LMSYS-Chat-1M gate access were granted).
- **WildChat in eval only.** Reserved as the closest-to-real-deployment
  prompt distribution, but not used for training because the assistant
  side of WildChat = LLM responses (would teach AI tells).
- **OASST2 SFT pairs are sparse (9k from 19k convos)** because the
  format_sft pipeline only emits "predict B turn" pairs and OASST2
  trees have shallow B coverage. Could extract A turns too in a v3.
