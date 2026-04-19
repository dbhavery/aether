# L2 Memory Kernel — Interface Pack

> **Layer:** L2 Memory Kernel (Aether)
> **Source of truth:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md
> **Companions:** file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md , file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md , file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md , file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md , file:///C:/Users/dbhav/Projects/aether-planning/plans/L7_trust_ux_onboarding_system_design.md , file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_L3_L6_integration_notes.md
> **Status:** Draft 1 — interface surface only, no implementation.

---

## 1. Purpose

The L2 Memory Kernel is Aether's single authoritative substrate for everything the assistant remembers across time horizons — from the current turn buffer through session summaries, durable user facts, artifacts Don has produced or referenced, learned behavior patterns, and (provisionally) the assistant's own state. L2 owns *storage, indexing, retrieval, provenance, and lifecycle* of memory. It does **not** own who is allowed to read or write memory (L5), which model handles a turn (L4), the live turn state machine (L1), persona assembly (L6), or presence/attention (L3).

Every read and every write must be gated by the L5 Policy Engine; privacy class propagates with every `MemoryHit` so downstream layers (router, persona compiler, UI) inherit the correct sensitivity envelope. L2's contract with L1 is hard: a memory query either returns within the deadline or returns empty — it never blocks the turn.

---

## 2. Primary Responsibilities

### 2.1 Owns — Six Memory Domains

1. **TurnMemory** — ephemeral per-turn scratch (inputs, tool calls, partial outputs). Flushed on `turn_end`.
2. **SessionMemory** — rolling summaries and salient spans for the current conversation/window.
3. **DurableUserMemory** — long-lived facts about Don (preferences, relationships, goals, identity).
4. **ArtifactMemory** — references to produced or attached artifacts (files, images, code, links) with content hashes + provenance.
5. **BehaviorMemory** — learned behavioral patterns (observed cadence, corrections, stylistic preferences, interaction feedback).
6. **AssistantStateMemory** *(provisional — see Open Questions §10)* — the assistant's own reflective state: prior commitments, unresolved TODOs toward Don, self-observations.

### 2.2 Owns — Pipelines

- **Ingestion pipeline** — candidate capture → dedup → salience scoring (uses L6 `CompiledSalience`) → privacy classification → L5 write-gate → persist → index (SQLite + vector).
- **Retrieval pipeline** — `MemoryQuery` → privacy scope resolution → candidate recall (lexical + vector) → rerank → L5 read-gate per hit → assemble `MemoryHit[]` within deadline.
- **Governance CRUD** — list, get, edit, delete (two-phase), export, retention policy mutation, review-provenance.
- **Provenance** — every item carries origin (turn id, source utterance hash, ingestion actor, L6 salience snapshot, L5 policy version at write).

### 2.3 Does NOT Own

- Policy decisions or capability grants → **L5**.
- Model/route selection and `confidence_summary` computation → **L4** (L2 only serves data into it).
- Turn state machine, deadlines, interruption semantics → **L1**.
- Persona text assembly, tone, system prompt synthesis → **L6**.
- Presence, attention, idle detection → **L3**.

---

## 3. Inbound Interfaces

