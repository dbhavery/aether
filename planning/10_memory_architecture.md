# 10 — Memory Architecture

Memory is central to Aether's companion feel. The memory engine is a **must-own custom-built layer** — not a vector database bolted onto chat history.

---

## Strategic role

Memory is what turns an assistant into a companion. Without persistent, governable, semantically-rich memory:
- The assistant forgets preferences between sessions.
- Relationship continuity doesn't exist.
- Personalization collapses to a system-prompt blob.
- Trust erodes — users can't see or control what's remembered.

Memory is therefore a **top-tier moat layer**, not infrastructure.

---

## Memory layers (five)

### 1. Ephemeral turn memory
- **Scope:** Current turn in progress.
- **Contents:** Active conversational state, partial transcript, in-flight intent.
- **Lifetime:** Until turn commits.
- **Purpose:** Immediate coherence within a single exchange.

### 2. Session memory
- **Scope:** Current conversation session.
- **Contents:** Conversation history, referenced artifacts, within-session context.
- **Lifetime:** Session only (by default).
- **Purpose:** Coherence across the current conversation; "you just said..."

### 3. Durable user memory
- **Scope:** Persistent across sessions.
- **Contents:** User preferences, biographical facts, recurring patterns, stated goals, stated dislikes.
- **Lifetime:** Until user edits or deletes.
- **Purpose:** Relationship continuity. "I remember you said..."

### 4. Artifact / document / file memory
- **Scope:** External content the user has shared or that the assistant has accessed.
- **Contents:** Files, screenshots, documents, extracted entities, summaries of external content.
- **Lifetime:** User-controlled; retention rules apply.
- **Purpose:** Reference across sessions. "In the doc you showed me last week..."

### 5. Behavior / persona memory
- **Scope:** How the user likes to interact.
- **Contents:** Preferred assistant style, voice, pacing, acknowledgment patterns, humor tolerance, formality.
- **Lifetime:** Durable, slow-drift (adapts gradually to feedback).
- **Purpose:** The assistant's social adaptation over time.

(Optional 6th: **extracted preference memory** — extracted implicit preferences, surfaced for user confirmation before becoming durable.)

---

## Memory governance (mandatory controls)

Users MUST be able to:
- **Review** — see everything the assistant remembers about them
- **Edit** — correct or rewrite any memory
- **Revoke** — remove a specific memory immediately
- **Delete** — bulk-delete a category or all memory
- **Export** — take their memory elsewhere (JSON, human-readable)
- **Configure retention** — per-category retention rules

The memory governance UX lives inside the sandbox/settings mode and is surfaced in the trust center.

---

## Memory quality requirements

### Selective ingestion
- **Do not store everything.** Indiscriminate ingestion produces noise, privacy risk, and retrieval failure.
- Only candidates that pass a novelty + salience filter are eligible for durable memory.
- User can explicitly request "remember this" to bypass filter.
- User can explicitly request "don't remember this" to block storage.

### Novelty filtering
- Duplicate-or-near-duplicate memories are merged, not duplicated.
- Existing memory is updated when new information contradicts or refines it — with provenance log.

### Confidence weighting
- Every memory item carries a **confidence score**:
  - Stated by user (high confidence)
  - Inferred from behavior (lower confidence)
  - Extracted from documents (context-dependent)
- Low-confidence memories are surfaced for user confirmation before they shape responses.

### Provenance tracking
- Every memory item records:
  - Source (user statement / inferred / extracted from artifact X)
  - Timestamp
  - Session ID
  - Related conversation excerpt (if user statement)
- Provenance is inspectable by the user.

### Recency and salience
- Recent memories weight higher in retrieval by default.
- User-pinned memories weight higher regardless of recency.
- Salience decays for memories that haven't been referenced in N months (configurable).

### User-controlled forgetting
- Memory can be soft-deleted (reversible within a grace window) or hard-deleted.
- Hard-delete purges from all indexes.
- Forgetting is observable in the trust center.

