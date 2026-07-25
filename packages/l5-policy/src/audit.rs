//! Audit log types.
//!
//! The audit log is append-only, hash-chained, HMAC-integrity protected.
//! The chain and HMAC implementation live in `aether-storage`; this module
//! only shapes the row and the event that carries it across the bus.

use serde::{Deserialize, Serialize};

use crate::approval::ApprovalScope;
use crate::capability::{Capability, ResourceScope};
use crate::common::{ActorRef, ChangeId, MonotonicTimestamp, Seq, WallTimestamp};
use crate::decision::{DecisionKind, StaticReasonId};
use crate::grants::GrantId;

/// Stable id of a single audit row.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AuditId(pub String);

/// Opaque handle identifying the HMAC signing key the row was sealed under.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct KeyId(pub String);

/// One `stage_trace` row recording a stage of the 5-layer evaluator.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageTrace {
    /// Stage name (pre-gates, feature, action, resource, mode, duration).
    pub stage: String,
    /// Outcome (Pass / Deny / Ask / DraftOnly / NeedsUpgrade / Skip).
    pub outcome: String,
    /// Monotonic nanoseconds spent in this stage.
    pub ns: u64,
}

/// Schema version for [`AuditRecordEvent`]. Per ADR-0009 §Decision 6.
///
/// - `1` — pre-2026-04-25 rows. No `original_utterance` or
///   `retrieval_provenance`. Absence of the `schema_version` field on
///   the wire deserializes implicitly to v1 (cheaper than a backfill
///   per ADR-0009 §Open items resolution; recorded in the
///   2026-04-25 decisions log, D-001).
/// - `2` — post-2026-04-25. Carries optional `original_utterance` and
///   `retrieval_provenance`; `Capability::Conversation` rows populate
///   them, other rows leave them `None`.
pub const AUDIT_SCHEMA_VERSION_V1: u32 = 1;
/// Current writer-side schema version. Always written on new rows by
/// post-ADR-0009 code paths.
pub const AUDIT_SCHEMA_VERSION_V2: u32 = 2;

/// Reference to one memory row that retrieval pulled in for the turn.
/// Per ADR-0009 §Decision 2.
///
/// Identifies the source record (`memory_id`), which durable lane it
/// came from (`domain` — e.g. `"durable"`, `"facts"`), and the rank
/// score the retrieval orchestrator computed for it. Used by the audit
/// UI to show "what context did Aether use?" without duplicating the
/// memory text into the audit row.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RetrievedMemoryRef {
    /// Stable id of the memory row (provider-specific; matches
    /// `SessionMemoryStore` row ids).
    pub memory_id: String,
    /// Memory domain the row came from. String rather than the
    /// `MemoryDomain` enum so L5 stays free of an L2 type dependency.
    pub domain: String,
    /// Rank score the orchestrator assigned (cosine similarity in the
    /// current rank function; opaque downstream).
    pub score: f32,
}

/// Provenance of the retrieval block (if any) that augmented the
/// `model_input_utterance` for this turn. Per ADR-0009 §Decision 2.
///
/// `block_present` is the cheap top-level summary
/// ("did retrieval add anything?"); `hits` is the per-row breakdown.
/// When retrieval was off, denied, bailed out, or returned zero rows,
/// callers stamp `block_present: false, hits: vec![]` so the audit row
/// affirmatively records "we asked, nothing came back" instead of
/// silent absence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RetrievalProvenance {
    /// Whether the retrieval orchestrator emitted a non-empty block
    /// that was prepended to the model-input utterance.
    pub block_present: bool,
    /// The ranked memory rows the block drew from. Empty when
    /// `block_present` is false.
    ///
    /// **Hard cap: [`RETRIEVAL_PROVENANCE_HITS_CAP`] entries.** Writers
    /// MUST trim oversized inputs before stamping the audit row;
    /// [`RetrievalProvenance::new`] enforces this. The L5 audit writer
    /// also asserts the cap defensively in
    /// `policy_engine::PolicyEngineImpl::write_audit` so a caller that
    /// constructs the struct via raw field assignment cannot silently
    /// inflate the audit row, the canonical-hash CPU cost, or the
    /// `aether_audit.db` row size. Resolves SECURITY_REVIEW.md
    /// MEDIUM-2.
    pub hits: Vec<RetrievedMemoryRef>,
}

/// Maximum number of hits permitted in [`RetrievalProvenance::hits`].
///
/// Today the orchestrator's `top_k` is 5 (per the retrieval spec), so 16
/// leaves head-room for future ranking changes (e.g. multi-pass merges)
/// without re-tightening this constant. A sustained breach indicates the
/// caller is bypassing the orchestrator's `top_k` contract and should be
/// fixed at the source rather than absorbed into audit growth. Set per
/// SECURITY_REVIEW.md MEDIUM-2 recommendation.
pub const RETRIEVAL_PROVENANCE_HITS_CAP: usize = 16;

