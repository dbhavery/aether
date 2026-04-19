//! L5 event family emitted on the Rust-internal event bus.
//!
//! Source: `planning/plans/implementation_prep/event_contracts_master.md`
//! and `planning/plans/implementation_prep/L5_interface_pack.md` §4.

use serde::{Deserialize, Serialize};

use crate::approval::ApprovalTicketId;
use crate::audit::{AuditId, AuditRecordEvent};
use crate::byok::{CostWindow, ProviderId};
use crate::capability::{Capability, ResourceScope, RiskClass};
use crate::common::{
    ActorRef, Cents, ChangeId, MonotonicTimestamp, PersonaId, RequestId, Seq,
};
use crate::decision::{DecisionKind, StaticReasonId};
use crate::grants::{ApprovalMode, GrantDuration, GrantId};
use crate::posture::{PolicyPostureSummary, PostureTrigger, WarnLevel};

/// Discriminator used by `EventFilter` bitsets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum L5EventKind {
    /// `ActionRequest` — republished on bus.
    ActionRequest,
    /// `PolicyDecision` result.
    PolicyDecision,
    /// `ApprovalPending` ticket.
    ApprovalPending,
    /// `GrantIssued`.
    GrantIssued,
    /// `GrantRevoked`.
    GrantRevoked,
    /// `AuditRecord`.
    AuditRecord,
    /// `EmergencyRevokeAll`.
    EmergencyRevokeAll,
    /// `CostThresholdHit`.
    CostThresholdHit,
    /// `PolicyPostureChanged`.
    PolicyPostureChanged,
}

/// Sum type of every L5 bus event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum L5Event {
    /// Republished `ActionRequest`.
    ActionRequest(ActionRequestEvent),
    /// Decision result.
    PolicyDecision(PolicyDecisionEvent),
    /// Ask ticket in flight.
    ApprovalPending(ApprovalPendingEvent),
    /// Grant issued.
    GrantIssued(GrantIssuedEvent),
    /// Grant revoked.
    GrantRevoked(GrantRevokedEvent),
    /// Audit row written.
    AuditRecord(AuditRecordEvent),
    /// Emergency revoke fired.
    EmergencyRevokeAll(EmergencyRevokeAllEvent),
    /// Cost threshold crossed.
    CostThresholdHit(CostThresholdHitEvent),
    /// Posture changed.
    PolicyPostureChanged(PolicyPostureChangedEvent),
}

// ---------------------------------------------------------------------------
// Individual event structs. Field sets per event_contracts_master.md /
// L5_interface_pack.md §4.
// ---------------------------------------------------------------------------

/// Republished `ActionRequest` for observer layers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionRequestEvent {
    /// Request id.
    pub request_id: RequestId,
    /// Capability.
    pub capability: Capability,
    /// Resource.
    pub resource: ResourceScope,
    /// Persona.
    pub actor_persona: PersonaId,
    /// Emitted-at.
    pub emitted_at: MonotonicTimestamp,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

/// `PolicyDecision` emitted on every `evaluate`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyDecisionEvent {
    /// Request id correlation.
    pub request_id: RequestId,
    /// Decision kind.
    pub decision: DecisionKind,
    /// Audit row.
    pub audit_id: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
    /// Optional reason.
    pub reason: Option<StaticReasonId>,
    /// Effective mode used by evaluator (if Allow / Ask).
    pub effective_mode: Option<ApprovalMode>,
}

/// `ApprovalPending` emitted for `Decision::Ask`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalPendingEvent {
    /// Ticket id.
    pub ticket_id: ApprovalTicketId,
    /// Correlating request.
    pub request_id: RequestId,
    /// Capability.
    pub capability: Capability,
    /// Resource.
    pub resource: ResourceScope,
    /// Risk class (copied from `CapabilityInfo`).
    pub risk_class: RiskClass,
    /// Static copy-id for the explanation string.
    pub explanation: StaticReasonId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

