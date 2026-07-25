# HuggingFace embedding provider — enablement guide

> **Status:** Available 2026-04-25 (Phase 4C of the autonomous session).
> **Default:** OFF. Configure via `memory.json::embeddings.provider`.
> **Cross-references:** ADR-0007 D7 (Spark default model),
> DECISIONS_LOG D-001 (`nomic-embed-text` substitution),
> DECISIONS_LOG D-013 (this provider's architecture choice).

## Why this exists

ADR-0007 Decision 7 named `bge-small-en-v1.5` as the Spark-tier
embedding default. At the time, no Rust-side loader existed for
HuggingFace models, so DECISIONS_LOG D-001 substituted
`nomic-embed-text` (Ollama-hosted) as a temporary stand-in. This
provider closes that gap: with the helper installed, the original
ADR-0007 D7 Spark default is loadable.

The substitution to `nomic-embed-text` remains valid for users who
do NOT install the Python helper — the `ollama:` provider remains
zero-dependency and the bundled default for fresh installs.

## How it works

1. `memory.json::embeddings.provider` is set to `hf:<org>/<repo>`
   (e.g. `hf:BAAI/bge-small-en-v1.5`).
2. The Tauri shell's `swap_embedding_provider_for_config` arm
   constructs an `HfEmbeddingProvider` and swaps it into the active
   `EmbeddingProvider` Arc. No subprocess is spawned yet.
3. On the first `embed()` call, the provider spawns
   `python tools/hf_embed_helper/embed.py` as a subprocess.
4. The helper imports `sentence_transformers`, downloads + loads the
   requested model on first request (~130 MB for
   `bge-small-en-v1.5`, cached under `~/.cache/huggingface/hub/`),
   and embeds the input.
5. Subsequent embed calls reuse the same helper subprocess and the
   in-memory model cache. Per-embed cost drops to <100 ms.

## Prerequisites

- **Python 3.9+** discoverable as `python` on the desktop shell's
  PATH. Override with `AETHER_HF_HELPER_PYTHON=<path>` if you want
  the helper to use a venv-bundled interpreter.
- **`sentence-transformers`** installed for that interpreter:
  ```
  python -m pip install sentence-transformers
  ```
  This pulls in `torch` (~2 GB on first install).
- **Outbound HTTPS to huggingface.co** for the first model download.
  Subsequent requests use the local cache and need no network.

## Configuration shapes

`memory.json::embeddings.provider` accepts:

| String                              | Effect                                         |
| ----------------------------------- | ---------------------------------------------- |
| `hf:BAAI/bge-small-en-v1.5`         | Canonical HF Hub form. Preferred.              |
| `hf:BAAI:bge-small-en-v1.5`         | Legacy three-segment form. Normalised to canonical at swap time. |
| `ollama:bge-m3`                     | Existing Ollama path (unchanged by this work). |
| `nomic-embed-text` (no prefix)      | Bare name = Ollama (D-001 substitution).       |

## Env var overrides

- `AETHER_HF_HELPER_PYTHON` — interpreter command (default `python`).
- `AETHER_HF_HELPER_SCRIPT` — path to `embed.py` (default
  `tools/hf_embed_helper/embed.py` resolved relative to the shell's
  CWD).

## Troubleshooting

| Symptom                                          | Likely cause                                                        | Fix                                              |
| ------------------------------------------------ | ------------------------------------------------------------------- | ------------------------------------------------ |
| `embed`: "spawn hf helper failed: python=…"      | Python not on PATH or wrong interpreter                             | Set `AETHER_HF_HELPER_PYTHON` to the right one.  |
| `embed`: "hf helper error (load): No module named 'sentence_transformers'" | `sentence-transformers` not installed for the active interpreter    | `python -m pip install sentence-transformers`    |
| `embed`: "hf helper error (load): … OSError"     | First-run download failed (network or HF 503)                       | Retry; check `huggingface.co` connectivity.      |
| First embed takes 15+ seconds                    | Expected — model load is one-shot per provider lifetime             | Subsequent embeds are <100 ms.                   |
| `embed`: "hf helper closed stdout before responding (likely crashed)" | Helper crashed mid-conversation; next call respawns automatically   | Check stderr in shell logs for the underlying Python traceback. |

## Heavy-usage cost summary

| Operation                        | Cost (Don's 3090 Ti workstation, CPU embed) |
| -------------------------------- | ------------------------------------------- |
| First helper spawn               | ~2 s (Python import only)                   |
| First model load (`bge-small-en-v1.5`, no cache) | ~10 s download + ~5 s warm                  |
| First model load (warm cache)    | ~5 s                                        |
| Per-embed (single text, ≤256 tokens) | ~30-80 ms                                   |
| 1000-row backfill (warm cache)   | ~1-2 min wall-clock                         |

GPU acceleration is NOT used in v1: `sentence-transformers` defaults to
CPU unless explicitly told otherwise. CPU is fast enough for personal-
scale use; the GPU is reserved for chat / vision workloads.

## What's deferred

- **Native-Rust path (candle).** A `candle-transformers`-backed BERT
  pipeline would remove the Python dependency but adds ~50 crates to
  the build and per-model-family pipeline code. Tracked in
  DECISIONS_LOG D-013.
- **GPU embed.** Would require either configuring
  `sentence-transformers` to use CUDA (`device='cuda'`) or migrating to
  the candle path. Personal-scale workloads don't need it; deferred
  with no specific trigger.
- **Multiple-text batched embed.** The helper protocol embeds one text
  per request. A batched op would amortise per-call protocol cost;
  worth doing only if a future workload (e.g. a 10k-row migration) makes
  the per-call cost visible. The 1000-row case fits inside the
  ad-hoc-feels-fine budget today.
