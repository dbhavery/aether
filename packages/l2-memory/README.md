# @aether/l2-memory

**Status:** Wave 4 stub + L2.1 turn-scoped session memory.

L2 owns the companion memory kernel — 6 domains, SQLite-backed items, blob refs, embedding refs, provenance tags.

## References

- `planning/plans/L2_memory_kernel_system_design.md`
- `planning/plans/implementation_prep/L2_interface_pack.md`
- `planning/plans/implementation_prep/sqlite_schema_pack.md` §3e

## Wave 4 contents (kernel stub)

- `MemoryId`, `EmbeddingRef`, `MemoryDomain` (6), `PrivacyClass`, `RetentionKind`, `ProvenanceTag`.
- `MemoryItem` struct.
- `MemoryKernel` + `EmbeddingStore` traits.
- `L2Error`.

## L2.1 contents (`session` module)

Narrow, turn-scoped working memory used by the demo/runtime path to carry short-range conversational continuity across turns. Orthogonal to the kernel stub above — the kernel is the long-term, richly-tagged surface; this is just a bounded transcript ring.

- `MemoryRole` (User / Assistant / System).
- `TurnMemoryRecord` (session_id, sequence, role, content, timestamp_ms).
- `RecentMemoryWindow` (oldest-first vector of records).
- `RecentMemoryConfig` (max_turns + max_chars; whichever hits first evicts oldest).
- `SessionMemoryStore` trait — `append`, `recent`, `clear_session`.
- `InMemorySessionMemoryStore` — `Mutex<HashMap<..>>` backed; in-process only.
- `render_transcript(&RecentMemoryWindow) -> String` — deterministic transcript block for prompt injection.

**Out of scope for L2.1:** embeddings, summarisation, retrieval, durable storage, cross-session recall, privacy-class gating. Those belong to the kernel path.

## Next wave

- L2.2+: durable session transcripts via `aether-storage`.
- Wave 5+: SQLite-backed `DefaultMemoryKernel`; embedding-store adapter (LanceDB candidate).