| From | Message / Call | Purpose |
|---|---|---|
| **L1 Interaction Timing** | `MemoryQuery { query_id, scopes, filters, deadline_ms, budget_hits }` | Retrieve hits for the current turn; must respect deadline. |
| **L1 Interaction Timing** | `turn_end { turn_id, outcome }` | Flush TurnMemory ephemera; promote candidates to ingestion. |
| **L4 Model Router** | `confidence_summary_request { scopes, topic_vector }` | Read-only summary of what L2 knows on a topic (count, recency, confidence band) — NOT full hits. |
| **L5 Policy Engine** | `PolicyDecision { op_id, allow, redactions, privacy_class }` | Response to every L2-initiated policy gate check. |
| **L5 Policy Engine** | `GrantRevoked { capability, subject_scope }` | Invalidate cached grants; re-gate pending ops touching that scope. |
| **L5 Policy Engine** | `EmergencyRevokeAll { reason }` | Freeze all reads/writes, flush in-flight, enter safe mode. |
| **L6 Persona Compiler** | `CompiledSalience { rules_version, weights, topic_boosts }` | Update salience scoring used during ingestion and rerank. |
| **L7 Trust UX** | `memory_review_request { filter }` | List memories for the review pane. |
| **L7 Trust UX** | `memory_edit { item_id, patch }` | Edit a memory item. |
| **L7 Trust UX** | `memory_delete { item_id, mode: soft \| hard }` | Begin two-phase delete. |
| **L7 Trust UX** | `memory_export { scope, format }` | User-initiated data export. |

All inbound ops carry a `request_id` and are routed through L5 before any storage touch.

---

## 4. Outbound Interfaces (Events / Results)

| Event | When emitted | Consumers |
|---|---|---|
| `memory_hit { query_id, item_id, snippet, privacy_class, score, provenance_ref }` | During retrieval, per surviving hit | L1, L4, L6 |
| `memory_write_confirmed { candidate_id, item_id, domain, privacy_class }` | After async ingestion commits | L5 (audit), L7 (if surfaced) |
| `memory_edit_confirmed { item_id, version_before, version_after }` | After edit commit | L7 |
| `memory_delete_pending { item_id, grace_expires_at }` | On delete request accepted | L7, L5 audit |
| `memory_delete_committed { item_id, tombstone_id }` | After grace window elapses | L7, L5 audit |
| `memory_retention_expired { item_id, policy }` | Retention sweep | L5 audit |
| `provenance_update { item_id, chain_ref }` | Whenever provenance extended | L7 |
| `memory_export_completed { export_id, uri, format, item_count }` | Export finalization | L7 |
| `memory_index_rebuild_started { index_name, reason }` | Start of rebuild | L1 (for degraded-mode hinting), L7 |
| `memory_index_rebuild_completed { index_name, duration_ms, stats }` | End of rebuild | L1, L7 |
| `ingestion_candidate_rejected { candidate_id, reason }` | On gate denial or dedup drop | L5 audit |

Privacy class is stamped on every hit-bearing event. Events carry monotonic `seq` for ordered replay.

---

## 5. Synchronous vs Asynchronous Boundaries

| Op | Mode | Contract |
|---|---|---|
| `query` | **Synchronous, deadline-bound** | Must return `MemoryHit[]` or empty within `deadline_ms` (target 150 ms p95). Never blocks the turn — partial results allowed, marked `truncated: true`. |
| `confidence_summary` | Synchronous, fast | Non-hit metadata only; target < 50 ms. |
| `propose_write` | **Asynchronous** | Returns `candidate_id` immediately. Commit emits `memory_write_confirmed` or `ingestion_candidate_rejected`. |
| `edit` | Synchronous with async side effects | Returns new version; reindex happens async. |
| `delete` | **Two-phase** | Phase 1: `memory_delete_pending` (item hidden from new queries, grace window honors undo). Phase 2: `memory_delete_committed` (hard tombstone) after grace or on explicit force. |
| `export` | Asynchronous | Returns `export_id`, emits `memory_export_completed`. |
| `set_retention` | Synchronous metadata write | Takes effect on next retention sweep tick. |
| `subscribe` | Streaming | Event stream; backpressure via bounded channel. |

Invariant: **no synchronous path blocks on vector-index I/O beyond `deadline_ms`**. If vector store is degraded, L2 falls back to lexical + recency and sets `truncated: true`.

---

## 6. Typed Contract Suggestions (pseudo-Rust)

