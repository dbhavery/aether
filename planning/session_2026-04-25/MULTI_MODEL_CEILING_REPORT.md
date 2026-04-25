# Phase 3C — Multi-Model VRAM Coexistence Ceiling Report

**Date:** 2026-04-25 (autonomous run)
**Hardware:** RTX 3090 Ti, 24 GB VRAM (24564 MB reported by `nvidia-smi`)
**Ollama:** v0.21.2, default env (no explicit `OLLAMA_MAX_LOADED_MODELS` override)
**Harness:** `planning/session_2026-04-25/bench_multi_model_ceiling.py`
**Raw timeline:** `planning/session_2026-04-25/multi_model_ceiling.json`

---

## Headline finding

**Ollama caps concurrent residency at 3 models by default — VRAM is NOT the binding constraint at the small-model end.**

The 24 GB card has plenty of headroom for a 4th small model (a 1.36 GB qwen3:1.7b would have brought total residency to ~6 GB across the 3 small + 1 small-LLM, leaving ~18 GB free), but Ollama evicted `gemma4:e4b` (the largest of the original trio) the moment a 4th model loaded. This matches the documented Ollama default `OLLAMA_MAX_LOADED_MODELS=3`. **Aether's coexistence ceiling on stock Ollama config is 3, not VRAM-limited.**

## Hard ceiling for a single large model

`gemma4:26b` (17.99 GB on disk) loads to ~19 GB resident VRAM and evicts every other model. After load, `nvidia-smi` reports 23051 MB used (94% of the card). The Ollama runtime treats it as solo-resident under default settings and almost certainly under any settings (one model + tail of others would exceed 24 GB).

## Timeline (compressed)

| Step | Action | nvidia-smi MB | Resident | Eviction |
|---|---|---|---|---|
| 0 | baseline | 3833 | (none) | — |
| 1 | load gemma4:e4b | 14255 | gemma4:e4b | — |
| 2 | load bge-m3 | 15940 | + bge-m3 | — |
| 3 | load nomic-embed-text | 16736 | + nomic-embed-text | — |
| 4 | load qwen3:1.7b (4th) | 11482 | qwen3:1.7b, bge-m3, nomic-embed-text | **gemma4:e4b** |
| 5 | load gemma4:26b | 23051 | gemma4:26b only | bge-m3, nomic-embed-text, qwen3:1.7b |

## Numbers worth memorizing

- **3 models** = stock Ollama coexistence ceiling under default config.
- **Aether's baseline trio** (gemma4:e4b + bge-m3 + nomic-embed-text) = 12.9 GB resident (16.7 GB nvidia-smi after baseline overhead).
- **Headroom above baseline at peak** = 19.2 GB.
- **Free VRAM at the 4-model attempt** ≈ 7.8 GB — wasted because of the model-count cap, not VRAM pressure.
- **Single-large-model ceiling** = `gemma4:26b` ~19 GB resident, 94% of card.

## Why the eviction surprised the harness

Initial assumption was VRAM-driven LRU eviction. Actual behavior is **count-driven** eviction (Ollama keeps `OLLAMA_MAX_LOADED_MODELS` models warm; loading the N+1th evicts the LRU regardless of available VRAM). The largest model (gemma4:e4b, ~10 GB) was the LRU at step 4 because the two embedders had been touched after it.

This has architectural implications for Aether: the future avatar (ADR-0008) and any non-Aether AI workload sharing the card will not race for VRAM with Aether's trio — they will race for an Ollama loaded-model slot. **Aether should consider setting `OLLAMA_MAX_LOADED_MODELS=4 or 5` in the Ollama daemon env on Forge tier to actually access the headroom** the 24 GB card provides.

## Recommended ADR-0006 §6 delta (proposed; do NOT edit ADR-0006 in this commit)

The current §6 reservation table is VRAM-budgeted with no model-count guidance. Suggested updates:

> **Forge tier addendum (proposed 2026-04-25):**
>
> Empirical ceiling on a 24 GB / RTX 3090 Ti with stock Ollama config: **3 concurrent models, ~17 GB resident** for the Aether baseline trio (gemma4:e4b + bge-m3 + nomic-embed-text). The remaining ~7 GB headroom is gated by `OLLAMA_MAX_LOADED_MODELS` (default 3), not by VRAM.
>
> A single large generator (`gemma4:26b`, ~19 GB resident) consumes 94% of card VRAM and forces solo residency under any setting; this is the practical "swap to a heavier model" budget for Forge users with no concurrent avatar/embedding workload.
>
> **Operational guidance for Aether on Forge tier:** if the avatar (ADR-0008) is to run as a 4th Ollama-managed model concurrent with the trio, the Ollama daemon must set `OLLAMA_MAX_LOADED_MODELS=4` (or higher), AND the avatar's resident VRAM must fit within `24 GB - (current_trio_resident ~17 GB) = ~7 GB`. The §6 Forge reservation of "~8 GB reserved" remains directionally correct; this measurement validates it.
>
> **Operational guidance for Aether on Flame tier (12-16 GB cards):** the trio alone consumes ~13 GB resident — already above the conservative half of a 16 GB card. Flame users running the avatar concurrently must either downgrade the generator (e.g., gemma4:e4b → qwen3:8b at ~5 GB resident) or accept Ollama-driven eviction churn between LLM and embedder. This validates the existing §6 Flame reservation pressure but reframes the constraint as **model-count + per-model size**, not raw VRAM.

The numerical reservations (~4 GB Flame, ~8 GB Forge) survive intact. What changes is the *operational framing*: Aether should treat `OLLAMA_MAX_LOADED_MODELS` as a first-class tier-tunable, not just VRAM.

## Files touched

- created `planning/session_2026-04-25/bench_multi_model_ceiling.py`
- created `planning/session_2026-04-25/multi_model_ceiling.json`
- created `planning/session_2026-04-25/MULTI_MODEL_CEILING_REPORT.md` (this file)
- appended to `planning/session_2026-04-25/DECISIONS_LOG.md` (D-005)

## Cleanup verification

Post-run: all 5 probed models unloaded with `keep_alive=0`. `nvidia-smi` returned to baseline range (~3.8 GB) and `/api/ps` returned empty.
