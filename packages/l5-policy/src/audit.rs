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

/// Event variant of an audit row (bus payload).
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
