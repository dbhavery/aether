//! Memory-aware router wrapper. Mirrors `apps/l1-cli/src/memory.rs` — kept
//! per-app so the shell stays standalone. On each dispatch it loads the
//! recent window from L2 and prepends a rendered transcript before
//! forwarding to the inner router. L1 itself stays memory-agnostic.

use std::sync::Arc;

use aether_l1_interaction::{L1Error, RouteOutcome, TurnId, TurnRequest, TurnResult, TurnRouter};
use aether_l2_memory::{
    render_transcript, MemoryRole, RecentMemoryWindow, SessionMemoryStore, TurnMemoryRecord,
};
use aether_l5_policy::Decision;

pub struct MemoryAwareRouter<R: TurnRouter> {
    inner: R,
    store: Arc<dyn SessionMemoryStore>,
    session_id: String,
}

impl<R: TurnRouter> MemoryAwareRouter<R> {
    pub fn new(
        inner: R,
        store: Arc<dyn SessionMemoryStore>,
        session_id: impl Into<String>,
    ) -> Self {
        Self {
            inner,
            store,
            session_id: session_id.into(),
        }
    }

    pub fn build_prompt(window: &RecentMemoryWindow, utterance: &str) -> String {
        let head = render_transcript(window);
        if head.is_empty() {
            utterance.to_string()
        } else {
            let mut out = String::with_capacity(head.len() + utterance.len() + 16);
            out.push_str(&head);
            out.push_str("User: ");
            out.push_str(utterance);
            out
        }
    }
}

impl<R: TurnRouter> TurnRouter for MemoryAwareRouter<R> {
    fn dispatch(
        &self,
        turn_id: &TurnId,
        prompt: &str,
        decision: &Decision,
    ) -> Result<RouteOutcome, L1Error> {
        let window = self
            .store
            .recent(&self.session_id)
            .map_err(|e| L1Error::Router(format!("memory recall failed: {e}")))?;
        let combined = Self::build_prompt(&window, prompt);
        self.inner.dispatch(turn_id, &combined, decision)
    }
}

/// Append the user side of a turn to memory.
pub fn user_record(session_id: &str, request: &TurnRequest) -> TurnMemoryRecord {
    TurnMemoryRecord {
        session_id: session_id.to_string(),
        sequence: 0,
        role: MemoryRole::User,
        content: request.utterance.clone(),
        timestamp_ms: request.emitted_at.0,
    }
}

/// Append the assistant or system side of a turn to memory. On Allow the
/// assistant text is the route response; on any block the content is a
/// short system note so transcript continuity survives refusals.
pub fn assistant_record(session_id: &str, result: &TurnResult, ts_ms: u64) -> TurnMemoryRecord {
    let (role, content) = summarise_turn_for_memory(result);
    TurnMemoryRecord {
        session_id: session_id.to_string(),
        sequence: 0,
        role,
        content,
        timestamp_ms: ts_ms,
    }
}

fn summarise_turn_for_memory(result: &TurnResult) -> (MemoryRole, String) {
    if let Some(route) = &result.route {
        return (MemoryRole::Assistant, route.response_text.clone());
    }
    let note = match &result.block {
        Some(aether_l1_interaction::BlockReason::AwaitingApproval) => {
            "awaiting user approval for the last request".to_string()
        }
        Some(aether_l1_interaction::BlockReason::Denied) => {
            "policy denied that request".to_string()
        }
        Some(aether_l1_interaction::BlockReason::NeedsUpgrade) => {
            "capability not in active preset".to_string()
        }
        Some(aether_l1_interaction::BlockReason::DraftOnly) => {
            "draft-only — no side effects permitted".to_string()
        }
        None => format!("turn ended in state {:?}", result.final_state),
    };
    (MemoryRole::System, note)
}
