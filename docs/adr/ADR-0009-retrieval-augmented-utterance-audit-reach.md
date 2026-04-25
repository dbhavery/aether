# ADR-0009: Retrieval-augmented utterance reach into L5 audit + L1 transcripts

- **Status:** **Proposed** (Don to ratify; cross-layer change requires its own focused session per CLAUDE.md §1.3 "one layer per session" doctrine).
- **Date:** 2026-04-24
- **Deciders:** Don (owner). Claude proposes, captures the asymmetry from the M2 Run 3 Session A handoff.
- **Supersedes:** nothing.
- **Superseded by:** nothing.
- **Related:** `docs/adr/ADR-0005-retrieval-wiring.md` (introduced the augmentation), `docs/adr/ADR-0007-embeddings-onboarding.md` (the ongoing onboarding work that surfaced this), `HANDOFF_2026-04-24_M2_RUN_3_SESSION_A_COMPLETE.md` §4.B (Risk B carry-over).

## Context

ADR-0005 wired retrieval into the turn dispatch path. The current behaviour, in `apps/desktop/src-tauri/src/commands.rs::submit_turn`:

```rust
let hits = run_retrieval_context(&state, SESSION_ID, &text, max_items, DEFAULT_RETRIEVAL_DEADLINE);
let retrieval_block = format_retrieval_block(&hits);
let router_utterance = augment_utterance(retrieval_block.as_deref(), &text);

let request = TurnRequest { /* ... */ utterance: router_utterance, /* ... */ };
// Memory + transcript independently records the ORIGINAL `text`:
let _ = state.memory.append(user_record_raw(SESSION_ID, &text, ts));
```

This produces a **two-channel asymmetry**:

- **Memory + transcript** see the **original** utterance (`text`). Correct: the user typed `text`, not the augmented form, and the audit story "what did the user say" should reflect intent.
- **L5 audit + L1 turn record** see the **augmented** utterance (`router_utterance` containing the prepended `Relevant context (retrieval): ...` block). Correct in one sense (it's what the model actually saw), wrong in another (it's not what the user said, and it pollutes audit-search semantics with retrieval block content).

A user reviewing the audit log would see their own utterances bracketed with retrieval context they never wrote. Worse, the same utterance composed with different memories produces materially different audit rows — making "what did Don say to Aether?" unanswerable from audit alone.

