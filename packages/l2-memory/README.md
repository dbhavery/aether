# @aether/l2-memory

**Status:** Memory V2 — step 4 shipped (session-memory + domain taxonomy).

L2 owns the companion memory kernel: the six Memory V2 domains and a
turn-scoped session-memory store used by the runtime path to carry
short-range conversational continuity across turns.

## References

- `docs/MEMORY-V2-ARCHITECTURE.md`
- `docs/adr/ADR-0001-memory-domain-reconciliation.md`
- `ARCHITECTURE.md` — the L2 memory layer.
- `docs/adr/ADR-0004-durable-store-shape.md` — the durable store shape.

## Current surface

### `domain` module

Hosted here per ADR-0001 (2026-04-23) so background jobs can speak
the taxonomy without coupling to the desktop binary.

- `MemoryDomain` — the six V2 domains: Session / Durable / Facts /
  Projects / Preferences / Artifacts. `ALL` constant + `label()`
  helper. Serde wire format is snake_case.

### `session` module (L2.1 turn-scoped)

Narrow, turn-scoped working memory used by the demo/runtime path
to carry short-range conversational continuity across turns.

- `MemoryRole` (User / Assistant / System).
- `TurnMemoryRecord` (session_id, sequence, role, content, timestamp_ms).
- `RecentMemoryWindow` (oldest-first vector of records).
- `RecentMemoryConfig` (max_turns + max_chars; whichever hits first evicts oldest).
- `SessionMemoryStore` trait — `append`, `recent`, `clear_session`,
  `remove`, `update`.
- `InMemorySessionMemoryStore` — `Mutex<HashMap<..>>` backed; in-process only.
- `SqliteSessionMemoryStore` + `DurableSessionStore` (feature `sqlite-backend`).
- `render_transcript(&RecentMemoryWindow) -> String` — deterministic transcript
  block for prompt injection.

### Retired in ADR-0001 (2026-04-23)

`MemoryKernel`, `MemoryItem`, `PrivacyClass`, `RetentionKind`,
`EmbeddingStore`, `EmbeddingRef`, and the pre-V2 `Personal/Work/...`
`MemoryDomain`. None had real-world consumers; the Wave 4 kernel
stub predated the Memory V2 taxonomy freeze.

## Next waves

- Memory V2 step 5: retention sweep (boot + low-rate tick) consuming
  `SessionMemoryStore` + per-domain `retention_days` from the shell's
  `MemoryConfig`.
- Memory V2 step 6: embeddings opt-in; a future `embeddings` module
  carries the new `EmbeddingStore` trait if we need one.
- Memory V2 step 7: `tools/lint-memory-doc/` rot guard + doc flip.