```rust
pub trait MemoryKernel {
    fn query(&self, q: MemoryQuery) -> Result<MemoryQueryResult, MemoryError>;
    fn confidence_summary(&self, req: ConfidenceSummaryRequest) -> Result<ConfidenceSummary, MemoryError>;
    fn propose_write(&self, cand: IngestionCandidate) -> Result<CandidateId, MemoryError>;
    fn edit(&self, item_id: ItemId, patch: MemoryPatch) -> Result<MemoryItem, MemoryError>;
    fn delete(&self, item_id: ItemId, mode: DeleteMode) -> Result<DeleteTicket, MemoryError>;
    fn export(&self, scope: ExportScope, fmt: ExportFormat) -> Result<ExportId, MemoryError>;
    fn list(&self, filter: MemoryFilter) -> Result<Vec<MemorySummary>, MemoryError>;
    fn get(&self, item_id: ItemId) -> Result<MemoryItem, MemoryError>;
    fn review_provenance(&self, item_id: ItemId) -> Result<ProvenanceChain, MemoryError>;
    fn set_retention(&self, scope: RetentionScope, policy: RetentionPolicy) -> Result<(), MemoryError>;
    fn subscribe(&self, topics: EventTopics) -> EventStream<MemoryEvent>;
}

pub trait EmbeddingStore {
    // Vendor-neutral; backing impl TBD (see Open Questions).
    fn upsert(&self, id: VectorId, vec: Embedding, meta: VectorMeta) -> Result<(), StoreError>;
    fn query(&self, vec: Embedding, k: usize, filter: VectorFilter) -> Result<Vec<VectorHit>, StoreError>;
    fn delete(&self, id: VectorId) -> Result<(), StoreError>;
    fn rebuild(&self, reason: RebuildReason) -> Result<RebuildHandle, StoreError>;
}

pub struct MemoryItem {
    pub id: ItemId,
    pub domain: MemoryDomain,
    pub privacy_class: PrivacyClass,
    pub content: MemoryContent,         // text, ref, structured payload
    pub summary: Option<String>,
    pub embedding_ref: Option<VectorId>,
    pub salience: f32,                  // computed from L6 CompiledSalience at write
    pub confidence: f32,
    pub created_at: Timestamp,
    pub updated_at: Timestamp,
    pub last_accessed_at: Option<Timestamp>,
    pub retention: RetentionPolicy,
    pub provenance: ProvenanceRef,
    pub version: u32,
    pub tombstoned: bool,
    pub tags: Vec<Tag>,
    pub links: Vec<ItemId>,             // inter-item references
}

pub struct MemoryQuery {
    pub query_id: QueryId,
    pub scopes: Vec<MemoryDomain>,
    pub text: Option<String>,
    pub topic_vector: Option<Embedding>,
    pub filters: MemoryFilter,
    pub budget_hits: u16,
    pub deadline_ms: u32,
    pub requester: RequesterId,         // L5 subject
}

pub struct MemoryHit {
    pub item_id: ItemId,
    pub domain: MemoryDomain,
    pub privacy_class: PrivacyClass,
    pub snippet: String,
    pub score: f32,
    pub confidence: f32,
    pub provenance_ref: ProvenanceRef,
    pub redactions_applied: Vec<RedactionTag>,
}

pub enum PrivacyClass {
    Public,
    Personal,
    Sensitive,
    Restricted,
    SelfReflective,                     // AssistantStateMemory default
}

pub enum MemoryDomain {
    Turn,
    Session,
    DurableUser,
    Artifact,
    Behavior,
    AssistantState,                     // provisional
}

pub enum RetentionPolicy {
    Ephemeral,                          // turn-scoped
    ShortTerm { ttl: Duration },
    LongTerm,
    UserPinned,
    LegalHold,
    ExpireOnEvent(EventKind),
}

pub enum DeleteMode { Soft, Hard, Force }
```

---

## 7. Error Vocabulary

