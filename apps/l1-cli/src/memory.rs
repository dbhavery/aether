//! Demo-side wiring for L2.1 turn-scoped conversation memory.
//!
//! The demo app is allowed to depend on both L1 and L2; L1 itself stays
//! persona- and memory-agnostic (see `CLAUDE.md` §1.4 and the layer-boundary
//! linter). This module implements two tiny pieces:
//!
//! 1. [`MemoryAwareRouter`] — an `aether_l1_interaction::TurnRouter` that
//!    reads the recent transcript for a fixed session id, prepends it to the
//!    prompt, and hands the result to an inner router. It never writes; the
//!    main loop appends records after each turn so memory lifecycle stays
//!    explicit at the orchestration layer.
//!
//! 2. [`summarise_turn_for_memory`] — maps a `TurnResult` into a short
//!    assistant/system string to append, whether the turn was allowed or
//!    blocked.

use std::sync::Arc;

use aether_l1_interaction::{L1Error, RouteOutcome, TurnId, TurnRequest, TurnResult, TurnRouter};
use aether_l2_memory::{
    render_transcript, MemoryRole, RecentMemoryWindow, SessionMemoryStore, TurnMemoryRecord,
};
use aether_l5_policy::Decision;

/// `TurnRouter` wrapper that injects a rendered transcript before calling an
/// inner router. Session-scoped; a new instance is created per session.
pub struct MemoryAwareRouter<R: TurnRouter> {
    inner: R,
    store: Arc<dyn SessionMemoryStore>,
    session_id: String,
}

impl<R: TurnRouter> MemoryAwareRouter<R> {
    /// Wrap `inner` with memory-aware prompt preparation for `session_id`.
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

    /// Build the prompt actually sent to the inner router: transcript block
    /// (if any) followed by a labelled `User:` line for the current utterance.
    /// Deterministic and side-effect-free so tests can assert against it.
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

/// Pick a short string to append to memory for the assistant/system side of
/// a turn. On Allow we store the route response; on any block we store a
/// system note so the next turn's transcript shows continuity even across
/// refusals.
pub fn summarise_turn_for_memory(result: &TurnResult) -> (MemoryRole, String) {
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
            "capability not in active preset (upgrade required)".to_string()
        }
        Some(aether_l1_interaction::BlockReason::DraftOnly) => {
            "draft-only — no side effects permitted".to_string()
        }
        None => format!("turn ended in state {:?}", result.final_state),
    };
    (MemoryRole::System, note)
}

/// Build a [`TurnMemoryRecord`] for the user side of a turn, using the
/// request's monotonic timestamp as a cheap proxy for wall-clock. Real apps
/// should pass an actual epoch-ms clock.
pub fn user_record(session_id: &str, request: &TurnRequest) -> TurnMemoryRecord {
    TurnMemoryRecord {
        session_id: session_id.to_string(),
        sequence: 0,
        role: MemoryRole::User,
        content: request.original_utterance.clone(),
        timestamp_ms: request.emitted_at.0,
    }
}

/// Build a [`TurnMemoryRecord`] for the assistant/system side of a turn.
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

#[cfg(test)]
mod tests {
    use super::*;
    use aether_l2_memory::InMemorySessionMemoryStore;
    use std::sync::Mutex;

    /// Router stub that records every prompt it receives and returns a fixed
    /// response.
    struct CapturingRouter {
        last: Mutex<Option<String>>,
        all: Mutex<Vec<String>>,
    }

    impl CapturingRouter {
        fn new() -> Self {
            Self {
                last: Mutex::new(None),
                all: Mutex::new(Vec::new()),
            }
        }
        fn last_prompt(&self) -> Option<String> {
            self.last.lock().unwrap().clone()
        }
        fn prompts(&self) -> Vec<String> {
            self.all.lock().unwrap().clone()
        }
    }

    impl TurnRouter for CapturingRouter {
        fn dispatch(
            &self,
            _turn_id: &TurnId,
            prompt: &str,
            _decision: &Decision,
        ) -> Result<RouteOutcome, L1Error> {
            *self.last.lock().unwrap() = Some(prompt.to_string());
            self.all.lock().unwrap().push(prompt.to_string());
            Ok(RouteOutcome {
                tier: "reflex".to_string(),
                provider: "test".to_string(),
                response_text: "ok".to_string(),
                latency_ms: None,
                tokens: None,
            })
        }
    }

    fn allow_decision() -> Decision {
        Decision::Allow {
            grant_ref: None,
            audit_id: aether_l5_policy::AuditId("audit-1".to_string()),
        }
    }

    /// Shim so a single `Arc<CapturingRouter>` can be owned by the
    /// `MemoryAwareRouter` while the test retains a clone for assertions.
    struct ArcRouter(Arc<CapturingRouter>);
    impl TurnRouter for ArcRouter {
        fn dispatch(
            &self,
            turn_id: &TurnId,
            prompt: &str,
            decision: &Decision,
        ) -> Result<RouteOutcome, L1Error> {
            self.0.dispatch(turn_id, prompt, decision)
        }
    }

