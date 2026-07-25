//! Demo-side wiring for L3.1 session presence.
//!
//! Keeps the main loop's presence bookkeeping in one testable place. The
//! `PresenceController` itself lives in `aether-l3-presence` — this module
//! only encodes the transitions the CLI wants.

use std::sync::Arc;

use aether_l1_interaction::TurnResult;
use aether_l3_presence::{PresenceController, PresenceState};
use aether_l5_policy::Decision;

/// Drive a full non-Ask turn through presence: Listening → Thinking →
/// Responding → Quiet. Each transition is recorded with the supplied
/// timestamp so tests can assert ordering by sequence.
///
/// Returns the resulting list of `PresenceState` the controller now holds
/// for `session_id`, oldest-first, for test assertions. Errors are bubbled.
pub fn drive_allow_turn_presence(
    presence: &Arc<dyn PresenceController>,
    session_id: &str,
    base_ts_ms: u64,
) -> Result<Vec<PresenceState>, aether_l3_presence::L3Error> {
    presence.set_state(session_id, PresenceState::Listening, base_ts_ms, None)?;
    presence.set_state(session_id, PresenceState::Thinking, base_ts_ms + 1, None)?;
    presence.set_state(session_id, PresenceState::Responding, base_ts_ms + 2, None)?;
    presence.set_state(session_id, PresenceState::Quiet, base_ts_ms + 3, None)?;
    Ok(presence
        .recent_transitions(session_id)?
        .into_iter()
        .map(|s| s.state)
        .collect())
}

/// Drive an Ask turn through presence where approval happened mid-turn:
/// Listening → Thinking → AwaitingApproval → Responding → Quiet (approved)
/// or Listening → Thinking → AwaitingApproval → Quiet (rejected).
pub fn drive_ask_turn_presence(
    presence: &Arc<dyn PresenceController>,
    session_id: &str,
    base_ts_ms: u64,
    result: &TurnResult,
    approved: bool,
) -> Result<Vec<PresenceState>, aether_l3_presence::L3Error> {
    presence.set_state(session_id, PresenceState::Listening, base_ts_ms, None)?;
    presence.set_state(session_id, PresenceState::Thinking, base_ts_ms + 1, None)?;
    let ticket_detail = match &result.policy_decision {
        Decision::Ask { ticket, .. } => Some(ticket.ticket_id.0.clone()),
        _ => None,
    };
    presence.set_state(
        session_id,
        PresenceState::AwaitingApproval,
        base_ts_ms + 2,
        ticket_detail,
    )?;
    if approved {
        presence.set_state(session_id, PresenceState::Responding, base_ts_ms + 3, None)?;
    }
    presence.set_state(session_id, PresenceState::Quiet, base_ts_ms + 4, None)?;
    Ok(presence
        .recent_transitions(session_id)?
        .into_iter()
        .map(|s| s.state)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l3_presence::InMemoryPresenceController;

    #[test]
    fn allow_turn_sequence_matches_expected_states() {
        let c: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let seq = drive_allow_turn_presence(&c, "s", 100).unwrap();
        assert_eq!(
            seq,
            vec![
                PresenceState::Listening,
                PresenceState::Thinking,
                PresenceState::Responding,
                PresenceState::Quiet,
            ]
        );
    }

    #[test]
    fn ask_approved_sequence_includes_awaiting_then_responding() {
        use aether_l1_interaction::{TurnId, TurnState};
        use aether_l5_policy::{
            ApprovalTicket, ApprovalTicketId, AuditId, Capability, RequestId, ResourceScope,
        };

        let ticket = ApprovalTicket {
            ticket_id: ApprovalTicketId("tk-1".into()),
            request_id: RequestId("r".into()),
            capability: Capability::FilesCreate,
            resource: ResourceScope::Path("/tmp".into()),
            deadline_hint: None,
            suggested_duration: None,
        };
        let ask = TurnResult {
            turn_id: TurnId("t".into()),
            final_state: TurnState::AwaitingPolicyApproval,
            policy_decision: Decision::Ask {
                ticket,
                audit_id: AuditId("a".into()),
            },
            route: None,
            block: Some(aether_l1_interaction::BlockReason::AwaitingApproval),
            state_trace: vec![],
        };

        let c: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let seq = drive_ask_turn_presence(&c, "s", 0, &ask, true).unwrap();
        assert_eq!(
            seq,
            vec![
                PresenceState::Listening,
                PresenceState::Thinking,
                PresenceState::AwaitingApproval,
                PresenceState::Responding,
                PresenceState::Quiet,
            ]
        );
        // Detail carries the ticket id.
        let log = c.recent_transitions("s").unwrap();
        assert_eq!(log[2].detail.as_deref(), Some("tk-1"));
    }

    #[test]
    fn ask_rejected_sequence_skips_responding() {
        use aether_l1_interaction::{TurnId, TurnState};
        use aether_l5_policy::{
            ApprovalTicket, ApprovalTicketId, AuditId, Capability, RequestId, ResourceScope,
        };

        let ticket = ApprovalTicket {
            ticket_id: ApprovalTicketId("tk-2".into()),
            request_id: RequestId("r".into()),
            capability: Capability::FilesDelete,
            resource: ResourceScope::Path("/tmp".into()),
            deadline_hint: None,
            suggested_duration: None,
        };
        let ask = TurnResult {
            turn_id: TurnId("t".into()),
            final_state: TurnState::AwaitingPolicyApproval,
            policy_decision: Decision::Ask {
                ticket,
                audit_id: AuditId("a".into()),
            },
            route: None,
            block: Some(aether_l1_interaction::BlockReason::AwaitingApproval),
            state_trace: vec![],
        };

        let c: Arc<dyn PresenceController> = Arc::new(InMemoryPresenceController::new());
        let seq = drive_ask_turn_presence(&c, "s", 0, &ask, false).unwrap();
        assert_eq!(
            seq,
            vec![
                PresenceState::Listening,
                PresenceState::Thinking,
                PresenceState::AwaitingApproval,
                PresenceState::Quiet,
            ]
        );
    }
}
