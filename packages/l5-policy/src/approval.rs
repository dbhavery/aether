//! Approval tickets and user-response shapes.
//!
//! Locked by Decision 2 (2026-04-18): `UserChoice::DeferToDraft` resolves
//! server-side to `Decision::DraftOnly { source: UserChoice }`.

use serde::{Deserialize, Serialize};

use crate::capability::{Capability, ResourceScope};
use crate::common::{CommandToken, MonotonicTimestamp, RequestId};
use crate::grants::GrantDuration;

/// Unique id of an in-flight approval ticket.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ApprovalTicketId(pub String);

/// Ticket issued to L7 when a `Decision::Ask` is emitted.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalTicket {
    /// Stable id for round-tripping.
    pub ticket_id: ApprovalTicketId,
    /// Originating request.
    pub request_id: RequestId,
    /// What the action wants to do.
    pub capability: Capability,
    /// Scope the capability is bound to.
    pub resource: ResourceScope,
    /// Optional deadline by which L7 should return a user choice.
    pub deadline_hint: Option<MonotonicTimestamp>,
    /// Suggested duration the UI may pre-select.
    pub suggested_duration: Option<GrantDuration>,
}

/// Response sent by L7 → Rust via `policy.respond_approval`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalResponse {
    /// The ticket being resolved.
    pub ticket_id: ApprovalTicketId,
    /// What the user chose.
    pub user_choice: UserChoice,
    /// L7 clock at time of response (for latency audit).
    pub responded_at: MonotonicTimestamp,
    /// Optional explicit scope narrower than the ticket (e.g. one file, not folder).
    pub scope_override: Option<ResourceScope>,
    /// Optional TTL override (if the UI offered a picker).
    pub duration_override: Option<GrantDuration>,
    /// Required for High / Critical capabilities (re-auth gate).
    pub reauth_token: Option<CommandToken>,
}

/// What the user picked.
///
/// `DeferToDraft` is the user-choice path that resolves to
/// `Decision::DraftOnly { source: UserChoice }` server-side (Decision 2).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum UserChoice {
    /// Allow once.
    Allow,
    /// Allow within a narrower scope than the ticket.
    AllowScope(ResourceScope),
    /// Allow for the duration of the current task.
    AllowTask,
    /// Allow for the duration of the current session.
    AllowSession,
    /// Deny.
    Deny,
    /// User chose "Draft only" — no side effects.
    DeferToDraft,
}