impl RetrievalProvenance {
    /// Construct a provenance row with the hits vector truncated to
    /// [`RETRIEVAL_PROVENANCE_HITS_CAP`]. Preferred over field-by-field
    /// construction because it enforces the cap writer-side.
    ///
    /// `hits` past the cap are dropped silently — the orchestrator's
    /// `top_k` contract is the source of truth, so anything past the
    /// cap is by definition lower-ranked than what was already kept.
    pub fn new(block_present: bool, mut hits: Vec<RetrievedMemoryRef>) -> Self {
        if hits.len() > RETRIEVAL_PROVENANCE_HITS_CAP {
            hits.truncate(RETRIEVAL_PROVENANCE_HITS_CAP);
        }
        Self {
            block_present,
            hits,
        }
    }
}

/// Optional ADR-0009 v2 audit fields, threaded through
/// [`crate::policy_engine::ActionRequest::audit_extras`] from the
/// caller into the audit row.
///
/// Lives as a dedicated struct so `ActionRequest` keeps a single
/// `Option<AuditExtras>` field rather than two parallel `Option<_>`
/// fields. Kept open for additive growth (e.g. future presence-state
/// snapshot, persona overlay id) without further `ActionRequest`
/// shape changes.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct AuditExtras {
    /// User's typed/spoken text. Mirrors
    /// `aether_l1_interaction::TurnRequest::original_utterance`.
    pub original_utterance: Option<String>,
    /// Retrieval block summary. `None` for capabilities that did not
    /// invoke the retrieval orchestrator (everything except
    /// `Capability::Conversation` today).
    pub retrieval_provenance: Option<RetrievalProvenance>,
}

/// Event variant of an audit row (bus payload).
///
/// ## ADR-0009 schema versions
///
/// `schema_version` discriminates v1 (pre-2026-04-25) from v2
/// (post-ADR-0009) rows. Deserializers reading old payloads see no
/// `schema_version` field — the `serde(default)` resolver maps that
/// case to v1 implicitly. v1 rows have `original_utterance: None` and
/// `retrieval_provenance: None`; the audit UI surfaces a "pre-ADR-0009
/// schema" badge so users understand why the user-phrasing field is
/// absent.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditRecordEvent {
    /// Row id.
    pub audit_id: AuditId,
    /// Monotonic timestamp.
    pub timestamp_monotonic: MonotonicTimestamp,
    /// Wall-clock timestamp (display only).
    pub timestamp_wall: WallTimestamp,
    /// Who / what initiated.
    pub actor: ActorRef,
    /// Capability requested.
    pub capability: Capability,
    /// Resource scope.
    pub resource: ResourceScope,
    /// Discriminator.
    pub decision: DecisionKind,
    /// Correlation id for the full chain of events tied to this decision.
    pub change_id: ChangeId,
    /// SHA-256 hash of the previous row's canonical serialization.
    pub prev_hash: Vec<u8>,
    /// HMAC over this row.
    pub record_hmac: Vec<u8>,
    /// Key id used to compute `record_hmac`.
    pub key_id: KeyId,
    /// Bus sequence number.
    pub seq: Seq,
    /// Optional reason copy-id (mirrors `Decision::DraftOnly.reason`).
    pub reason: Option<StaticReasonId>,
    /// Optional evaluator trace for diagnostics.
    pub stage_trace: Vec<StageTrace>,
    /// Whether this row was produced under a privileged profile.
    pub privileged_profile: bool,
    /// ADR-0009 schema version. Writers stamp [`AUDIT_SCHEMA_VERSION_V2`]
    /// on new rows; absence on the wire (old rows) maps to
    /// [`AUDIT_SCHEMA_VERSION_V1`] via `serde(default)`.
    #[serde(default = "default_schema_version_v1")]
    pub schema_version: u32,
    /// User's original utterance for `Capability::Conversation` rows.
    /// `None` on v1 rows and on v2 rows for non-conversation
    /// capabilities (e.g. file ops, media frames).
    #[serde(default)]
    pub original_utterance: Option<String>,
    /// Retrieval block provenance. `None` on v1 rows and on v2 rows
    /// where retrieval did not run for the turn.
    #[serde(default)]
    pub retrieval_provenance: Option<RetrievalProvenance>,
    /// Scope chosen on the user-facing approval that produced this row.
    /// `None` for: pre-T1.3 rows, system-emitted decisions that never
    /// went to the user (`Decision::Allow` from a pre-existing grant,
    /// `Decision::Deny` from policy without prompting).
    /// See the approval-scope design in `ARCHITECTURE.md`.
    ///
    /// Note: not covered by HMAC chain — the v2 `CanonicalAuditPayloadV2`
    /// shape is frozen, so adding this field does NOT alter
    /// `canonical_bytes`. A future v3 schema bump can fold it in if
    /// audit-integrity coverage is required. Until then this field is
    /// audit-visible-but-not-sealed; trust-center filtering and human
    /// review still benefit from it.
    #[serde(default)]
    pub approval_scope: Option<ApprovalScope>,
    /// Backref to the grant that auto-approved this row. `Some(_)` only
    /// when this row was a follow-on use of a `OncePerSession` /
    /// `OncePerTask` grant (i.e. the user was *not* prompted). See
    /// the approval-scope design in `ARCHITECTURE.md`.
    #[serde(default)]
    pub auto_approved_under_grant: Option<GrantId>,
}

