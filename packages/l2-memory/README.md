# @aether/l2-memory

**Status:** Wave 4 stub.

L2 owns the companion memory kernel — 6 domains, SQLite-backed items, blob refs, embedding refs, provenance tags.

## References

- `ARCHITECTURE.md` — the L2 memory kernel layer.
- `docs/adr/ADR-0001-memory-domain-reconciliation.md` — the memory domains.
- `docs/adr/ADR-0004-durable-store-shape.md` — the SQLite store shape.

## Wave 4 contents

- `MemoryId`, `EmbeddingRef`, `MemoryDomain` (6), `PrivacyClass`, `RetentionKind`, `ProvenanceTag`.
- `MemoryItem` struct.
- `MemoryKernel` + `EmbeddingStore` traits.
- `L2Error`.

## Next wave

Wave 5+ — SQLite-backed `DefaultMemoryKernel` once rusqlite is wired in `aether-storage`; embedding-store adapter (LanceDB candidate).
