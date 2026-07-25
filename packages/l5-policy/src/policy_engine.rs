//! `PolicyEngine` trait and in-process error vocabulary.

use serde::{Deserialize, Serialize};

use crate::approval::ApprovalResponse;
use crate::capability::{
    Capability, CapabilityFilter, CapabilityInfo, ProvenanceTag, ResourceScope,
};
use crate::common::{ChangeId, MonotonicTimestamp, PersonaId, RequestId, TaskId, TurnId};
use crate::decision::Decision;
use crate::events::{EmergencyScope, L5Event, L5EventKind};
use crate::grants::{Grant, GrantFilter};
use crate::posture::DegradedMode;

/// An action-initiating engine's request for authorization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionRequest {
    /// ULID of this request.
    pub request_id: RequestId,
    /// Turn correlation.
    pub turn_id: TurnId,
    /// What to do.
    pub capability: Capability,
    /// What it is bound to.
    pub resource: ResourceScope,
    /// Persona initiating.
    pub actor_persona: PersonaId,
    /// Monotonic emit timestamp.
    pub emitted_at: MonotonicTimestamp,
    /// Optional task id.
    pub task_id: Option<TaskId>,
    /// Provenance tags (missing → treated as tainted).
    pub provenance_tags: Vec<ProvenanceTag>,
    /// Route hint from L4.
    pub intended_route: Option<RouteHint>,
    /// Optional risk-class hint (evaluator re-checks regardless).
    pub risk_class_hint: Option<crate::capability::RiskClass>,
    /// ADR-0009 audit-row extras: original utterance + retrieval
    /// provenance. The evaluator copies this into the audit row when
    /// present; absent on non-conversation capabilities and on legacy
    /// wire payloads (covered by the serde default).
    #[serde(default)]
    pub audit_extras: Option<crate::audit::AuditExtras>,
}

/// Hint L4 attaches when it has already picked a tier.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum RouteHint {
    /// Local-only.
    LocalOnly,
    /// Prefer local, may escalate.
    LocalPreferred,
    /// Remote escalation chosen — must clear privacy gate.
    RemoteEscalation,
}

/// Subscriber-side bus filter.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EventFilter {
    /// Event kinds to include.
    pub kinds: Vec<L5EventKind>,
    /// Capabilities (prefix-ish) filter.
    pub capabilities: Vec<Capability>,
    /// Optional `since_seq` cursor.
    pub since_seq: Option<u64>,
}

/// Opaque handle to a bus subscription. Wave 2 is a placeholder; Wave 3
/// replaces with a real `tokio::sync::broadcast::Receiver`-backed stream.
#[derive(Debug)]
pub struct EventStream<T> {
    _marker: std::marker::PhantomData<T>,
}

impl<T> Default for EventStream<T> {
    fn default() -> Self {
        Self {
            _marker: std::marker::PhantomData,
        }
    }
}

/// Receipt of an emergency revoke operation (in-process Rust path).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmergencyReceipt {
    /// Completion time (monotonic ns).
    pub completed_ns: u64,
    /// Total revoked.
    pub revoked_count: u32,
}

/// The non-bypassable authorization surface.
///
/// Every executor holds an `Arc<dyn PolicyEngine>` and presents a
/// `Decision::Allow` (or a resolved grant) before any side-effectful call.
pub trait PolicyEngine: Send + Sync {
    /// Synchronous evaluation. See §5 of the interface pack for budgets.
    fn evaluate(&self, req: ActionRequest) -> Result<Decision, PolicyEngineError>;

    /// Subscribe to a category of events.
    fn subscribe(&self, filter: EventFilter) -> EventStream<L5Event>;

    /// Emergency revoke — usually via Tauri, occasionally in-process.
    fn emergency_revoke(
        &self,
        scope: EmergencyScope,
    ) -> Result<EmergencyReceipt, PolicyEngineError>;

    /// Read-only grants snapshot.
    fn snapshot_grants(&self, filter: GrantFilter) -> Vec<Grant>;

    /// Enumerate capabilities visible under the active posture.
    fn capabilities(&self, filter: CapabilityFilter) -> Vec<CapabilityInfo>;

    /// Ingest a user response to a pending approval ticket.
    fn respond_approval(&self, response: ApprovalResponse) -> Result<ChangeId, PolicyEngineError>;
}

/// In-process error vocabulary.
#[derive(Debug, thiserror::Error)]
pub enum PolicyEngineError {
    /// Engine is in a degraded mode.
    #[error("degraded mode: {0:?}")]
    Degraded(DegradedMode),
    /// Event bus torn down (shutdown).
    #[error("bus closed")]
    BusClosed,
    /// Malformed request.
    #[error("invalid request: {0}")]
    Invalid(&'static str),
    /// Ticket id not found.
    #[error("ticket not found")]
    TicketNotFound,
    /// Ticket state conflict (double-respond, stale, revoked mid-ask).
    #[error("ticket conflict: {0}")]
    TicketConflict(&'static str),
    /// Capability-gated in-process call without valid re-auth token.
    #[error("requires re-auth")]
    RequiresReauth,
    /// Audit writer unhealthy.
    #[error("audit blocked")]
    AuditBlocked,
    /// Uncategorized.
    #[error("internal: {0}")]
    Internal(String),
}
