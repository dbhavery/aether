# L2 — Companion Memory Kernel

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.2)
**Depends on:** L5 (policy gates memory reads/writes), L6 (persona supplies salience rules).
**Blocked by:** storage-engine choice (borrowable), event bus.

---

## Purpose

The companion memory system. Five-layer kernel (ephemeral / session / durable-user / artifact / behavior) with novelty filtering, scoped recall, editable entries, provenance, confidence decay, and user-enforced forgetting. This is what makes Aether feel like a relationship rather than a stateless chat.

## Why must-own

Memory is the primary surface where trust, continuity, and "companion feel" live. SaaS wrappers cannot offer editable, scoped, provenance-tracked memory with local-first guarantees. This layer is the single largest trust moat together with L5.

## Boundaries

**Owns:**
- Five-layer taxonomy & lifecycle rules.
- Novelty/salience filter (deciding what becomes durable).
- Retrieval ranker (semantic + recency + salience + persona-weighted).
- Editing, forgetting, and provenance UI data model.
- Confidence decay model.
- Memory-write event emission and cross-engine memory-hit publication.
- Schema, migrations, sync policy.

**Does not own:**
- Underlying vector store / SQLite (borrowable; behind our interface).
- Embedding model (borrowable).
- Raw artifact storage (filesystem).
- Permission evaluation for memory access (L5).

## Dependencies

- **L5 policy** — every memory read/write passes through capability check.
- **L6 persona** — salience weights parameterized per-persona.
- **L1 reflex** — fast memory hit (<150 ms) for reflex classifier.
- **Cognition deliberative path** — full recall (<500 ms).
- **Sync layer** — memory is delta-synced across devices (desktop canonical).

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Vector store | **Borrow** (Chroma / LanceDB / Qdrant-embedded) behind `MemoryStore` trait. |
| Embedding model | **Borrow** (BGE-M3 or similar) — swap-friendly. |
| SQLite backing | **Borrow** for durable layer. |
| Novelty filter | **Custom.** Defines what gets remembered — doctrine-sensitive. |
| Retrieval ranker | **Custom.** Balances salience vs recency vs persona; shapes the relationship. |
| Editing / forgetting UX data model | **Custom.** Trust surface. |
| Provenance chain | **Custom.** Audit requirement. |
| Sync protocol | **Custom** (on top of borrowed CRDT lib TBD). |

## Five layers (recap)

1. **Ephemeral** — single-turn scratch; auto-purged.
2. **Session** — within-conversation continuity; bounded decay.
3. **Durable user** — long-term user facts, preferences, relationships.
4. **Artifact** — files, documents, captures user has attached.
5. **Behavior** — learned interaction patterns (style, pacing, preferred modes).

Each layer has distinct write policy, retention default, export policy, and visibility in trust center.

## Key risks

1. **Runaway durable layer** — memory bloat, irrelevant recall. Mitigation: novelty threshold + periodic compaction + user-surfaced "what I remember" review.
2. **Silent context leak** — memory hit injected into prompt without user awareness. Mitigation: trust-center surfaces every memory used per turn.
3. **Provenance loss on sync conflict.** Mitigation: CRDT/op-log with per-entry provenance chain.
4. **Forgetting that doesn't forget** — embeddings/caches retain removed data. Mitigation: cascading delete across vector store + cache + event log.
5. **Salience gaming** — persona-weighted ranker amplifies bias. Mitigation: explainable ranker; trust-center shows why an entry surfaced.

## Sequencing

1. **P0 (OSS Preview)** — ephemeral + session + simple durable (flat SQLite + Chroma). No editing UI beyond "clear all." Demonstrates continuity.
2. **P1 (Pro Phase 0)** — five-layer taxonomy formalized; novelty filter; editing UI; provenance for durable.
3. **P2 (Pro Phase 1)** — confidence decay; "what I remember" review surface; export/forget UI.
4. **P3 (Pro Phase 2)** — artifact layer + behavior layer; cross-device sync (CRDT/op-log choice resolved).
5. **P4 (Pro Phase 3+)** — persona-weighted ranker; Isabelle-specific salience rules.

## Acceptance criteria

- Memory hit latency p95 <150 ms (reflex) / <500 ms (deliberative).
- Every durable entry has provenance (source turn / source artifact / source user-action) viewable in trust center.
- "Forget this" propagates to vector store, cache, and sync within <1 s locally.
- Novelty filter reduces durable-layer write rate to <5% of candidate writes in typical conversation.
- Zero silent memory access — every memory used per turn is logged and retrievable.
- Sync converges across devices within 30 s of network reconnection without provenance loss.

## Open decisions for executing agent

- Vector store choice (Chroma vs LanceDB vs Qdrant-embedded).
- Embedding model specifics per tier (BGE-M3 is default but may differ for Lite).
- CRDT library vs op-log (surfaces in OPEN_QUESTIONS sync architecture).
- Behavior-layer schema (last to design).

## Reference specs

- `file:///C:/Users/dbhav/Projects/aether-planning/10_memory_architecture.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/13_trust_security_redteam.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/16_tech_stack.md`