This ADR proposes the cleanup. **It is explicitly cross-layer** (touches L1 turn engine, L5 audit store, and the shell's submit_turn) and therefore violates CLAUDE.md §1.3 "one layer per session" — implementation requires a focused session of its own, not a smuggled fix into an unrelated commit.

## Decisions

### 1. The audit truth is the user's original utterance, not the augmented form.

L5 audit rows for `Capability::Conversation` record `original_utterance` (what the user typed), not the model-input string. The retrieval block is an internal prompt-builder artifact, not an audit-relevant fact about user intent.

Rationale: audit answers "what did the user do?" not "what did the model see?" The latter is a reproducibility concern handled by separate prompt-replay machinery (future).

### 2. The retrieval provenance is captured separately, on the same audit row, as structured metadata.

Add an optional `retrieval_provenance` field to the audit row:

```rust
pub struct RetrievalProvenance {
    pub block_present: bool,
    pub hits: Vec<RetrievedMemoryRef>, // (memory_id, domain, score)
}
```

This way the audit can answer "what context did Aether use?" without polluting the `original_utterance` field. Searching audit by user phrasing still works; correlating phrasing to retrieval behavior is a separate query.

### 3. The transcript shape stays as-is.

Memory + transcript already record the original. No change. Decision 2 only adds structured metadata to the audit row, not to the transcript.

### 4. The router still receives the augmented utterance.

The shell's `submit_turn` continues to compose `router_utterance = augment_utterance(block, original)` and pass it to `TurnRequest`. The change is in how `TurnRequest` (and downstream L1 + L5) decompose that input for the audit row.

Two implementation paths considered (Decision 5 picks):

**Path A — split TurnRequest fields.** Add `original_utterance: String` and `model_input_utterance: String` to `TurnRequest`. The L1 engine forwards `model_input_utterance` to the provider but writes `original_utterance` to the audit row. Clearest contract; requires `TurnRequest` schema bump.

**Path B — strip the augmentation in L1.** L1 detects the `"Relevant context (retrieval):\n"` prefix and strips it before audit. Brittle (relies on string format), does not survive a future block-format change.

### 5. Pick Path A.

Path A is the right shape. The cost is one new field on `TurnRequest` and a small audit-row schema change. The benefit is a stable, format-independent contract: any future prompt-augmentation (Memory V2 retrieval block, presence-state injection, persona overlays) just adds another `model_input_*` field — the `original_utterance` remains untouched.

### 6. Migration of existing audit rows.

Existing rows pre-Path-A have augmented utterances stored as `utterance`. Keep them as-is — historical fidelity matters more than retroactive cleanup, and a migration would require parsing every row by retrieval-block-prefix detection (which Path B-style stripping rejected).

Add a `schema_version: u32` field on the audit row; pre-Path-A rows are version 1, post-Path-A rows are version 2. Audit UI surfaces the version when relevant ("This row uses the pre-2026-04-24 schema; the utterance may include retrieval context").

## Alternatives considered

### Strip augmentation in shell before audit (no L1 change).

The shell could pre-emit two memory rows: original to memory + transcript, augmented to a parallel "audit-only" sink. This duplicates writes, leaves L1 unaware of the asymmetry, and creates a maintenance trap (future prompt augmentations would have to remember to write twice). Rejected.

### Forbid retrieval from augmenting at all (revert ADR-0005).

The whole point of ADR-0005 is to give the model retrieved context. Reverting kills the feature. Rejected.

### Defer indefinitely.

Risk B in the Session A handoff carried this for one milestone already. The L1 audit dashboard hasn't shipped a UI yet; once it does, the asymmetry becomes a real user-visible bug. Worth fixing before the surface ships, not after. Defer is feasible but kicks the can.

## Consequences

**Positive.**

- Audit search by user phrasing actually works.
- Future prompt augmentations (presence-state, persona overlays, etc.) inherit the `original_utterance` field and stay clean by construction.
- Reproducibility ("what did the model see?") is recoverable from `model_input_utterance + retrieval_provenance` without needing to re-run the embed pipeline.

**Negative.**

- Cross-layer change: requires a focused session covering L1 (`TurnRequest` shape), L5 (audit row schema + storage migration), and shell (`submit_turn` field plumbing). Estimated 2-3 hr session.
- Audit-row schema bump means rot-guard anchor updates and a migration test for the version-1-vs-2 boundary.
- Frontend audit-row renderer (`TrustDrawer.tsx::AuditList`) needs to handle both schemas during the transition window.

**Neutral.**

- Existing audit rows stay as-is per Decision 6 — no destructive migration.

## Implementation note

This ADR is **Proposed**. Implementation is held until Don ratifies AND a cross-layer session is opened (per CLAUDE.md §1.3, this cannot land as a one-line fix in an unrelated commit).

Estimated change set on accept:

1. `packages/l1-interaction/src/turn.rs` — `TurnRequest` field split.
2. `packages/l5-policy/src/audit.rs` — audit-row schema bump (v1 → v2) + serde migration.
3. `apps/desktop/src-tauri/src/commands.rs::submit_turn` — pass both `original_utterance` and `router_utterance` into the request.
4. `apps/desktop/src/components/TrustDrawer.tsx::AuditList` — version-aware rendering.
5. New tests covering: round-trip serde for both schema versions, audit row contains the original utterance not the augmented form, retrieval_provenance is populated when retrieval fires.
6. Rot-guard anchors for the new fields in `tools/lint-policy-doc/check.py`.

## Open items (NOT decided here)

- Whether `retrieval_provenance` lives on the audit row or in a sidecar table keyed by `turn_id`. Sidecar is cleaner schema-wise but adds a join cost on audit reads.
- Whether to backfill `schema_version: 1` onto existing rows or treat the absence of the field as version 1 implicitly. (Implicit is cheaper; explicit is clearer.)
- Whether the audit UI should offer a toggle "show me what the model actually saw" that re-composes the `model_input` view.

---

(end of ADR-0009)
