//! Audit log types.
//!
//! The audit log is append-only, hash-chained, HMAC-integrity protected.
//! The chain and HMAC implementation live in `aether-storage`; this module
//! only shapes the row and the event that carries it across the bus.

use serde::{Deserialize, Serialize};

use crate::capability::{Capability, ResourceScope};
use crate::common::{ActorRef, ChangeId, MonotonicTimestamp, Seq, WallTimestamp};
use crate::decision::{DecisionKind, StaticReasonId};

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
///   per ADR-0009 §Open items resolution in
///   `planning/session_2026-04-25/DECISIONS_LOG.md` D-001).
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
    pub hits: Vec<RetrievedMemoryRef>,
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
    /// Whether this row was produced under a privileged profile (Isabelle).
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