---

## Multimodal memory

Memory supports:
- Text (primary)
- Images (screenshots, photos the user shares)
- Audio (optional, user-opt-in — conversation snippets)
- Files (documents with summaries + extracted facts)

Research direction (from [sources_matrix.md](sources_matrix.md)): selective ingestion, progressive retrieval, multimodal atomic units, structured memory units. OmniMem-style design principles apply.

---

## Retrieval

### Progressive retrieval
- **Fast path:** keyword + recency match for reflex answers.
- **Semantic path:** embedding similarity for deeper context.
- **Graph path:** relationship-based retrieval (who, what, when, related to).
- Multiple paths can fire in parallel; highest-confidence hits surface.

### Retrieval confidence
- Every retrieval result carries a confidence score.
- Low-confidence hits may be mentioned to the user ("I think I remember...") rather than asserted.
- The user can correct — correction updates confidence, not just the memory content.

### Retrieval scope
- **Always**: current session memory.
- **Usually**: durable user memory.
- **By permission**: artifact memory (if the file is in-scope per permissions).
- **Never silent**: cross-user memory (N/A in Aether — single-user architecture).

---

## Memory writes

### When to write
- User makes a stated commitment ("I prefer X")
- User shares a persistent fact ("My name is...")
- Behavior feedback ("Don't respond so formally")
- Task outcome (result of a tool run that the user wanted remembered)
- Explicit user request ("Remember this")

### When NOT to write
- Transient conversational state
- Sensitive data flagged by the user
- Content the user has explicitly asked not to remember
- Low-confidence inferences (without explicit confirmation)

### Write flow
1. Cognition emits `memory_write` event with candidate memory.
2. Memory engine applies novelty + salience filter.
3. If passes: write to durable store with provenance.
4. If borderline: surface to user for "should I remember this?" confirmation.
5. Audit logged.

---

## Storage and indexing

### Target architecture
- **Primary store**: local (SQLite + vector index, TBD in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md))
- **Encryption**: at-rest encryption for durable memory.
- **Sync**: when multi-device is active, encrypted delta sync (desktop is canonical source).
- **Backup / export**: user-initiated, human-readable format.

### Indexes needed
- Text / keyword index
- Vector / embedding index
- Temporal index (recency queries)
- Relational / graph index (entity relationships)
- Per-category tag index

---

## Interaction with other engines

- **Cognition** queries memory at turn start (reflex path) and during deliberative reasoning.
- **Interaction** surfaces memory hits to the UI where relevant ("I remember you mentioned...").
- **Policy** enforces permission checks on artifact memory (file access scope).
- **Persona compiler** reads behavior/persona memory to shape responses.
- **Trust center** exposes memory counts, recent writes, retention status.

---

## Isabelle-specific memory

Isabelle inherits the full memory engine but with:
- Wider ingestion scope (Don's workflows, projects, personal data)
- Longer retention
- Cross-project memory linkage (Isabelle knows about Don's other projects — Library, CIGE, Portfolio, etc.)
- Integration with existing Isabelle_Kunstig data where migration applies

See [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md).

---

## Anti-patterns (rejected)

- **Vector DB dump of every conversation turn** — produces noise, zero governance.
- **System-prompt memory injection without persistence** — not durable, not editable, not inspectable.
- **Hidden memory the user can't see** — destroys trust.
- **Silent memory that influences responses without being mentioned** — violates transparency.
- **Indiscriminate ingestion** — privacy risk and retrieval failure.
- **Confidently wrong retrieval** — low-confidence hits must be flagged, not asserted.

---

## Cross-references
- Architecture: [08_system_architecture.md](08_system_architecture.md)
- Trust center: [13_trust_security_redteam.md](13_trust_security_redteam.md)
- Permissions (artifact memory scope): [12_permissions_autonomy.md](12_permissions_autonomy.md)
- Isabelle memory extensions: [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md)
