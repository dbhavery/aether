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

/// Temporal extent over which a user-issued approval applies to subsequent
/// matching actions. Orthogonal to [`crate::grants::ApprovalMode`] (what is
/// approved) and [`crate::grants::GrantDuration`] (calendar-style TTL).
///
/// **Default: [`ApprovalScope::PerAction`].** Every existing call site that
/// does not set this field deserializes / constructs as `PerAction` and so
/// behaves exactly as before this enum landed.
///
/// Per the approval-scope design in `ARCHITECTURE.md`, the four
/// variants are:
///
/// - [`ApprovalScope::PerAction`] — today's default. Every action prompts;
///   no reuse across actions.
/// - [`ApprovalScope::OncePerSession`] — granted for the lifetime of the
///   current session. Resets on app restart or explicit session end.
///   Device-local per ADR-0016 (does not sync across devices).
/// - [`ApprovalScope::OncePerTask`] — granted for the lifetime of the
///   current task (turn-window, identified by `change_id` lineage / task id).
/// - [`ApprovalScope::DraftOnly`] — agent prepares the action artifact;
///   L5 does not dispatch the executor. User reviews and clicks to run —
///   re-entering the policy engine as a fresh request. The user-chosen
///   counterpart of [`crate::decision::DraftSource::UserChoice`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ApprovalScope {
    /// Today's default. Every action prompts; no reuse across actions.
    PerAction,
    /// User granted for the lifetime of the current session.
    OncePerSession,
    /// User granted for the lifetime of the current task.
    OncePerTask,
    /// Agent prepares the artifact; L5 does not dispatch the executor.
    /// User must re-issue an `ActionRequest` to actually run it.
    DraftOnly,
}

impl Default for ApprovalScope {
    fn default() -> Self {
        ApprovalScope::PerAction
    }
}

impl ApprovalScope {
    /// Map a [`UserChoice`] to its persisted, audit-visible
    /// [`ApprovalScope`] per design doc §2.
    ///
    /// | `UserChoice` | `ApprovalScope` |
    /// |---|---|
    /// | `Allow` / `AllowScope(_)` | `PerAction` |
    /// | `AllowSession` | `OncePerSession` |
    /// | `AllowTask` | `OncePerTask` |
    /// | `Deny` | `PerAction` (no grant issues) |
    /// | `DeferToDraft` | `DraftOnly` |
    ///
    /// `UserChoice` is consumed in-memory; `ApprovalScope` is the
    /// projection that survives onto the persisted grant + audit row.
    pub fn from_user_choice(choice: &UserChoice) -> Self {
        match choice {
            UserChoice::Allow | UserChoice::AllowScope(_) => Self::PerAction,
            UserChoice::AllowSession => Self::OncePerSession,
            UserChoice::AllowTask => Self::OncePerTask,
            UserChoice::Deny => Self::PerAction,
            UserChoice::DeferToDraft => Self::DraftOnly,
        }
    }
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
