# ADR-0002: Embeddings provider + vector backend (Memory V2 step 6)

- **Status:** Accepted (Decision 1 superseded by ADR-0003 on 2026-04-24).
- **Date:** 2026-04-23
- **Deciders:** Don (owner). Session delegated authority to execute Run 3 past the usual stopping point.
- **Supersedes:** nothing.
- **Superseded by:** `docs/adr/ADR-0003-model-defaults-supersession.md` — Decision 1 (embedding model default) only. All other decisions in this ADR remain in force.
- **Related:** `docs/adr/ADR-0001-memory-domain-reconciliation.md`, `docs/MEMORY-V2-ARCHITECTURE.md` §§8 (hard constraint 5 — local-only), 9 (open questions), 10 item 6.

## Context

`docs/MEMORY-V2-ARCHITECTURE.md` §9 (open questions) left two
decisions open for implementation time:

1. **Embedding provider.** Which local model produces the vectors?
   Doc suggests `bge-small` or `nomic-embed-text` via Ollama.
2. **Vector index backend.** SQLite + rusqlite extensions? A
   separate `sqlite-vec` file? An in-process structure?

ADR-0001 additionally retired the pre-V2 `EmbeddingStore` trait
along with the rest of `kernel.rs`, so Run 3 has a clean slate:
no legacy trait shape to preserve.

Memory V2 step 6 is opt-in (`memory.json::embeddings.enabled`
defaults to `false`) and local-only (hard constraint §8 item 5),
so the "wrong" pick is reversible — nothing breaks when a later
PR swaps the provider or backend.

## Decisions

### 1. Embedding provider: Ollama `/api/embeddings` with model `nomic-embed-text` as the default.

- Ollama is already the canonical local-model dependency for
  Aether text generation (chat + evals default to `gemma4` via
  Ollama). Reusing the daemon avoids adding a second
  model-serving surface.
- `nomic-embed-text` is a 137M-parameter open-weights embedding
  model, 768-dim output, fast enough for background use (~tens
  of ms per text on CPU), freely pullable via `ollama pull
  nomic-embed-text`.
- `bge-small` (the other doc candidate) is smaller but distributed
  primarily through Hugging Face; Ollama support exists but is
  less canonical. Not worth the ergonomic split.
- Provider is configurable at runtime via
  `memory.json::embeddings.provider` (already in the schema)
  plus an `AETHER_EMBED_OLLAMA_MODEL` env var for the model id
  (matches the `AETHER_EVAL_OLLAMA_MODEL` pattern shipped in
  Quality-Eval v1.1).

### 2. Vector backend: in-process flat-file store (domain-partitioned).

- One `HashMap<MemoryId, Vec<f32>>` per opt-in domain, with
  optional JSONL persistence to
  `<app_data>/embeddings/<domain>.jsonl`.
- Nearest-neighbour query is linear cosine-similarity over the
  loaded vectors.
- Pros: zero new heavy dependencies (per CLAUDE.md hard constraint),
  trivial to test, fully local, easy to inspect / delete.
- Cons: O(N) query cost. With 768-dim vectors and a realistic
  personal-memory corpus (≤ tens of thousands of durable items
  over years), this is still sub-millisecond and fits the opt-in
  usage profile. A vector index (`sqlite-vec`, `lancedb`,
  in-process HNSW) can replace the flat-file impl later behind
  the same `EmbeddingStore` trait.
- Out of scope: cross-item metadata indices, BM25 hybrids, any
  SQLite-vec dependency. Those are post-step-6 candidates keyed
  by actual measured slowness, not hypotheticals.

### 3. New L5 capability: `MemoryEmbed`.

Additive variant on the existing `Capability` enum (same pattern
as `MemoryWrite`, `MemoryRead`, `MemoryForget`, `MemoryEdit`).
No `AuditRecordEvent` shape change — the capability is the only
new wire value.

