---
status: draft
date: 2026-04-18
layer: L2 (companion memory kernel)
mode: system design (implementation-grade)
upstream:
  - 01_product_doctrine.md (§"Must-own layers" #2, §"Borrowable layers", §"Applied to evaluation")
  - MASTER_OUTLINE_TREE.md §7 memory architecture
  - plans/00_ORCHESTRATION_MAP.md §6–7 dependency DAG
  - plans/L2_memory_kernel.md (upstream plan this doc elaborates)
  - plans/L5_policy_engine_system_design.md (authoritative PolicyEngine trait, memory.* capabilities §2, events §4, commands §5, privacy-posture gate §10)
  - plans/L1_interaction_timing_system_design.md (MemoryQuery deadline contract, memory_hit consumption)
  - plans/L4_model_router_system_design.md (consumes confidence summary for routing)
  - plans/L7_trust_ux_onboarding_system_design.md (memory review / edit / export / delete UI)
  - plans/L6_persona_engine.md / plans/L6_persona_compiler.md (salience rules, PrivacyPosture)
  - plans/X3_tauri_architecture.md §2 (memory.* commands), §7 (filesystem scopes for audit log + SQLite)
  - 10_memory_architecture.md, 13_trust_security_redteam.md §5 (memory poisoning threats)
downstream_consumers:
  - L1 (issues MemoryQuery with deadline; consumes memory_hit)
  - L4 (consumes confidence_summary for tier + privacy routing)
  - L5 (gates every read/write/edit/delete/export; receives ActionRequests from L2)
  - L6 (salience_rules + PrivacyPosture feed into ranker; persona_swap rewires weights)
  - L7 (CRUD UI, review, export, forget flows)
scope_of_this_document:
  - Implementation blueprint for L2: domains, object model, ingestion, retrieval, governance, storage, interfaces, events, commands, failure modes, stubs
  - DDL pseudo-schema + pseudotypes + data-flow inside markdown only
  - Freezes the L2 contract that L1 / L4 / L6 / L7 stub against
non_goals:
  - Writing Rust crates, SQL DDL files, migrations, or tests (design only)
  - Picking the vector store vendor (borrowable, behind trait)
  - Picking the embedding model (borrowable, per-tier)
  - Owning policy decisions (L5), persona compilation (L6), artifact raw bytes (filesystem)
---

# L2 — Companion Memory Kernel — System Design

> The plan (file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel.md) says *what* L2 owns. This document says *how* L2 is built. Downstream layers (L1, L4, L6, L7) should stub against the contracts frozen here (§3, §5, §8, §9, §11, §15).
>
> Canonical planning root: file:///C:/Users/dbhav/Projects/aether-planning/
> Target package home (X1-dependent): file:///C:/Users/dbhav/Projects/aether/packages/l2-memory/ (Rust) + file:///C:/Users/dbhav/Projects/aether/packages/l2-memory-ts/ (typed bindings)
> Storage root (X3 §7): file:///C:/Users/dbhav/AppData/Local/Aether/core.data/memory/

---

## 1. Purpose and design stance

L2 is **not** "chat history + embeddings". It is a **selective, editable, governable memory kernel** whose first-class citizens are:

- **Provenance** — every memory carries the chain of sources it came from.
- **Confidence** — how sure L2 is that the content is accurate / current, with decay.
- **Recency** — monotonic timestamp of last reinforcement.
- **Salience** — persona-weighted importance score with a decay curve.
- **Privacy class** — a typed tag that propagates into every downstream payload.
- **Revocability** — the user can forget anything; forgetting cascades.
- **Retention policy** — per-item retention default; expiry is a first-class event.

**Design stance (doctrine-sourced):**

1. **Local-first canonical.** The authoritative memory store is on disk, single-writer, owned by the Rust core process (X3 §8.1). Remote sync (if present) is a projection, never the source of truth.
2. **L2 does not decide policy.** Every read and every write is a `policy.evaluate(ActionRequest)` call into L5. L2 asks; L5 answers. No memory operation is a silent bypass (`13 §"Red-team focus areas"` #5).
3. **User trust is non-negotiable.** Every memory is reviewable, editable, exportable, and forgettable. Every memory used in a turn is surfaced in the trust center (`01 §"Must-own layers"` #2).
4. **Privacy class follows content.** A `MemoryHit` carries its `privacy_class` across the layer boundary; L4 and L5 use it for the §10 privacy-posture gate without having to re-derive it.
5. **Contradictions are surfaced, never silently reconciled.** When two memories disagree, the provenance chain is shown to the user; L2 never picks a winner.
6. **Borrowable implementations sit behind traits.** The vector store, the embedding model, and the encryption backend are swappable. The object model, ingestion rules, ranker, and governance surfaces are custom.

---

## 2. Memory domains

L2 manages **six typed domains**. Each has distinct write policy, retention defaults, privacy-class defaults, and L5 capability mapping.

| # | Domain | Lifetime | Default privacy class | L5 write cap | L5 read cap | Hot in cache? |
|---|---|---|---|---|---|---|
| 1 | `TurnMemory` | ephemeral, scoped to current turn; flushed on `turn_end` per retention | `internal` | `MemoryWriteSession` | `MemoryRead` | always |
| 2 | `SessionMemory` | bounded rolling window within a session; decays to cold or promotion | `internal` | `MemoryWriteSession` | `MemoryRead` | always |
| 3 | `DurableUserMemory` | long-lived preferences, facts, relationships | `private` (user facts) or `public` (stated preferences, e.g. "I prefer terse answers") | `MemoryWriteDurable` | `MemoryRead` | tiered per §17 |
| 4 | `ArtifactMemory` | files, documents, captures the user attached; includes excerpts + summaries; raw bytes in filesystem, metadata in L2 | inherits from artifact (may be `sensitive-health`, `sensitive-financial`, `secret`) | `MemoryWriteDurable` + `FilesRead` (for the underlying file) | `MemoryRead` | on-demand |
| 5 | `BehaviorMemory` | observed style / preferences; requires user-confirmation to elevate beyond low-confidence | `private` (behavioral inference is sensitive) | `MemoryWriteExtractedPref` | `MemoryRead` | tiered |
| 6 | `AssistantStateMemory` | internal to the assistant: persona coherence, presence state, routing history | `internal` | `MemoryWriteSession` | `MemoryRead` (internal scope) | always |

**Notes:**

- `TurnMemory` vs `SessionMemory` are both session-scoped but differ in lifetime and observability. Turn memory is the reflex scratchpad L1 can populate and immediately read; session memory persists for the conversation.
- `AssistantStateMemory` is the only domain whose contents L7 **redacts by default** even under review mode — it is operationally internal, not user-facing content, and exposing raw values can leak model internals.
- `ArtifactMemory` always stores **metadata + summary + excerpts** in L2 and a **content-hash file reference** into `core.data`. L2 never holds raw artifact bytes in the SQLite row.

---

## 3. Memory object model — conceptual schema

```
MemoryItem {
  memory_id:            MemoryId,            // ULID
  domain:               MemoryDomain,        // enum of §2
  content_summary:      String,              // short, surface-safe summary (used in review UI)
  content_ref:          ContentRef,          // Inline(String) | BlobHash(Sha256) | ArtifactPath(PathId)
  source:               MemorySource,        // Turn(TurnId) | Artifact(PathId) | UserManual(UserEdit) | Observed(ObservationId)
  provenance_chain:     Vec<ProvenanceLink>, // ordered; each link is { source_id, source_layer, captured_at, trust_tag }
  confidence:           f32,                 // 0.0..=1.0
  confidence_model:     ConfidenceModel,     // how confidence was derived + decay curve
  recency_ts:           MonotonicTimestamp,  // last reinforcement
  created_ts:           MonotonicTimestamp,
  salience:             f32,                 // 0.0..=1.0, persona-weighted, decays per curve
  salience_curve:       SalienceCurve,       // decay parameters
  privacy_class:        PrivacyClass,        // see §13
  revocable:            bool,                // false ONLY for AssistantStateMemory system-required items
  retention_policy:     RetentionPolicy,     // Session | NDays(u32) | UntilUserRevokes | Indefinite
  linked_artifacts:     Vec<PathId>,         // references to files/blobs
  created_by:           CreatedBy,           // System | UserConfirmed | Observed(needs_confirm=true/false)
  last_accessed_ts:     Option<MonotonicTimestamp>,
  access_count:         u64,
  editable:             bool,                // false for AssistantStateMemory
  audit_trail_ref:      Vec<AuditId>,        // L5 audit IDs for every op touching this item
  tombstone:            Option<Tombstone>,   // soft-delete before hard delete
  schema_version:       u16,
}

PrivacyClass:
  public | private | internal | sensitive-health | sensitive-financial | secret

ConfidenceModel {
  derivation:           DerivationKind,      // UserConfirmed | RepeatedObservation | SingleObservation | Inferred
  base:                 f32,
  decay_halflife_days:  Option<f32>,         // None = no decay
  floor:                f32,                 // confidence cannot decay below this
}

SalienceCurve {
  base:                 f32,
  halflife_days:        f32,
  persona_weight_ref:   PersonaSalienceRuleId, // from L6
  access_boost:         f32,                   // each access bumps salience by this, capped
}

RetentionPolicy:
  Session | NDays(u32) | UntilUserRevokes | Indefinite

ProvenanceLink {
  source_id:            SourceId,
  source_layer:         SourceLayer,          // L1 | L2 (derivation) | L6 (persona) | Media | Core
  captured_at:          MonotonicTimestamp,
  trust_tag:            TrustTag,             // trusted | untrusted | scraped | user-stated
}

Tombstone {
  requested_at:         MonotonicTimestamp,
  grace_until:          MonotonicTimestamp,   // after grace, hard delete
  reason:               ForgetReason,
  audit_ref:            AuditId,
}
```

**Invariants:**

- `privacy_class` is mandatory on every item; there is no "unclassified" state.
- `provenance_chain` is non-empty for every `DurableUserMemory`, `ArtifactMemory`, and `BehaviorMemory`.
- `editable = false ⇒ user cannot patch content` but `revocable` may still be true (user can still forget).
- Content and provenance are edited via **separate** ops (see §14) so provenance-chain revocation doesn't rewrite content and vice-versa.

---

## 4. Ingestion pipeline

### 4.1 Inputs

- **Turn transcripts** — L1 publishes turn-final transcripts and classified intent; L2 inspects them for candidate memory writes.
- **User-confirmed saves** — user explicitly says "remember that" or clicks "save to memory" in L7.
- **Artifact ingests** — user attaches a file; the file is hashed, optionally chunked, summarized, and excerpts are proposed as `ArtifactMemory`.
- **Observed behavior signals** — style, pacing, rejection patterns, repeated phrasings; produced by an L2-internal behavior extractor.

### 4.2 Stages

```
[Capture]
  Candidate assembled with tentative domain + privacy-class + source
    |
    v
[Novelty filter]
  - Content hash dedup against existing items
  - Vector-similarity dedup against top-k neighbors above threshold T_dedup
  - If duplicate within a tolerance → reinforce (bump recency_ts, access_count, salience) instead of insert
  - If duplicate but contradictory → flag contradiction (see §14) and proceed as separate item
    |
    v
[Classification]
  - Domain assignment (rules + heuristics, deterministic)
  - Privacy-class assignment:
      * Inherit from source if ArtifactMemory
      * Persona PrivacyPosture narrows (Strict → defaults upgrade)
      * Content-type heuristics (health terms → sensitive-health, etc.)
  - Retention-policy selection from domain defaults
    |
    v
[Confidence assignment]
  - UserConfirmed → base=0.95
  - RepeatedObservation(n≥3) → base=0.8
  - SingleObservation → base=0.45
  - Inferred → base=0.3
  - Attach decay halflife per domain
    |
    v
[Salience weighting]
  - base from domain defaults
  - persona_weight_ref resolved via L6's compiled_persona.salience_rules
  - SalienceCurve parameters persisted with item
    |
    v
[Policy check — L5]
  - Construct ActionRequest {
      capability: <MemoryWriteSession | MemoryWriteDurable | MemoryWriteExtractedPref>,
      resource: MemoryScope(domain+privacy_class),
      provenance_tags: derived from provenance_chain,
      actor_persona: current,
    }
  - Call policy_engine.evaluate(req)
  - Outcomes:
      Allow       → proceed to persist
      Ask         → emit ingestion_candidate_held; wait on ApprovalResponse
      DraftOnly   → persist as draft (not retrievable by L1) awaiting user confirmation
      Deny        → emit ingestion_candidate_rejected { reason }; drop
      NeedsUpgrade → emit ingestion_candidate_rejected; surface in L7
    |
    v
[Persist]
  - Write memory_items row
  - Write memory_provenance rows
  - Queue embedding for EmbeddingStore (async; see §7.2)
  - Emit memory_write_confirmed { change_id, memory_id, domain, privacy_class }
```

### 4.3 User-confirmed vs auto-saved

| Path | Confidence base | Salience base | Retention default | L5 default posture |
|---|---|---|---|---|
| User-confirmed | 0.95 | high | UntilUserRevokes | auto-allow (MemoryWriteDurable=task) |
| Auto-saved (observed) | 0.30–0.45 | low | NDays(30) with re-confirm prompt | ask / task (MemoryWriteExtractedPref) |

Auto-saved items are subject to **reduced-salience retention**: if salience decays below a domain-specific floor before user confirmation, the item is auto-forgotten (not tombstoned — it never crossed the durability threshold).

### 4.4 Event emitted

`memory_write_confirmed { change_id, memory_id, domain, privacy_class, source_layer: L2, seq }` — projected to webview in summary form.

---

## 5. Retrieval pipeline

### 5.1 Inputs

```
MemoryQuery {
  turn_id:              TurnId,
  scope:                Vec<MemoryDomain> | MemoryScopeId,
  query_text:           String,
  query_embedding:      Option<Embedding>,   // pre-computed by caller when possible
  confidence_threshold: f32,                 // floor for returned hits
  k_max:                u32,                 // soft cap
  deadline_ms:          u32,                 // hard cap per L1's T_memory_deadline
  privacy_posture:      PrivacyPosture,      // from L6 via L1
  requester_layer:      SourceLayer,         // L1 | L4 | L7
  intended_route:       Option<RouteHint>,   // for L4's privacy-posture preview
}
```

### 5.2 Stages

```
[Scope filter]
  - Reject domains the caller isn't authorized to query (pre-L5 cheap check)
    |
    v
[Policy check — L5]
  - One ActionRequest per (domain, privacy_class) combination touched
  - capability: MemoryRead
  - resource: MemoryScope(domain+privacy_class)
  - Deny on any combo → drop that class from candidate set (retrieval continues)
  - Emit memory_access_denied audit reference per denied combo
    |
    v
[Candidate recall]
  - Lexical recall (FTS5 or equivalent over content_summary)
  - Vector recall (EmbeddingStore.query(query_embedding, k=k_lex_plus_vec))
  - Structured-index recall (keyed lookups: source_id, artifact_path, tag)
  - Merge into a candidate set with dedup by memory_id
    |
    v
[Rank]
  - score = w_recency * recency_norm
         + w_salience * salience_now (curve-evaluated)
         + w_confidence * confidence_now (decay-evaluated)
         + w_persona * persona_weight(item, persona_salience_rules)
         + w_lexical_or_vector_match
  - Weights come from L6 compiled_persona.salience_rules; fallback to system defaults
    |
    v
[Threshold filter]
  - Drop any hit where confidence_now < confidence_threshold
  - Drop any hit whose privacy_class is disallowed under the caller's privacy_posture
    (e.g. Strict posture on a route preview that would send to remote: strip private/sensitive)
    |
    v
[Return MemoryHit[]]
  - Hard-deadline: if time budget exhausted, return what's ranked so far
  - Must-respond-or-empty: caller MUST get a response within deadline_ms
  - Empty is valid
```

### 5.3 MemoryHit contract

```
MemoryHit {
  memory_id:           MemoryId,
  domain:              MemoryDomain,
  privacy_class:       PrivacyClass,          // propagates downstream
  content_summary:     String,                // redacted per privacy class + posture
  content_ref:         ContentRef,            // only dereferenceable via memory.get with L5 allow
  confidence_now:      f32,                   // decay-evaluated at query time
  salience_now:        f32,                   // curve-evaluated at query time
  recency_ts:          MonotonicTimestamp,
  provenance_summary:  ProvenanceSummary,     // redacted chain — counts + trust tags, not raw ids
  rank_score:          f32,
  contradiction_flag:  Option<ContradictionRef>, // points at conflicting memory(ies)
  audit_ref:           AuditId,               // the read audit record for this hit
}
```

**Rule:** L2 emits **`content_summary` across layer boundaries, never raw `content_ref` contents**, unless the caller's `ActionRequest` explicitly claimed `MemoryUseInFutureTask` or `MemoryExport` and L5 allowed. Raw content dereference is a second, gated round-trip.

### 5.4 Must-respond-or-empty contract with L1

- L1's `T_memory_deadline = 150 ms` (L1 §2.1 row `PartialASR` + §3).
- L2 guarantees: a response (possibly empty) before `deadline_ms` elapses.
- On internal stall (vector index rebuilding, SQLite contention, L5 slow), L2 returns **whatever is ready** plus a `partial=true` flag in `memory_hit`, and emits a `retrieval_deadline_exceeded` internal metric (not a user-visible event).

### 5.5 Event emitted

`memory_hit { turn_id, hits: Vec<MemoryHit-summary>, partial: bool, change_id, source_layer: L2, seq }` — projected to webview so L7's trust center can render "what memories influenced this turn".

---

## 6. Governance and trust

### 6.1 User flows (each is an L5-gated ActionRequest)

| Flow | L5 capability | Command (§11) | Events emitted |
|---|---|---|---|
| Review (list by domain+privacy+date) | `MemoryRead` | `memory.list` | none (read) |
| Get single item (full content) | `MemoryRead` + `MemoryUseInFutureTask` if crosses task boundary | `memory.get` | none |
| Edit content / salience / retention | `MemoryWriteDurable` or `MemoryWriteExtractedPref` | `memory.edit` | `memory_edit_confirmed` |
| Delete (soft, then hard after grace) | `MemoryDelete` | `memory.delete` | `memory_delete_pending`, later `memory_delete_committed` |
| Revoke provenance source | `MemoryDelete` (scoped to provenance subgraph) | `memory.review_provenance` + `memory.edit` patch | `provenance_update` + possible `memory_edit_confirmed` for downstream re-weighted items |
| Export bundle | `MemoryExport` | `memory.export` | `memory_export_completed` |
| Set retention | `MemoryWriteDurable` | `memory.set_retention` | `memory_edit_confirmed` |

### 6.2 Retention engine

- Background job (Rust core, single-writer) runs every `T_retention_tick` (default 5 min).
- For each item whose `retention_policy` expires at or before now, emit `memory_retention_expired { memory_id, domain, privacy_class }`, soft-delete (write tombstone), and schedule hard-delete after grace.
- **Never surfaces expired content as current.** Retrieval filters on `tombstone.is_none()`.
- Failure handling: see §12.

### 6.3 Forgetting

- **Soft delete** writes a `Tombstone` row + `memory_delete_pending` event. Content remains readable *only* by the review UI under `MemoryRead + forget-review-window` for the grace period so user can undo.
- **Hard delete** after grace:
  - Removes the content blob (if inline) and the `memory_items` row contents (keeps the row as a tombstone-only record for audit cross-reference).
  - Removes the embedding vector from `EmbeddingStore`.
  - Invalidates any cache / snapshot / sync delta referring to the content.
  - Emits `memory_delete_committed { memory_id, audit_ref }`.
- **Audit preserved:** the L5 audit log keeps the cryptographic record of the delete forever (hash-chained, tamper-evident per L5 §8). The **content is gone**, the **fact of its deletion is not**.

### 6.4 Export

- `memory.export` is High-risk (L5 §2.2 `MemoryExport`).
- Produces a **signed export bundle** (manifest + JSONL of items + sidecar of provenance + sidecar of privacy-class tags). Signature uses the same key handling as L5 §8 audit-log HMAC.
- Destination path is subject to `FilesCreate` + filesystem scope gate per X3 §7.
- Emits `memory_export_completed { bundle_path, scope_summary, audit_ref }`.

### 6.5 L5 integration summary

Every memory op — read, write, edit, delete, export — **is** an `ActionRequest` to L5. L2 holds `Arc<dyn PolicyEngine>` (L5 §12.1) and never calls executors directly. A CI lint (mirroring L5's `tools/lint-policy-bypass`) rejects any code path in L2 that writes to `memory_items` without going through the gated `write_gated()` helper.

---

## 7. Storage architecture (planning level)

### 7.1 SQLite table sketch (pseudo-DDL)

```
-- Primary item table
TABLE memory_items (
  memory_id              BLOB PRIMARY KEY,    -- 16B ULID
  domain                 TEXT NOT NULL,       -- enum
  privacy_class          TEXT NOT NULL,       -- enum
  content_summary        TEXT NOT NULL,
  content_ref_kind       TEXT NOT NULL,       -- 'inline' | 'blob' | 'artifact'
  content_inline         BLOB NULL,           -- encrypted inline content
  content_blob_hash      BLOB NULL,           -- sha256 → core.data/blobs/<hash>
  artifact_path_id       BLOB NULL,           -- FK to artifact table
  confidence             REAL NOT NULL,
  confidence_model       BLOB NOT NULL,       -- serialized ConfidenceModel
  recency_ts_mono        INTEGER NOT NULL,
  created_ts_mono        INTEGER NOT NULL,
  salience               REAL NOT NULL,
  salience_curve         BLOB NOT NULL,
  retention_policy       BLOB NOT NULL,
  created_by             TEXT NOT NULL,
  editable               INTEGER NOT NULL,
  revocable              INTEGER NOT NULL,
  last_accessed_ts_mono  INTEGER NULL,
  access_count           INTEGER NOT NULL DEFAULT 0,
  tombstone_ref          BLOB NULL,           -- FK to memory_tombstones
  schema_version         INTEGER NOT NULL
);
INDEX idx_items_domain_privacy ON memory_items(domain, privacy_class);
INDEX idx_items_recency         ON memory_items(recency_ts_mono);
FTS5 VIRTUAL TABLE memory_items_fts (content_summary);

-- Provenance — separate table so chain edits don't rewrite content
TABLE memory_provenance (
  provenance_id     BLOB PRIMARY KEY,
  memory_id         BLOB NOT NULL REFERENCES memory_items(memory_id),
  order_idx         INTEGER NOT NULL,         -- chain position
  source_id         BLOB NOT NULL,
  source_layer      TEXT NOT NULL,
  captured_at_mono  INTEGER NOT NULL,
  trust_tag         TEXT NOT NULL,
  UNIQUE(memory_id, order_idx)
);
INDEX idx_prov_source ON memory_provenance(source_id);

-- Tags (privacy + domain + user labels)
TABLE memory_tags (
  memory_id  BLOB NOT NULL REFERENCES memory_items(memory_id),
  tag_kind   TEXT NOT NULL,                   -- 'privacy' | 'domain' | 'user_label'
  tag_value  TEXT NOT NULL,
  PRIMARY KEY (memory_id, tag_kind, tag_value)
);

-- Retention schedule
TABLE memory_retention (
  memory_id        BLOB PRIMARY KEY REFERENCES memory_items(memory_id),
  policy_kind      TEXT NOT NULL,
  expires_at_mono  INTEGER NULL,              -- NULL = indefinite / until-revoke
  last_checked_at  INTEGER NULL
);
INDEX idx_retention_expires ON memory_retention(expires_at_mono);

-- Tombstones (soft-delete + audit anchor)
TABLE memory_tombstones (
  tombstone_id      BLOB PRIMARY KEY,
  memory_id         BLOB NOT NULL REFERENCES memory_items(memory_id),
  requested_at_mono INTEGER NOT NULL,
  grace_until_mono  INTEGER NOT NULL,
  reason            TEXT NOT NULL,
  hard_deleted_at   INTEGER NULL,
  audit_ref         BLOB NOT NULL
);
INDEX idx_tomb_grace ON memory_tombstones(grace_until_mono);

-- Embedding store reference (the vector itself lives in the EmbeddingStore impl)
TABLE memory_embeddings_ref (
  memory_id         BLOB PRIMARY KEY REFERENCES memory_items(memory_id),
  embedding_model   TEXT NOT NULL,            -- e.g. 'bge-m3', 'bge-small-lite'
  embedding_dims    INTEGER NOT NULL,
  vector_ref        BLOB NOT NULL,            -- opaque ref (store-specific id)
  indexed_at_mono   INTEGER NOT NULL,
  stale             INTEGER NOT NULL DEFAULT 0 -- 1 when content edited since last index
);
INDEX idx_emb_stale ON memory_embeddings_ref(stale);
```

### 7.2 Vector index — `EmbeddingStore` trait

```
trait EmbeddingStore {
  fn upsert(id: MemoryId, vec: Embedding) -> Result<(), EmbeddingStoreError>;
  fn delete(id: MemoryId) -> Result<(), EmbeddingStoreError>;
  fn query(vec: Embedding, k: u32, filter: Option<VectorFilter>) -> Result<Vec<VectorHit>, EmbeddingStoreError>;
  fn rebuild(from_iter: impl Iterator<Item = (MemoryId, Embedding)>) -> Result<RebuildReceipt, EmbeddingStoreError>;
  fn health() -> EmbeddingStoreHealth;
}
```

Vendor-neutral: L2 does not pick between hnswlib-rs, usearch, LanceDB-embedded, Qdrant-embedded, or a custom HNSW. The borrowable decision is deferred to integration (tracked in §19 open questions; the upstream plan notes Chroma / LanceDB / Qdrant-embedded as candidates).

### 7.3 Encryption at rest

- SQLite encrypted via **SQLCipher** or `libsql` with an encryption at rest plugin (align with L5 §8 key handling — same keyring, same re-auth flow for master-key unlock).
- **Artifact blobs** stored under `core.data/blobs/<sha256>` with per-file encryption keys derived from the master key + item salt.
- **EmbeddingStore** — if the chosen backend doesn't support at-rest encryption natively, L2 wraps it with a filesystem-level encrypted volume; alternatively, vectors are stored in SQLCipher (acceptable for smaller k).

### 7.4 Single-writer rule

- One Rust process owns every SQLite handle, every EmbeddingStore handle, every blob-writer (X3 §8.1 + `tauri-plugin-single-instance`).
- Read replicas are allowed but never outside the Rust core process.
- The webview never touches disk.

### 7.5 Artifact blob storage

- Raw artifact bytes land in `core.data/blobs/<sha256>`; `memory_items.content_blob_hash` references them.
- Excerpts and summaries live as `content_inline` or separate summary rows.
- Delete of an `ArtifactMemory` **does not** delete the raw artifact file (that's filesystem scope, gated by `FilesDelete`); it only removes the memory row + embedding + tombstones the linkage.

---

## 8. Interfaces (typed pseudotype)

### 8.1 To L1 — must-respond-or-empty within deadline

```
fn memory.query(req: MemoryQuery) -> Vec<MemoryHit>
  // Contract:
  //   * Returns within req.deadline_ms (hard cap). Empty is valid.
  //   * Every MemoryHit carries privacy_class.
  //   * Rank respects persona salience rules if CompiledPersona available.
  //   * Denied domains produce no hits + an audit trail entry (not an error).
```

### 8.2 To L4 — routing confidence summary

```
fn memory.confidence_summary(turn_id: TurnId) -> ConfidenceSummary {
  domain_coverage:   HashMap<MemoryDomain, DomainCoverage>,
  privacy_tags:      HashSet<PrivacyClass>,    // union across hits surfaced this turn
  max_confidence:    f32,
  min_confidence:    f32,
  hit_count:         u32,
  contradiction_flags: u32,
}
```

L4 uses `privacy_tags` for §10 privacy-posture preview; `max_confidence` to upshift/downshift tier confidence; `contradiction_flags` to decide whether a deliberative tier with explain-capability is preferred.

### 8.3 To L6 — subscribes to persona lifecycle

- **Subscribes to** `compiled_persona_ready { persona_id, salience_rules, privacy_posture }` — L2 re-weights future rankings using these rules.
- **Subscribes to** `persona_swap_commit { from, to }` — L2 recomputes salience for **hot** items only (cold items re-rank on next access) and emits `memory_index_rebuild_started` / `memory_index_rebuild_completed` if the swap invalidates a large slice.

### 8.4 To L7 — full CRUD + review

- `memory.list(scope, filter) -> Vec<MemorySummary>`
- `memory.get(memory_id) -> MemoryDetail` (raw content dereference; L5-gated)
- `memory.propose_write(draft) -> WriteProposal`
- `memory.edit(memory_id, patch) -> ()`
- `memory.delete(memory_id, reason) -> ()`
- `memory.export(scope, format) -> Uri`
- `memory.review_provenance(memory_id) -> ProvenanceChain`
- `memory.get_retention(memory_id) -> RetentionPolicy`
- `memory.set_retention(memory_id, policy) -> ()`

### 8.5 From L5 — decisions gate every op

- **Subscribes to** `policy_decision { request_id, decision }` — unblocks pending memory ops keyed by `request_id`.
- **Subscribes to** `grant_revoked { grant_id }` — invalidates in-flight queries that relied on that grant; drops the corresponding hits.
- **Subscribes to** `emergency_revoke_all { scope }` — aborts all in-flight queries, cancels pending writes (except already-committed audit records), and emits `memory_index_rebuild_started` only if the scope demands re-indexing (rare).

---

## 9. Event contracts emitted

Every event carries `change_id: ChangeId`, `source_layer: L2`, `seq: Seq`. Projection column follows X3 §3.2 + L5 §4.2 conventions.

| Event | Fields | Emitter | Subscribers | Idempotency | Projected? |
|---|---|---|---|---|---|
| `memory_hit` | `turn_id`, `hits: Vec<MemoryHitSummary>`, `partial: bool`, `requester_layer` | L2 | L1, L4, L7 | Per `(turn_id, requester_layer)`; last wins within turn | **Yes** (summary only; redacted per privacy class) |
| `memory_write_confirmed` | `memory_id`, `domain`, `privacy_class`, `created_by`, `audit_ref` | L2 | L7, L1 | `memory_id` unique | **Yes** |
| `memory_edit_confirmed` | `memory_id`, `patch_kind: EditKind` (content|salience|retention|provenance), `audit_ref` | L2 | L7, L1 | Latest `audit_ref` wins per memory_id | **Yes** |
| `memory_delete_pending` | `memory_id`, `grace_until`, `reason`, `audit_ref` | L2 | L7, L1 | Once per soft-delete | **Yes** |
| `memory_delete_committed` | `memory_id`, `audit_ref` | L2 | L7 | Once per hard-delete | **Yes** |
| `memory_retention_expired` | `memory_id`, `domain`, `privacy_class`, `audit_ref` | L2 (retention engine) | L7 | Once per expiry | **Yes** |
| `provenance_update` | `memory_id`, `chain_delta: ProvenanceDelta`, `affected_confidence_delta: f32`, `audit_ref` | L2 | L7, L1 | Monotonic per memory_id | **Yes** |
| `memory_export_completed` | `bundle_path`, `scope_summary`, `item_count`, `audit_ref` | L2 | L7 | Per export request | **Yes** |
| `memory_index_rebuild_started` | `scope`, `estimated_items` | L2 | L7 (degraded banner), L1 (fallback to lexical-only) | One in-flight per scope | **Yes** |
| `memory_index_rebuild_completed` | `scope`, `duration_ms`, `item_count` | L2 | L7, L1 | Pairs with `started` | **Yes** |
| `ingestion_candidate_rejected` | `candidate_ref`, `reason: RejectReason` (novelty_dup | policy_deny | low_confidence | privacy_violation) | L2 | L7 (optional counters) | Per candidate | **No** (internal; counter projected) |

---

## 10. Events subscribed to

| Event | Source | L2 action |
|---|---|---|
| `policy_decision` | L5 | Unblock the memory op keyed by `request_id`; on `Deny`, emit `ingestion_candidate_rejected` or return empty hit set |
| `grant_revoked` | L5 | Invalidate any in-flight query that held the grant; future queries re-evaluate |
| `emergency_revoke_all` | L5 | Abort in-flight queries; cancel pending writes not yet audited; retention engine pauses until recovery |
| `compiled_persona_ready` | L6 | Re-weight ranker; update hot cache |
| `persona_swap_commit` | L6 | Re-rank hot items; emit `memory_index_rebuild_*` if salience topology changed |
| `turn_end` | L1 | Flush ephemeral `TurnMemory` per its retention policy; persist any `SessionMemory` accumulated in the turn |

---

## 11. Tauri IPC commands (align with X3 §2.2)

All commands are `#[tauri::command]` in Rust with typed request/response, follow the L5 §5 failure-vocab pattern, and return a `ChangeId` for write-class ops.

```
# Shared error envelope
MemoryIpcError =
  Degraded(DegradedMode)        // AuditBroken | SafeMode | IndexRebuilding | RetentionPaused | Corrupt
  | NotFound(String)
  | Invalid(String)
  | PolicyDenied(DenyReason)    // forwarded from L5
  | DeadlineExceeded
  | Internal(String)
```

| Command | Request | Response | Failure vocab | Side effects | Capability-gated? |
|---|---|---|---|---|---|
| `memory.query` | `MemoryQuery` | `QueryResult { hits: Vec<MemoryHit>, partial: bool, change_id }` | `Degraded`, `DeadlineExceeded`, `Invalid` | Emits `memory_hit`; writes L5 read audits | **Yes** — each (domain, privacy_class) combo → `MemoryRead` |
| `memory.list` | `ListRequest { scope, filter, cursor, page_size }` | `ListPage { items: Vec<MemorySummary>, next_cursor, change_id }` | `Degraded`, `Invalid`, `PolicyDenied` | Read-only; L5 audit entries per domain touched | **Yes** — `MemoryRead` |
| `memory.get` | `memory_id` | `MemoryDetail { full fields, dereferenced content }` | `NotFound`, `PolicyDenied`, `Degraded` | Bumps `access_count`, `last_accessed_ts`; L5 audit | **Yes** — `MemoryRead` (+ `MemoryUseInFutureTask` if crossing task) |
| `memory.propose_write` | `WriteDraft { domain, content, source, suggested_privacy_class, suggested_retention }` | `WriteProposal { proposal_id, requires_approval: bool, change_id }` | `PolicyDenied`, `Invalid`, `Degraded` | Runs ingestion pipeline up to persist stage; emits `memory_write_confirmed` on Allow | **Yes** — `MemoryWriteSession` / `MemoryWriteDurable` / `MemoryWriteExtractedPref` per domain |
| `memory.edit` | `EditRequest { memory_id, patch: EditPatch }` where EditPatch = ContentPatch | SaliencePatch | RetentionPatch | ProvenancePatch | `EditReceipt { change_id }` | `NotFound`, `PolicyDenied`, `Invalid`, `Degraded` | Writes new row revision semantics (content mutation is an audited update); emits `memory_edit_confirmed` and/or `provenance_update` | **Yes** — `MemoryWriteDurable` (+ `MemoryDelete` if patch removes provenance links) |
| `memory.delete` | `memory_id`, `reason: ForgetReason`, `grace_override: Option<Duration>` | `DeleteReceipt { change_id, grace_until }` | `NotFound`, `PolicyDenied`, `Degraded` | Soft delete now; hard delete after grace; emits `memory_delete_pending` then `memory_delete_committed` | **Yes** — `MemoryDelete` |
| `memory.export` | `ExportRequest { scope, format, destination }` | `ExportReceipt { bundle_path, change_id }` | `PolicyDenied`, `Invalid`, `Degraded` | Writes signed bundle; emits `memory_export_completed` | **Yes** — `MemoryExport` (+ `FilesCreate` on destination) |
| `memory.review_provenance` | `memory_id` | `ProvenanceChain { links: Vec<ProvenanceLink>, impact_analysis: Vec<DownstreamImpact> }` | `NotFound`, `PolicyDenied`, `Degraded` | Read-only | **Yes** — `MemoryRead` |
| `memory.set_retention` | `memory_id`, `policy: RetentionPolicy` | `RetentionReceipt { change_id }` | `NotFound`, `PolicyDenied`, `Invalid`, `Degraded` | Writes `memory_retention` row; emits `memory_edit_confirmed { patch_kind: retention }` | **Yes** — `MemoryWriteDurable` |
| `memory.get_retention` | `memory_id` | `RetentionPolicy` | `NotFound`, `PolicyDenied` | Read-only | **Yes** — `MemoryRead` |
| `memory.subscribe` | `EventFilter` | `EventStream<L2Event>` | `Degraded` | Stream | No (stream of already-projected events) |

---

## 12. Failure modes and degraded operation

| Failure class | Detection | Degraded behavior | Exit path | User-visible surface |
|---|---|---|---|---|
| Retrieval unavailable (SQLite contention, deadlock) | `memory.query` exceeds deadline | Empty result + `partial=true`; turn tagged `no-memory`; L1 proceeds without memory; L4 treats `confidence_summary` as all-zero | Next successful query | L1 emits `turn_state_change{DegradedNoMemory}` (L1 §2.1 row 17) |
| Low-confidence retrieval | All surviving hits < caller's `confidence_threshold` | Return what's ranked + `low_confidence_flag` on each hit; L1 / L4 downshift trust | N/A — design-expected | Trust center shows "low-confidence recall used this turn" |
| Corrupt SQLite | Integrity check on boot / per-write failure | `DegradedMode::Corrupt`; L2 enters **read-only recovery**: serves from last-known-good snapshot; no writes, no retention ticks | User-confirmed rebuild from audit log + artifact replay | L7 degraded-mode banner with "Rebuild memory from audit log" action |
| Conflicting memories (contradictory facts) | Novelty filter detects semantic overlap with opposing polarity | Store both; attach `ContradictionRef` each way; surface in `MemoryHit.contradiction_flag`; **no auto-resolution** | User edits / forgets one via L7 | L7 review UI shows conflict badge; L1 emits turn-level `contradiction_flag` for L3 to render |
| Policy-denied read | L5 returns `Deny` | Drop the denied (domain, privacy_class) slice; return remaining hits; emit `memory_access_denied` audit cross-ref | Next query (possibly with upgraded preset) | None by default — visible only in trust center audit |
| Vector index rebuild in progress | `EmbeddingStore.health() != Ready` | **Lexical-only retrieval fallback**; `memory_hit.partial=true`; emit `memory_index_rebuild_started` if not already | `memory_index_rebuild_completed` | L7 banner "memory index rebuilding" |
| Retention engine failure | Tick fails; job queue stalls | Expired items **remain** until next successful tick, but retrieval **never surfaces them as current** (filter-on-read uses `expires_at_mono <= now`); `DegradedMode::RetentionPaused` flag | Next successful tick | L7 banner "retention paused — forgetting delayed" |
| Provenance rewrite mid-read | Concurrent `memory.edit` with ProvenancePatch while a read is in-flight | Reader uses chain snapshot captured at query start; returned hit carries `provenance_snapshot_at` | N/A | None |
| Audit-log write failure (upstream of L5) | L5 returns `Deny { AuditWriteFailed }` | L2 **deny-all**: refuses all reads and writes until L5 recovers; emits `ingestion_candidate_rejected` for any in-flight candidate | L5 recovery | L7 shows L5's "Aether is paused" banner |
| EmbeddingStore corruption | Store health check fails | Enter lexical-only mode; schedule full rebuild from `memory_items` + re-embedding | Rebuild completes | L7 banner |
| Master-key unavailable (SQLCipher) | Boot-time decrypt failure | `DegradedMode::Corrupt`; only non-encrypted metadata (if any) readable — effectively L2 offline | User re-auth / key recovery | L7 hard-blocking banner |

---

## 13. Privacy-class propagation rules

1. **Every MemoryHit carries `privacy_class`.** Non-negotiable. Callers cannot strip it; serialization schemas reject `MemoryHit` without it.
2. **L4 routing constraint.** L4 MUST NOT include `private`, `sensitive-health`, `sensitive-financial`, or `secret` hits in prompts routed to a remote tier unless the actor persona holds an active `RouterAllowRemoteWithPrivate` grant scoped to that provider (L5 §10.4). L2 enforces this by **pre-filtering** on any query that arrives with `intended_route = RemoteEscalation { provider }` and no such grant in the snapshot: private+sensitive hits are dropped from the return and an `ingestion_candidate_rejected`-style audit note (`retrieval_privacy_stripped`) is recorded.
3. **L7 review UI redaction.** `private`, `sensitive-*`, and `secret` content is **redacted by default** in the review UI; unmasking requires re-auth (same path as L5 `policy.set_preset` re-auth, X3 §2.2).
4. **Exports preserve tags.** Every exported item ships with its `privacy_class`; bundle manifests include a per-class item count. `secret` class is **never** exported unless the user confirms per-item (L7 flow) and holds an explicit `MemoryExport` grant with `include_secret = true` waiver (tracked as an extension to L5 `MemoryExport`).
5. **`internal` class never crosses a remote boundary.** `AssistantStateMemory` and other internal items are hard-blocked from remote routing under all grants (evaluated in L5 §10 pre-evaluator, analogous to hardcoded block).
6. **Privacy class is sticky under edit.** `memory.edit` cannot narrow the privacy class (e.g. `private → public`) without an explicit `ReclassifyPatch` op that L5 treats as High-risk and that audits the old and new class.

---

## 14. Provenance and audit integration

### 14.1 Audit integration

- Every memory op appears in L5's audit log via the `policy.evaluate` + post-op `audit_record` flow.
- L2's `memory_items.audit_trail_ref` keeps a **pointer list** to every `AuditId` that touched the item; retrieval UI can query L5 for the full chain via `policy.explain_decision(audit_id)`.
- Write operations: the `audit_record` references the `change_id` emitted by the write command, creating a bi-directional link.

### 14.2 Provenance independence

- `memory_provenance` is a separate table from `memory_items`.
- **Chain edits are independent of content edits.** Revoking a provenance source (user says "forget that you learned this from X") does **not** rewrite content; it removes links and triggers re-weighting.
- Content edits do not rewrite provenance; they produce a new `ProvenanceLink` with `trust_tag = user-stated` appended.

### 14.3 Forgetting a provenance source (cascade)

When user revokes source `S`:

1. Find all `memory_provenance` rows with `source_id = S`; collect affected `memory_id`s.
2. For each affected memory, remove the link (append a `provenance_update` event with `chain_delta = Removed(S)`).
3. Recompute confidence: `new_confidence = confidence_model.recompute(remaining_chain)`.
4. If `new_confidence < threshold_flag_for_review` (default 0.3), mark the memory with a `user_review_recommended` flag and emit `provenance_update { affected_confidence_delta, user_review_recommended: true }`.
5. If user additionally elected "delete memories derived from S" in the L7 flow, cascade `memory.delete` on each affected memory (each delete is its own L5 `ActionRequest`).

---

## 15. Stub interfaces (unblock L1 / L4 / L6 / L7 against L2)

Downstream layers freeze against these shapes.

### 15.1 Rust trait — the single L2 entry point

```rust
pub trait MemoryKernel: Send + Sync {
    fn query(&self, req: MemoryQuery) -> Result<QueryResult, MemoryError>;
    fn confidence_summary(&self, turn_id: TurnId) -> Result<ConfidenceSummary, MemoryError>;
    fn propose_write(&self, draft: WriteDraft) -> Result<WriteProposal, MemoryError>;
    fn edit(&self, memory_id: MemoryId, patch: EditPatch) -> Result<EditReceipt, MemoryError>;
    fn delete(&self, memory_id: MemoryId, reason: ForgetReason) -> Result<DeleteReceipt, MemoryError>;
    fn export(&self, req: ExportRequest) -> Result<ExportReceipt, MemoryError>;
    fn list(&self, req: ListRequest) -> Result<ListPage, MemoryError>;
    fn get(&self, memory_id: MemoryId) -> Result<MemoryDetail, MemoryError>;
    fn review_provenance(&self, memory_id: MemoryId) -> Result<ProvenanceChain, MemoryError>;
    fn set_retention(&self, memory_id: MemoryId, policy: RetentionPolicy) -> Result<RetentionReceipt, MemoryError>;
    fn subscribe(&self, filter: EventFilter) -> EventStream<L2Event>;
}

#[derive(thiserror::Error, Debug)]
pub enum MemoryError {
    #[error("degraded mode: {0:?}")] Degraded(DegradedMode),
    #[error("policy denied: {0:?}")] PolicyDenied(DenyReason),
    #[error("not found")] NotFound,
    #[error("invalid: {0}")] Invalid(String),
    #[error("deadline exceeded")] DeadlineExceeded,
    #[error("bus closed")] BusClosed,
    #[error("internal: {0}")] Internal(String),
}
```

### 15.2 Consumed trait — PolicyAdapter (defined by L5, §12.1)

L2 holds `Arc<dyn PolicyEngine>` and calls `evaluate`, `subscribe`, `snapshot_grants`. L2 does **not** re-define these — it imports them.

### 15.3 What each downstream stubs against

- **L1** — `memory.query` with deadline + `memory_hit` event; `confidence_summary` for turn-local reasoning is optional but available.
- **L4** — `memory.confidence_summary(turn_id)` + subscription to `memory_hit` (for `privacy_tags` in route preview).
- **L6** — contract that L2 **subscribes** to `compiled_persona_ready` and `persona_swap_commit`; L6 stubs by emitting these events with `salience_rules` and `privacy_posture` shapes.
- **L7** — full CRUD commands (§11) + event stream; L7 stubs against the commands returning mock data until L2 ships.

---

## 16. Testing strategy (design level)

### 16.1 Property tests

- **Retrieval respects policy denies.** Random (domain, privacy_class, preset) combos → assert no hit returned when L5 would deny.
- **Delete is idempotent.** `delete(m)` then `delete(m)` → second call returns `NotFound` (or no-op), no double-audit, no exception.
- **Retention never surfaces expired.** Generate items with random expiries; advance clock; retrieval never returns any item with `expires_at_mono <= now`.
- **Novelty filter is deterministic.** Same candidate + same existing set → same dedup verdict.
- **Privacy class stickiness.** No sequence of non-reclassify edits can change `privacy_class`.
- **Provenance cascade correctness.** Revoking source S and re-running confidence recompute produces the same result regardless of order.

### 16.2 Red-team (from `13 §5`)

- **Memory poisoning** — inject false provenance (untrusted scraped content posing as user-stated). Assert: trust_tag is preserved; ranker down-weights untrusted; L4 privacy-posture gate treats untrusted + private as poisoned.
- **Privacy leak** — attempt retrieval under wrong posture (Strict posture, remote route). Assert: private/sensitive hits stripped; audit cross-ref written.
- **Export exfiltration** — craft an export request that tries to escape `MemoryScope`. Assert: L5 `MemoryExport` denies; no partial bundle written.
- **Inference-time prompt injection via retrieved content** — retrieved content contains adversarial instructions. Assert: content passed with `trust_tag = untrusted`; L4 / cognition treat untrusted content as data, not instructions.
- **Forgetting that doesn't forget** — delete item; assert embedding, blob, cache, sync delta all purged after grace; only audit record remains.

### 16.3 Load tests

- **P95 < 150 ms** for `memory.query` at N=10k items, mixed domains, with lexical + vector recall.
- **Retention tick < 500 ms** at N=10k items with 1% expiring.
- **Ingestion throughput** — 100 candidates/sec under novelty-filter + L5 evaluate (L5 itself is bounded; L2's overhead should be <10 ms per candidate).

### 16.4 Replay tests

- **Audit-log + retention log reconstruct current state.** Wipe `memory_items`; replay L5 audit events of type `memory.*` and retention-log records; assert final state matches pre-wipe snapshot (content may be missing for hard-deleted items — but tombstones and structural state reconstruct exactly).

---

## 17. Tier awareness

| Tier | Vector index | Domains hot in cache | Embedding dims | k_max default | Retention windows |
|---|---|---|---|---|---|
| Lite | Smaller HNSW (M=8, efSearch=32); may use a **smaller embedding** (e.g. bge-small, 384d) | Turn + Session + DurableUser only; Artifact + Behavior on-demand | 384 | 8 | Shortened: `NDays(14)` default for auto-saved |
| Balanced | Standard HNSW (M=16, efSearch=64); bge-m3 or equivalent | All domains; hot cache for recency top-1000 | 768 | 20 | Standard: `NDays(30)` |
| Full | Larger HNSW (M=32, efSearch=128); optionally cross-encoder re-rank stage | All domains; hot cache for recency top-10000 | 1024 | 50 | Longer: `NDays(90)` default for auto-saved; offer `Indefinite` easily |

Per-tier settings are compiled into the `EmbeddingStore` config at boot; a tier change triggers `memory_index_rebuild_started` + `completed`.

---

## 18. Deliverables summary (what an implementer builds first)

1. **SQLite DDL** for `memory_items` + `memory_provenance` (+ minimal `memory_tombstones`, `memory_retention`, `memory_embeddings_ref`). §7.1.
2. **`MemoryKernel` trait** + typed `MemoryQuery` / `MemoryHit` / `ConfidenceSummary`. §15.1, §5.1, §5.3, §8.2.
3. **Ingestion pipeline** with novelty filter (hash + vector-similarity dedup) and classification. §4.
4. **Retrieval pipeline** with L5 policy gate + lexical + vector recall + ranker + threshold filter. §5.
5. **`EmbeddingStore` trait** (vendor-neutral). §7.2.
6. **Governance CRUD commands** (Tauri) + event emission. §11, §9.
7. **Privacy-class propagation** plumbed end-to-end (MemoryHit → L4 → L5 gate). §13.
8. **Retention engine** (background job) + `memory_retention_expired` emission. §6.2.
9. **Provenance independence** (separate table + cascade logic). §14.

Out of P0 scope (deferred per upstream `L2_memory_kernel.md §Sequencing`): artifact + behavior domains fully, cross-device sync, persona-weighted ranker tuning, confidence-decay tuning per persona.

---

## 19. Open questions

1. **Vector store vendor.** Chroma vs LanceDB vs Qdrant-embedded vs custom HNSW (hnswlib-rs / usearch). Upstream plan leaves open; impacts on-disk layout, encryption story, rebuild time, and Lite-tier footprint.
2. **Embedding model per tier.** Is `bge-small` at 384d sufficient for Lite recall quality? Or does Lite need a distilled bge-m3 variant? Benchmark required.
3. **Inline-content encryption vs SQLCipher whole-DB.** SQLCipher is simpler but slower; per-column encryption is more surgical but more code. L5 §8 key handling must be aligned either way.
4. **Contradiction surfacing UX vs ranking behavior.** Does the ranker down-weight **both** conflicting items, **neither**, or surface the higher-confidence one with a flag? Design stance says "surface via provenance, no auto-resolution"; the ranker behavior specifics (e.g. always return both in top-k for L1) need L7 UX input.
5. **Auto-saved memory default retention.** `NDays(30)` balanced default is a guess; needs user-testing signal from OSS Preview.
6. **Behavior-domain schema.** Upstream plan explicitly defers "Behavior-layer schema (last to design)". This doc treats Behavior as a first-class domain with `MemoryWriteExtractedPref` gating but leaves the observation-signal grammar open.
7. **CRDT / op-log for sync.** Cross-device sync is a later phase; the choice affects provenance-chain merge semantics (see `L2_memory_kernel.md §Open decisions`).
8. **`internal` privacy class — exportable at all?** Current stance: never. But debug export for Don's own troubleshooting may need a Power User / Custom waiver path. Unresolved.
9. **Master-key recovery** when the user loses the keyring. Recovery phrase? Account-bound key escrow? Impacts §7.3 and whether "forgetting" survives a key-loss event (probably: if the key is lost, all encrypted content is irretrievably forgotten — which is arguably correct, but needs UX).
10. **`RouterAllowRemoteWithPrivate` granularity.** L5 §10.4 scopes this to `ProviderId`; §13 here inherits that scope. Should this be further task-scoped at L2 retrieval time (i.e. the grant applies only to a specific retrieval purpose, not "all private to provider X this session")? Waiver-scope precision affects how L2 pre-filters.

---

## 20. Contradictions flagged with upstream

Per doctrine: flag contradictions; do not silently resolve.

1. **Five-layer vs six-domain count.** Upstream `L2_memory_kernel.md §Five layers` enumerates **five**: ephemeral / session / durable-user / artifact / behavior. This design adds a sixth: `AssistantStateMemory` (`internal` privacy class). Rationale: persona coherence + presence state need a typed home with explicit privacy class so they don't masquerade as user memory. **Flagged for Don's sign-off.** If rejected, `AssistantStateMemory` folds into `SessionMemory` with an `internal` subtype marker, at the cost of weaker typing.
2. **`MemoryRead` as "Low risk, auto everywhere".** L5 §2.2 lists `MemoryRead` as risk=Low with `auto` across all presets. This design requires L5 evaluation per `(domain, privacy_class)` combo, which is strictly more stringent — consistent with L5 §10 privacy-posture gate, but the §2.2 table row alone would permit silent reads of `secret` memories. **Interpretation used here:** §10 gate supersedes §2.2 row for any non-`public`/`internal` class. L5's own design supports this reading, but the §2.2 table is misleading in isolation and should be footnoted.
3. **Upstream §Boundaries — "Owns: memory-write event emission and cross-engine memory-hit publication"** lines up with §9 here, but upstream also says L2 **does not own** "Permission evaluation for memory access (L5)" — consistent. No contradiction, just re-asserted.
4. **Retention vs durable-layer infinite memories.** Upstream §Acceptance criteria says "Novelty filter reduces durable-layer write rate to <5%"; this design's auto-saved default of `NDays(30)` prunes further. If <5% of candidates become durable and of those some auto-expire at 30 days, steady-state durable count may be lower than upstream implicitly assumes. **Flagged as open question #5.**

---

## Closing self-review checklist

- [x] Every memory op has an L5 capability entry (§6.1 table, §11 capability column).
- [x] Every MemoryHit carries `privacy_class` (§5.3, §13 rule #1).
- [x] Every event in §9 has typed fields + projection flag.
- [x] §12 has a degraded-mode entry for each failure class (retrieval, low-confidence, corrupt SQLite, contradictions, policy-deny, index rebuild, retention failure, provenance rewrite, audit-log upstream failure, embedding corruption, master-key unavailable).
- [x] §15 gives L1 / L4 / L6 / L7 enough stub surface (trait, event shapes, consumed PolicyEngine, per-layer notes).
- [x] Contradictions flagged (§20), not silently resolved.
- [x] Storage is local-first, single-writer, Tauri-shell-aligned (§7, §8.4).
- [x] Every user-visible path linked in file:///C:/... forward-slash form.