```rust
pub enum MemoryError {
    RetrievalUnavailable { reason: String, degraded_mode: bool },
    PolicyDenied { op_id: OpId, capability: Capability, reason: String },
    CorruptIndex { index_name: String, detail: String },
    ConflictingMemories { item_ids: Vec<ItemId>, note: String },
    RetentionEngineFailed { phase: RetentionPhase, detail: String },
    VectorIndexRebuilding { eta_ms: Option<u32> },
    ExportFailed { export_id: ExportId, detail: String },
    ProvenanceChainBroken { item_id: ItemId, missing_link: LinkRef },
}
```

Every error carries enough context for L5 audit and L7 user surfacing. `PolicyDenied` must never leak *why* beyond what L5 has cleared for disclosure.

---

## 8. Dependency Expectations

- **L5 Policy Engine** — gates every `query`, `propose_write`, `edit`, `delete`, `export`, and provenance read. L2 holds a short-lived decision cache keyed by `(subject, capability, scope, policy_version)`; invalidated by `GrantRevoked` / `EmergencyRevokeAll`. **L2 MUST NEVER bypass L5**, including for internal housekeeping sweeps — retention and reindex operations carry a system-subject identity and go through L5 like any other caller.
- **L6 Persona Compiler** — supplies `CompiledSalience`; L2 treats it as cache-invalidating input for ingestion scoring and rerank weights.
- **Storage package** — SQLite for relational/provenance/metadata + a vector index behind the `EmbeddingStore` trait. Storage package owns migrations, WAL tuning, backup hooks.
- **No direct dependency** on L1 timing internals, L3 presence, L4 routing, or L7 UI code — L2 exposes contracts; consumers adapt.

---

## 9. Implementation Notes

- **Crate layout (per monorepo §2 in system design):**
  - `packages/l2-memory` (Rust) — authoritative kernel, trait `MemoryKernel` impl, ingestion/retrieval pipelines, retention scheduler.
  - `packages/l2-memory-ts` — TypeScript **read-only views** for renderer/UI (L7 review pane, onboarding). No write paths in TS; all mutations round-trip through Rust via Tauri command.
  - `packages/storage` — SQLite schema + migrations + `EmbeddingStore` trait + concrete vector adapter (vendor TBD).
- **Vector index** — behind `EmbeddingStore` trait so vendor can be swapped (candidates: local sqlite-vss / lancedb / qdrant-embedded). No consumer of L2 sees the vendor.
- **Privacy propagation** — `PrivacyClass` is stamped at write time from the ingestion classifier and L5 policy, re-asserted on every read, and travels on every outbound event.
- **Two-phase delete** — grace window configurable per `PrivacyClass`; `Restricted` and `LegalHold` ignore grace and commit immediately when policy permits, or refuse and emit `PolicyDenied`.
- **Observability** — every op emits a structured trace with `op_id`, `policy_version`, `latency_ms`, `deadline_met`, `truncated`.

---

## 10. Open Questions (flagged per constraints)

1. **Vector store vendor** — sqlite-vss vs lancedb vs qdrant-embedded. Decision deferred; `EmbeddingStore` trait isolates the choice. Need a benchmark pass on Don's corpus size + recall@k before locking.
2. **Embedding model per tier** — one model for all domains, or tiered (e.g. small/cheap for TurnMemory, larger for DurableUserMemory/ArtifactMemory)? Multi-model complicates reindex and cross-domain rerank; single-model simplifies but may underserve artifact retrieval. Needs empirical pass.
3. **AssistantStateMemory domain status** — provisional. Open questions: is self-reflective state a first-class L2 domain or does it belong to a separate L? What is its default `PrivacyClass` (`SelfReflective` assumed)? How does L5 gate the assistant reading its own prior commitments? Blocker before schema freeze.
4. **Contradiction ranking** — when retrieval surfaces conflicting memories (`ConflictingMemories`), what is the tiebreaker? Recency vs confidence vs provenance weight vs explicit user pin? Policy TBD; needs L6 + L7 input before lock.

---

*End of L2 Interface Pack — Draft 1.*