    #[test]
    fn build_prompt_with_empty_window_returns_raw_utterance() {
        let w = RecentMemoryWindow {
            session_id: "s".into(),
            records: vec![],
        };
        let p = MemoryAwareRouter::<ArcRouter>::build_prompt(&w, "hello");
        assert_eq!(p, "hello");
    }

    #[test]
    fn build_prompt_prepends_rendered_transcript_and_user_line() {
        let store = InMemorySessionMemoryStore::new_default();
        store
            .append(TurnMemoryRecord {
                session_id: "s".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "ping".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        store
            .append(TurnMemoryRecord {
                session_id: "s".into(),
                sequence: 0,
                role: MemoryRole::Assistant,
                content: "pong".into(),
                timestamp_ms: 2,
            })
            .unwrap();
        let w = store.recent("s").unwrap();
        let p = MemoryAwareRouter::<ArcRouter>::build_prompt(&w, "again");
        assert!(p.contains("Recent conversation:"));
        assert!(p.contains("- User: ping"));
        assert!(p.contains("- Companion: pong"));
        assert!(p.ends_with("User: again"));
    }

    #[test]
    fn second_turn_prompt_contains_first_turn_content() {
        // Integration-style: wire MemoryAwareRouter over a capturing inner
        // router, drive two sequential turns with explicit memory appends
        // between them, and confirm the second prompt sees the first turn.
        let cap = Arc::new(CapturingRouter::new());

        let store: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        let router = MemoryAwareRouter::new(ArcRouter(cap.clone()), store.clone(), "sess-1");

        let t1 = TurnId("turn-1".into());
        let d = allow_decision();

        // Turn 1: user says "what's the weather". Dispatch, then append both
        // sides to memory (main-loop responsibility).
        let out1 = router.dispatch(&t1, "what's the weather", &d).unwrap();
        assert_eq!(out1.response_text, "ok");
        store
            .append(TurnMemoryRecord {
                session_id: "sess-1".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "what's the weather".into(),
                timestamp_ms: 1,
            })
            .unwrap();
        store
            .append(TurnMemoryRecord {
                session_id: "sess-1".into(),
                sequence: 0,
                role: MemoryRole::Assistant,
                content: out1.response_text.clone(),
                timestamp_ms: 2,
            })
            .unwrap();

        // Turn 2: user says "and tomorrow". The dispatch should see the
        // rendered transcript of turn 1 prepended.
        let t2 = TurnId("turn-2".into());
        let _out2 = router.dispatch(&t2, "and tomorrow", &d).unwrap();

        let prompts = cap.prompts();
        assert_eq!(prompts.len(), 2);
        assert_eq!(prompts[0], "what's the weather"); // no history yet
        let p2 = &prompts[1];
        assert!(p2.contains("- User: what's the weather"), "got: {p2}");
        assert!(p2.contains("- Companion: ok"), "got: {p2}");
        assert!(p2.ends_with("User: and tomorrow"), "got: {p2}");
    }

    #[test]
    fn different_sessions_do_not_see_each_others_memory() {
        let cap = Arc::new(CapturingRouter::new());
        let store: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());

        let r_a = MemoryAwareRouter::new(ArcRouter(cap.clone()), store.clone(), "A");
        let r_b = MemoryAwareRouter::new(ArcRouter(cap.clone()), store.clone(), "B");
        let d = allow_decision();

        r_a.dispatch(&TurnId("t".into()), "first-in-A", &d).unwrap();
        store
            .append(TurnMemoryRecord {
                session_id: "A".into(),
                sequence: 0,
                role: MemoryRole::User,
                content: "first-in-A".into(),
                timestamp_ms: 1,
            })
            .unwrap();

        r_b.dispatch(&TurnId("t".into()), "hello-in-B", &d).unwrap();
        let p = cap.last_prompt().unwrap();
        assert!(!p.contains("first-in-A"), "session B leaked A: {p}");
        assert_eq!(p, "hello-in-B");
    }

    #[test]
    fn summarise_for_allow_uses_route_response() {
        use aether_l1_interaction::TurnState;
        let tr = TurnResult {
            turn_id: TurnId("t".into()),
            final_state: TurnState::Completed,
            policy_decision: allow_decision(),
            route: Some(RouteOutcome {
                tier: "reflex".into(),
                provider: "test".into(),
                response_text: "answer".into(),
                latency_ms: None,
                tokens: None,
            }),
            block: None,
            state_trace: vec![],
        };
        let (role, content) = summarise_turn_for_memory(&tr);
        assert_eq!(role, MemoryRole::Assistant);
        assert_eq!(content, "answer");
    }

    #[test]
    fn summarise_for_deny_uses_system_note() {
        use aether_l1_interaction::{BlockReason, TurnState};
        let tr = TurnResult {
            turn_id: TurnId("t".into()),
            final_state: TurnState::PolicyDenied,
            policy_decision: Decision::Deny {
                reason: aether_l5_policy::DenyReason::FeatureDisabled,
                audit_id: aether_l5_policy::AuditId("a".into()),
            },
            route: None,
            block: Some(BlockReason::Denied),
            state_trace: vec![],
        };
        let (role, content) = summarise_turn_for_memory(&tr);
        assert_eq!(role, MemoryRole::System);
        assert!(content.contains("denied"));
    }
}
