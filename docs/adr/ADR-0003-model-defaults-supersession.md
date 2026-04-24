# ADR-0003: Model default pins (text + embeddings) — supersedes ADR-0002 embedding default

- **Status:** Accepted
- **Date:** 2026-04-24
- **Deciders:** Don (delegated expert call to Claude during M2 planning). Session delegated authority to execute the pin swap past the usual "reserved decisions" gate because the change is a default-constant + doc swap — implementation mechanics are trivial and the reasoning is research-driven.
- **Supersedes:** `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md` §Decisions 1 (embedding-model default). All other ADR-0002 decisions (Ollama provider, flat-file store, MemoryEmbed capability, cargo feature gate, embed-eligible domains) remain in force.
- **Superseded by:** `docs/adr/ADR-0007-embeddings-onboarding.md` (Decision 2 only — embedding-model default is now tier-parameterised under the ADR-0006 hardware tier model rather than globally singular). Decision 1 (gemma4:e4b LLM pin) remains in force pending a future LLM tier-manifest ADR.
- **Related:** `MILESTONE_1_RETROSPECTIVE_2026-04-23.md` §4 (invariant: ADRs precede cross-layer refactors — this one covers L2 + L4 + tools/evals), `ROADMAP_2026-04-24_MILESTONE_2.md` (runs that consume these defaults).

## Context

Between ADR-0002's acceptance (2026-04-23) and Milestone 2's planning, the local-inference landscape shifted enough to justify re-reading the defaults. Two things had changed:

1. **Text model default** (`packages/l4-router/src/providers/ollama.rs::DEFAULT_MODEL = "gemma4"`) rode the Ollama `:latest` tag implicitly. Per Ollama's library, `gemma4:latest` currently resolves to the `e4b` variant (9.6 GB, 128K context). That resolution could drift over time — a future Ollama update could flip `:latest` to point at the 31B Dense variant, which has a known FlashAttention hang bug on prompts > 3–4K tokens ([Ollama issue #15350](https://github.com/ollama/ollama/issues/15350), not fully resolved as of Ollama v0.20.3 per April 2026 reports).

2. **Embedding model default** (`packages/l2-memory/src/embeddings.rs::DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"`) was picked in ADR-0002 on "768-dim, CPU-fast, pullable" grounds. Since then, **BGE-M3** has landed in the Ollama library as `bge-m3:latest` (1.2 GB, 8K context) with substantially better retrieval quality in April 2026 RAG benchmarks. Tiger Data's comparison: BGE-M3 at 72% retrieval accuracy vs nomic-embed-text's 57.25% — a ~25-point gap that directly affects Memory V2 retrieval quality when that lane ships (M2 Run 2 in the revised roadmap).

ADR-0002 explicitly called out that the provider/model pick was "reversible — nothing breaks when a later PR swaps the provider or backend." This ADR is that PR.

## Decisions

### 1. Text model default: pin explicitly to `gemma4:e4b`.

- Rename the default from `"gemma4"` (untagged, ride-latest) to `"gemma4:e4b"` (pinned variant).
- Rationale: removes silent tag drift. Today's `:latest` = `e4b`; tomorrow's `:latest` might be the FA-hang 31B Dense. Explicit pin freezes the known-good variant until a future ADR deliberately moves it.
- **Power-user override** remains `AETHER_OLLAMA_MODEL` env var. Users who want the larger 26B-A4B MoE for heavier reasoning workloads can set `AETHER_OLLAMA_MODEL=gemma4:26b-a4b-it-q4_K_M` without a code change.
- Aether's workload (single-turn conversational companion) matches `e4b`'s profile (fast, 128K context, 9.6 GB). The 26B-A4B MoE is a coding-agent-shaped choice; not the right companion default.

### 2. Embedding model default: `bge-m3:latest`.