/// `GrantIssued` event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrantIssuedEvent {
    /// Grant id.
    pub grant_id: GrantId,
    /// Capability.
    pub capability: Capability,
    /// Scope pattern.
    pub resource_scope: ResourceScope,
    /// Mode.
    pub approval_mode: ApprovalMode,
    /// Duration.
    pub duration: GrantDuration,
    /// Issued-at.
    pub issued_at: MonotonicTimestamp,
    /// Actor that triggered issuance.
    pub issued_by: ActorRef,
    /// Backref to audit row.
    pub audit_ref: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
    /// Preset version at issuance.
    pub preset_version_issued_under: u32,
}

/// Why a grant was revoked.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RevokeReason {
    /// User revoked via trust center.
    UserRevoked,
    /// Preset switch narrowed scope.
    PresetNarrowed,
    /// Persona swap cascaded revoke.
    PersonaSwap,
    /// TTL hit.
    TtlExpired,
    /// Emergency revoke-all fired.
    EmergencyRevoke,
    /// Approval timed out (maps from `ApprovalExpired`).
    ApprovalTimeout,
}

/// `GrantRevoked` event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GrantRevokedEvent {
    /// Grant id.
    pub grant_id: GrantId,
    /// Revocation time.
    pub revoked_at: MonotonicTimestamp,
    /// Reason.
    pub revoked_reason: RevokeReason,
    /// Audit backref.
    pub audit_ref: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

/// Scope of an emergency revoke.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum EmergencyScope {
    /// Revoke every grant.
    All,
    /// Revoke an entire capability category.
    Category(crate::capability::Capability),
    /// Revoke a persona's grants only.
    Persona(PersonaId),
}

/// `EmergencyRevokeAll` event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmergencyRevokeAllEvent {
    /// Initiator.
    pub initiated_by: ActorRef,
    /// Scope.
    pub scope: EmergencyScope,
    /// Start timestamp.
    pub initiated_at: MonotonicTimestamp,
    /// Finish timestamp (if any).
    pub completed_at: Option<MonotonicTimestamp>,
    /// Total revoked.
    pub revoked_count: Option<u32>,
    /// Audit backref.
    pub audit_ref: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

/// `CostThresholdHit` event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostThresholdHitEvent {
    /// Provider.
    pub provider: ProviderId,
    /// Which threshold crossed.
    pub threshold: crate::byok::CostThreshold,
    /// Dollars-hit value (for UX).
    pub dollars_hit: Cents,
    /// Window.
    pub counter_window: CostWindow,
    /// Optional early-warn level.
    pub warn_level: Option<WarnLevel>,
    /// Audit backref.
    pub audit_ref: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

/// `PolicyPostureChanged` event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyPostureChangedEvent {
    /// Posture before change.
    pub prior_posture: PolicyPostureSummary,
    /// Posture after change.
    pub new_posture: PolicyPostureSummary,
    /// What triggered the change.
    pub trigger: PostureTrigger,
    /// Grants dropped on narrow.
    pub stripped_grants: Vec<GrantId>,
    /// Capabilities added on widen.
    pub added_capabilities: Vec<Capability>,
    /// Audit backref.
    pub audit_ref: AuditId,
    /// Change id.
    pub change_id: ChangeId,
    /// Seq.
    pub seq: Seq,
}

impl L5Event {
    /// Flat kind for filter matching.
    pub fn kind(&self) -> L5EventKind {
        match self {
            L5Event::ActionRequest(_) => L5EventKind::ActionRequest,
            L5Event::PolicyDecision(_) => L5EventKind::PolicyDecision,
            L5Event::ApprovalPending(_) => L5EventKind::ApprovalPending,
            L5Event::GrantIssued(_) => L5EventKind::GrantIssued,
            L5Event::GrantRevoked(_) => L5EventKind::GrantRevoked,
            L5Event::AuditRecord(_) => L5EventKind::AuditRecord,
            L5Event::EmergencyRevokeAll(_) => L5EventKind::EmergencyRevokeAll,
            L5Event::CostThresholdHit(_) => L5EventKind::CostThresholdHit,
            L5Event::PolicyPostureChanged(_) => L5EventKind::PolicyPostureChanged,
        }
    }
}
