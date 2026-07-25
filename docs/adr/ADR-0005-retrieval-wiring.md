# ADR-0005: Retrieval wiring — capability, timing, rank, lookup

- **Status:** Accepted
- **Date:** 2026-04-25
- **Deciders:** Don (owner). Authorised all three reserved decisions (#M2-01, #M2-02, #M2-03) and the follow-up lookup-method decision in this session; Claude captures the rationale.
- **Supersedes:** nothing.
- **Superseded by:** nothing.
- **Related:** `docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md` (embedding store shape), `docs/adr/ADR-0003-model-defaults-supersession.md` (bge-m3 default), `docs/adr/ADR-0004-durable-store-shape.md` (Durable lane), `ROADMAP_2026-04-24_MILESTONE_2.md` (Run 2), `HANDOFF_2026-04-25_M2_RUN_1_COMPLETE.md` §§5, 7.
- **Cleanup follow-up:** `docs/adr/ADR-0009-retrieval-augmented-utterance-audit-reach.md` (Accepted 2026-04-25, commit `b577105`) cleaned up the audit-row asymmetry this ADR introduced — specifically, `submit_turn` here passes the augmented `router_utterance` as a single field, but the L5 audit row should record the user's *original* utterance, not the augmented form. ADR-0009 splits `TurnRequest` into `original_utterance` + `model_input_utterance` and bumps the audit row to schema v2 with `retrieval_provenance`. The pipeline described in this ADR is otherwise unchanged.

## Context

Memory V2 (ADR-0001 / ADR-0002) shipped an embeddings lane that today has **no consumer**. Runs 0–4 of Milestone 1 built the write path; Mini-Run 0 (ADR-0003) picked BGE-M3 as the default vectoriser; ADR-0004 gave Durable a real backing store so there is something to embed. Run 2's job is to close the loop — make the turn engine actually read from `EmbeddingStore::query_nearest` so turning the `embeddings.enabled` flag on has a user-visible effect.

Four design questions surfaced while proposing Run 2:

1. **Where in the turn pipeline does retrieval run?** Parallel with prompt compilation, or sequentially after memory recall?
2. **What L5 capability name covers this read?** Reuse the existing `MemoryRead`, or introduce a distinct variant?
3. **How do retrieved items rank?** Pure similarity, similarity + recency, something richer?
4. **How does the orchestrator get content from a `SimilarityHit`?** Add a fetch method to the memory store, or denormalise content into `EmbeddingRow`?

Don authorised all four decisions in this session. ADR-0005 captures them as the implementation contract for Run 2.

## Decisions

### 1. Timing: sequential, post-memory, pre-prompt. Hard 5s bailout. (Resolves #M2-02.)

Turn pipeline becomes:

```
intent & tool selection
  → apply Memory V2 enrichment (SessionMemoryStore::recent on the domain-routed store)
  → run retrieval_context (embed utterance, query every embed-eligible domain's EmbeddingStore)
  → build final prompt (memory + retrieval + request)
  → model call
```

Retrieval runs **after** memory recall so its query vector can be formed from the memory-augmented context, not just the raw utterance. Retrieval runs **before** prompt construction so the prompt builder stays the single assembly point.

**Bailout.** The embed call is an Ollama round-trip (~100–300ms locally, single-digit seconds on cold start). If any single retrieval phase (embed, query, fetch) exceeds **5000 ms**, the orchestrator aborts retrieval, emits exactly one `warn!` naming the failed phase, and returns the memory-only window. The turn completes on memory context alone. No silent fallback (doctrine §9 §no-silent-fallback); the warn is the audible signal.

Rationale: sequential beats parallel-with-timeout here because retrieval quality materially improves when the query vector reflects memory state, not just the raw utterance. The 5s bailout is a safety valve for a broken Ollama, not a normal-path latency target.

### 2. Capability: `Capability::RetrievalContext`. Wire token `retrieval_context`. (Resolves #M2-01.)

New variant on `aether_l5_policy::Capability`. Default posture: Auto (parallel to `MemoryRead`). L5 audit rows for retrieval are distinct from session-recall audit rows, so future surfaces (Memory tab "recalled X" chips, audit export, metrics dashboards) can filter on the kind of read without string-matching.

Naming follows the existing enum convention (PascalCase variant, snake_case wire via `#[serde(rename_all = "snake_case")]`). Extendable: if future runs add retrieval modes beyond semantic search (web retrieval, code-aware retrieval, graph retrieval), they can land as sibling capabilities (`RetrievalContextWeb`, etc.) without re-opening this ADR.

Rationale for a new variant rather than reusing `MemoryRead`: audit distinguishability. Bundling retrieval-augmented reads under `MemoryRead` would force string-matching on resource scope to tell them apart. One additional enum variant is cheaper now than a capability schism later.

### 3. Rank: score desc → recency tiebreak → fixed top-K. (Resolves #M2-03.)

Rank contract:

1. Primary sort: cosine similarity **descending** (higher = closer).
2. Tiebreak: `timestamp_ms` **descending** (newer first). Timestamp is sourced from the memory row reached via the lookup method (Decision 4) — never from the embedding row, which does not carry one.
3. Truncate to a fixed **top-K**. Default **K = 5**. Configurable via a new additive field `memory.json::retrieval.max_items: u32` (default 5 on missing / null, same additive-on-read shape every other field in `memory.json` uses).
4. No rerank stage in Run 2. A later ADR may add cross-encoder rerank, LLM-judge rerank, or other post-processing; this ADR explicitly punts.

Rank applies ONLY to the retrieval output. Session recall and retrieval occupy **separate slots** in the final prompt (per Decision 1 timing). They are not unioned; no "interleave by recency + similarity" across the two. The prompt builder gets a `RecentMemoryWindow` (session) and a `Vec<RetrievalHit>` (retrieval) as independent inputs.

Rationale: score+recency+K is the minimum stable contract that:
- tests can assert against (higher scores first; for equal scores, newer first; never exceed K);
- survives backend swaps (swap BGE-M3 for another provider, swap the flat-file store for sqlite-vec — the rank contract is unchanged);
- leaves room for future rerank without breaking downstream shape.

### 4. Lookup: `SessionMemoryStore::fetch_one(session_id, sequence)`. (New; #M2-15.)

`EmbeddingStore::query_nearest` returns `Vec<SimilarityHit>`. A `SimilarityHit` carries only `memory_id` + `score`. The retrieval orchestrator must dereference each `memory_id` back to its content to populate the prompt.

Chosen approach: **extend the `SessionMemoryStore` trait with a `fetch_one` method**.

```rust
fn fetch_one(
    &self,
    session_id: &str,
    sequence: u64,
) -> Result<Option<TurnMemoryRecord>, L2Error>;
```

- `Ok(Some(row))` — row present.
- `Ok(None)` — row evicted / never existed. Orchestrator drops the hit and moves on; the embedding row is now orphaned and will be cleaned on the next per-item forget.
- `Err(_)` — store failure. Propagates up; orchestrator decides whether to bail or continue with partial results.

Implemented on both `InMemorySessionMemoryStore` (trivial filter on the per-session ring) and `SqliteSessionMemoryStore` (parameterised SELECT on `{table_name}`). The parameterised query inherits the ADR-0004 table routing for free — a `fetch_one` on the Durable-lane store hits `durable_log`, same row semantics as `recent`.

**Rejected alternative: denormalise `content` into `EmbeddingRow`.** Would be slightly faster (one fewer read per hit) but:
- content is now stored in two places (memory + embeddings);
- edits via the Memory tab leave the embedding copy stale until a sync path is wired;
- any existing embedding JSONL files need regenerating — ADR-0002 shape change.
The speed win does not justify the correctness tax. `fetch_one` is additive, backwards-compatible, and keeps content single-source.

### 5. `memory_id` parse contract.

`mk_memory_id(session_id, seq)` today produces `"mem-{session_id}-{seq}"` at the shell boundary. The orchestrator needs the inverse to route a `SimilarityHit` to the right store and row. Two options:

- **(a) Carry `(session_id, sequence)` inline on `EmbeddingRow`** (ADR-0002 shape change).
- **(b) Reverse-parse `memory_id` at the orchestrator.**

Choose **(b)**. Parse `memory_id` with a stable regex at the orchestrator boundary; no store shape change. Failures on parse (malformed id, unknown shape) drop the hit with a `warn!` — same failure mode as a stale embedding row. Document the shape in one place (`mk_memory_id` + orchestrator parser) so rotating the format is a paired change.

## Consequences

- **New L5 variant** `RetrievalContext`. `packages/l5-policy` tests grow by one coverage row (default posture Auto, parallel to MemoryRead).
- **New trait method** `SessionMemoryStore::fetch_one`. Every existing implementation (`InMemorySessionMemoryStore`, `SqliteSessionMemoryStore`) gains a small implementation. Trait extensions land additively — consumers that only call `append`/`recent`/etc. compile unchanged. Default impl is NOT provided (trait method without body would break L5 consumers that currently implement the trait in tests via a shell stub; force explicit implementation).
- **New config field** `memory.json::retrieval.max_items: u32` with default 5. Additive; existing files without the field read the default.
- **New orchestrator module** likely `apps/desktop/src-tauri/src/retrieval.rs` (or inline in `memory_router.rs` if Don prefers fewer files). Holds the embed → query → fetch → rank pipeline + the 5s bailout.
- **Wire integration** in `MemoryAwareRouter::dispatch` and `RoleTaggedOllamaRouter::dispatch`: insert the retrieval call between `self.store.recent(session_id)` and `self.inner.dispatch(...)`.
- **Tests grow** by:
  - L2: +1 for `fetch_one` (round-trip under both in-memory and SQLite backends).
  - L5: +1 for the `RetrievalContext` default posture.
  - Shell: +4 to +6 retrieval orchestrator tests (determinism, fallback, bailout, rank, K cap, memory-only byte-identity with embeddings off).
- **Rot guards grow** by ~8 anchors in `tools/lint-memory-doc/check.py`.

## Rejected alternatives

- **Parallel with 250ms timeout** (my original proposal). Rejected: retrieval quality benefits from seeing memory-augmented context; parallel robs that. Sequential with a 5s bailout captures the safety concern without the quality cost.
- **Reuse `MemoryRead` capability**. Rejected: bundles retrieval-augmented reads with session-recall audit lines. Cheap now, expensive to untangle later.
- **Union session recall + retrieval into one ranked stream**. Rejected: session recall has no similarity score; shoehorning it into the rank contract requires inventing a score or stapling a weight. Two slots in the prompt is cleaner.
- **Denormalise content into `EmbeddingRow`**. Rejected (Decision 4 discussion).
- **Inline `(session_id, sequence)` on `EmbeddingRow`**. Rejected (Decision 5 discussion).
- **Rerank stage in Run 2**. Rejected: scope creep. Future ADR if evidence emerges.

## Verification (Run 2 close checklist)

- `Capability::RetrievalContext` defined in `packages/l5-policy`; default-posture test covers it.
- `SessionMemoryStore::fetch_one` in trait; implemented on InMemory + SQLite; integration test for each.
- `memory.json` shape gains `retrieval.max_items` (additive, default 5).
- Orchestrator module exists; embed → query → fetch → rank pipeline wired with 5s bailout.
- `MemoryAwareRouter::dispatch` + `RoleTaggedOllamaRouter::dispatch` call the orchestrator when `embeddings.enabled == true`; skip it when `false`.
- Shell test: `embeddings.enabled = false` → byte-identical window to tip `3ffe105`.
- Shell test: embeddings on + unreachable provider → memory-only window + one `warn!` per turn.
- Shell test: embeddings on + hits present → prompt carries retrieval rows in #M2-03 rank order, capped at K.
- Shell test: 5s bailout triggers on a fake-slow provider.
- `python tools/lint-memory-doc/check.py` passes after anchor additions.
- `docs/MEMORY-V2-ARCHITECTURE.md` §10 or a new §11 captures the retrieval path.

## Notes

This ADR is the last "structural" decision Milestone 2 Run 2 needs. Everything after is mechanical implementation of the four decisions above. If ADR-0006 emerges in a later run, it should be for retrieval *extensions* (web retrieval, rerank, code-aware retrieval) — not for re-opening these four choices.