Each embedding write produces exactly one L5 audit row via
`MemoryEmbed`. Symmetric with step 5's MemoryForget-per-sweep
pattern (Decision #57).

### 4. Cargo feature gate: `embeddings` on the `aether-l2-memory` crate.

Mirror of the existing `sqlite-backend` feature. The default
build has no embedding code compiled in; enabling the feature
pulls in the `EmbeddingStore` trait, the flat-file
implementation, and the Ollama provider adapter.

### 5. Embed-eligible domains: Durable, Projects, Artifacts.

Per `docs/MEMORY-V2-ARCHITECTURE.md` §8 and the Run 3 prompt
("persist embeddings only for Durable / Projects / Artifacts on
opt-in"). Session domain is short-lived; Facts / Preferences are
structured/keyed and don't benefit from semantic indexing.

### 6. Out of scope for step 6.

- **Retrieval wiring in the turn engine.** Step 6 lands the
  write path + store + query API. Using embeddings to re-rank
  memory recall in live turns is a separate slice
  (step 6-adjacent or step 8).
- **Remote embedding providers.** Hard constraint §8 item 5.
- **UI beyond the existing Settings toggle.** The toggle already
  exists in `memory.json::embeddings.enabled` + the Settings
  panel from step 2. Step 6 wires the runtime consumer.
- **Embedding forget-on-retention-sweep.** Sweep evicts
  `SessionMemoryStore` rows today; Durable/Projects/Artifacts
  don't have a backing durable store yet (Risk C from 2026-04-23
  Run 1+2 handoff). When that store lands, sweep extends to
  prune embedding rows too.

## Consequences

### Immediate (Run 3 scope)

- New file: `packages/l2-memory/src/embeddings.rs` (behind
  `embeddings` feature) — `EmbeddingStore` trait,
  `FlatFileEmbeddingStore` impl, `EmbeddingProvider` trait,
  `OllamaEmbeddingProvider` impl.
- `packages/l2-memory/Cargo.toml` gains a `embeddings` feature.
- `packages/l2-memory/src/lib.rs` re-exports the new types
  behind `#[cfg(feature = "embeddings")]`.
- L5 `Capability::MemoryEmbed` variant + paired policy /
  capability tests.
- Shell wiring: `memory_service.rs::perform_memory_write`
  branches on `memory_config().embeddings.enabled` and
  `EMBED_ELIGIBLE_DOMAINS.contains(&domain)`. On an allowed
  write it emits an embedding via the configured provider +
  writes to the store; on failure the primary write still
  succeeds (embedding is best-effort, not a hard dependency).
- Emits `memory_embedded` telemetry kind on successful
  embedding writes; aggregates per sweep-style operations.
- `AppState::memory_forget` (and per-item variants) also delete
  the embedding row when present.
- `memory.json` shape unchanged.

### Downstream (step 6-adjacent and step 7)

- Step 7 (rot guard): anchor manifest includes the new
  `embeddings.rs` file, the trait names, and the telemetry
  kind string.
- Retrieval integration (not in this ADR): a future
  `EmbeddingStore::query(domain, vector, k)` consumer in the
  turn engine replaces or augments the current
  `SessionMemoryStore::recent` fallback for durable recall.

### Risk surface

- **Ollama dependency.** Users without Ollama running + the
  model pulled get a WARN + no-op on embedding writes; primary
  writes still land. Matches the prompt's "provider mis-spelled
  ⇒ warn + no-op" requirement.
- **Opt-out doesn't retroactively delete.** Flipping
  `embeddings.enabled` from `true` to `false` stops new writes
  but leaves existing rows. Explicit "forget embeddings" is
  available via the existing forget UX path.
- **Flat-file scalability.** Documented as a known future
  concern. Not a blocker at the opt-in personal-scale target.

## Alternatives considered and rejected

- **sqlite-vec extension as the vector backend.** Rejected for
  step 6 — adds a native-code dependency (not pure-Rust), adds
  a SQLite extension load path the shell has to manage, and
  the O(N) scan wasn't measured as slow for realistic corpora.
  Revisit if real measurements show the flat-file impl is a
  bottleneck.
- **LanceDB / Qdrant / in-proc HNSW.** Rejected as too heavy
  for step 6's "minimal viable write path" scope. All three
  are viable replacements behind the trait, none earn their
  weight today.
- **Hash-based stub provider (no Ollama).** Rejected as a
  shipped default. Acceptable as a test stub only — real users
  should see real embeddings, not a degenerate "similarity =
  string equality" placeholder.
- **Local Python sentence-transformers server.** Rejected —
  Ollama already solves the "local daemon serving models over
  HTTP" problem for Aether; a parallel Python stack would
  double the dependency surface.
- **Putting embeddings inside the existing `conversation_log`
  SQLite table.** Rejected — mixes vector blobs with small
  row-oriented content, forces a migration, and couples vector
  storage to the session-memory schema. Separate concerns.

## Follow-ups

- Step 7 (Run 4): rot guard + doc flip, covers the new
  `embeddings.rs` surface.
- A later slice wires retrieval: the turn engine queries
  embeddings for Durable/Projects/Artifacts recall instead of
  (or in addition to) the short-range session window.
- When the domain-typed durable store lands (post-step-5.5),
  retention sweep extends to prune embedding rows whose parent
  memory has been evicted.