/// Resolver for the `schema_version` `serde(default)`. Returns v1 so
/// pre-ADR-0009 rows on disk deserialize cleanly without an explicit
/// field on the wire.
fn default_schema_version_v1() -> u32 {
    AUDIT_SCHEMA_VERSION_V1
}

/// Filter for `policy.get_audit_summary` and `policy.stream_audit`.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AuditFilter {
    /// Limit to capabilities starting with this root (prefix).
    pub capability_prefix: Option<String>,
    /// Limit to a persona.
    pub persona_id: Option<crate::common::PersonaId>,
    /// Monotonic window (inclusive lower).
    pub since: Option<MonotonicTimestamp>,
    /// Monotonic window (exclusive upper).
    pub until: Option<MonotonicTimestamp>,
    /// Limit to decision kinds.
    pub decisions: Option<Vec<DecisionKind>>,
    /// Limit to rows whose `approval_scope` matches. `None` (the
    /// default) does not filter on scope. See
    /// the approval-scope design in `ARCHITECTURE.md`.
    pub approval_scope: Option<ApprovalScope>,
}

/// Lightweight audit summary returned by `policy.get_audit_summary`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditSummary {
    /// Time window covered.
    pub window: (MonotonicTimestamp, MonotonicTimestamp),
    /// Per-decision counts.
    pub by_decision: std::collections::HashMap<DecisionKind, u64>,
    /// Top-5 capabilities for the window.
    pub top_capabilities: Vec<(Capability, u64)>,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fake_hit(i: usize) -> RetrievedMemoryRef {
        RetrievedMemoryRef {
            memory_id: format!("mem-{i}"),
            domain: String::from("durable"),
            score: 0.5,
        }
    }

    #[test]
    fn retrieval_provenance_new_truncates_above_cap() {
        let oversized: Vec<_> = (0..RETRIEVAL_PROVENANCE_HITS_CAP + 8)
            .map(fake_hit)
            .collect();
        let p = RetrievalProvenance::new(true, oversized);
        assert_eq!(p.hits.len(), RETRIEVAL_PROVENANCE_HITS_CAP);
        // Truncation drops the *tail* — first cap entries (assumed
        // highest-ranked by orchestrator contract) survive.
        assert_eq!(p.hits.first().unwrap().memory_id, "mem-0");
        assert_eq!(
            p.hits.last().unwrap().memory_id,
            format!("mem-{}", RETRIEVAL_PROVENANCE_HITS_CAP - 1)
        );
    }

    #[test]
    fn retrieval_provenance_new_passes_through_when_under_cap() {
        let small: Vec<_> = (0..3).map(fake_hit).collect();
        let p = RetrievalProvenance::new(true, small);
        assert_eq!(p.hits.len(), 3);
    }

    #[test]
    fn retrieval_provenance_new_passes_through_at_exact_cap() {
        let exact: Vec<_> = (0..RETRIEVAL_PROVENANCE_HITS_CAP).map(fake_hit).collect();
        let p = RetrievalProvenance::new(false, exact);
        assert_eq!(p.hits.len(), RETRIEVAL_PROVENANCE_HITS_CAP);
        assert!(!p.block_present);
    }

    #[test]
    fn retrieval_provenance_cap_constant_is_sixteen() {
        // Pin the cap value so a future change is forced through code
        // review. Per SECURITY_REVIEW.md MEDIUM-2 — cap of 16 leaves
        // head-room over today's `top_k = 5` without absorbing
        // unbounded growth.
        assert_eq!(RETRIEVAL_PROVENANCE_HITS_CAP, 16);
    }
}
