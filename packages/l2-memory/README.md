# @aether/l2-memory

**Status:** Wave 4 stub.

L2 owns the companion memory kernel — 6 domains, SQLite-backed items, blob refs, embedding refs, provenance tags.

## References

- `planning/plans/L2_memory_kernel_system_design.md`
- `planning/plans/implementation_prep/L2_interface_pack.md`
- `planning/plans/implementation_prep/sqlite_schema_pack.md` §3e

## Wave 4 contents

- `MemoryId`, `EmbeddingRef`, `MemoryDomain` (6), `PrivacyClass`, `RetentionKind`, `ProvenanceTag`.
- `MemoryItem` struct.
- `MemoryKernel` + `EmbeddingStore` traits.
- `L2Error`.

## Next wave

Wave 5+ — SQLite-backed `DefaultMemoryKernel` once rusqlite is wired in `aether-storage`; embedding-store adapter (LanceDB candidate).