- Flip `DEFAULT_OLLAMA_EMBED_MODEL` from `"nomic-embed-text"` to `"bge-m3"`.
- Rationale: ~25-point retrieval accuracy lift in April 2026 RAG benchmarks. Native multi-functional retrieval (dense + sparse + multi-vector) sets up future hybrid-search work cleanly. MIT license. 8K context (same as nomic). 1.2 GB pull (≈3× nomic's footprint — acceptable at personal scale; BGE-M3 still runs on CPU).
- Dimension change: nomic is 768-dim; BGE-M3 dense is 1024-dim. **No in-place migration needed** — embeddings are opt-in and the flag has almost certainly not been flipped on real data yet (flat-file embedding store is trivially regeneratable; ADR-0002 §Decision 6 documents the store as rewritten-on-every-mutation). If Don has in-fact enabled embeddings and accumulated rows, regenerating is a background job, not an ADR blocker. The flat-file format does not encode dimension in a header; mismatch surfaces as a `query_nearest` length-filter skip (see `embeddings.rs` line 304), not a crash. Safe.

### 3. Eval harness text model default: pin to match the router.

- `tools/evals/__main__.py::AETHER_EVAL_OLLAMA_MODEL` default flips from `"gemma4"` to `"gemma4:e4b"`. Same rationale as Decision 1 — eval reproducibility relies on knowing which Gemma variant was exercised.

### 4. Keep all other ADR-0002 decisions intact.

- Ollama `/api/embeddings` endpoint — unchanged.
- Flat-file domain-partitioned store — unchanged.
- `MemoryEmbed` capability on L5 — unchanged.
- `embeddings` cargo feature gate — unchanged.
- Embed-eligible domains (Durable / Projects / Artifacts only) — unchanged.

### 5. No runtime pivot. Ollama stays.

- Research scanned `mistral.rs`, `candle`, `ZML`, `vLLM`, `LM Studio`, and llama.cpp direct. None surfaced in April 2026 mainstream comparisons as a justified pivot for a Tauri-Rust desktop app at personal scale. Ollama is still the right default local runtime; reevaluate in 6–12 months.

## Consequences

- **First Ollama pull on a fresh profile** now needs `ollama pull gemma4:e4b` and (if embeddings flag on) `ollama pull bge-m3`. M2 Run 3 (Embeddings Onboarding) should bundle both into its availability-check flow.
- **Existing embedding rows from any prior on-flag session** will be retained in flat-file storage but silently skipped on query (dimension mismatch filter in `FlatFileEmbeddingStore::query_nearest`). Recommended clean-up is one-shot: delete `<data_dir>/embeddings/*.jsonl` before first post-swap run with embeddings on. Not a code change.
- **Eval regressions possible** if prior eval captures used raw `"gemma4"` → 26B MoE resolution at the time of capture. The `:e4b` pin freezes behaviour going forward; historical captures may need re-record if they silently tested a different variant. Call out in the first post-swap eval run.
- **Future model pin changes** should be ADRs, not silent commits. ADR-0002 supersession is Milestone 1's second example of this pattern (#1 was ADR-0001 → ADR-0001 execution). Promoting it to explicit policy: any change to `DEFAULT_MODEL` or `DEFAULT_OLLAMA_EMBED_MODEL` constants requires an ADR.

## Rejected alternatives

- **Promote 26B-A4B MoE as default.** Rejected: wrong shape for Aether's conversational workload. Adds ~5 GB of RAM pressure for a model tuned for coding-agent use. Power users can override.
- **Swap runtime to mistral.rs / candle.** Rejected: not enough 2026 ecosystem traction. Costs more than it saves for single-user desktop at this time.
- **In-place migration of nomic-dim embeddings to BGE-M3-dim.** Rejected: no user corpus exists at scale to justify the engineering. Silent skip + opt-in regenerate is simpler and correct.
- **Keep untagged `gemma4` default for auto-update convenience.** Rejected: silent tag drift is exactly the class of bug the rot-guard lints + ADR policy are designed to prevent. Explicit pin wins.

## Verification

- `packages/l4-router/src/providers/ollama.rs::DEFAULT_MODEL` reads `"gemma4:e4b"`.
- `packages/l2-memory/src/embeddings.rs::DEFAULT_OLLAMA_EMBED_MODEL` reads `"bge-m3"`.
- `tools/evals/__main__.py` default literal reads `"gemma4:e4b"`.
- `docs/MEMORY-V2-ARCHITECTURE.md` §9 item 1 updated to reflect BGE-M3.
- `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` §6 env-var section updated.
- `docs/ARCHITECTURE-V2.md` embeddings row updated.
- `tools/lint-memory-doc/check.py` still passes (symbol anchors unchanged by value swap).
- `tools/lint-quality-doc/check.py` still passes (anchors unaffected by the eval default swap).
- `cargo check --workspace` clean.
- `cargo test -p aether-l2-memory --features "sqlite-backend embeddings"` all pass (the one test that referenced `"nomic-embed-text"` literally — `ollama_provider_label_includes_model` — is swapped to `"bge-m3"`).

## Notes

This ADR supersedes ADR-0002's Decision 1 only. ADR-0002 remains the authoritative document for the trait surface, capability model, and store shape. The two should be read together.
