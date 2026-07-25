//! Demo-side wiring for the L7.1 approval loop.
//!
//! Turns a `Decision::Ask` returned by `TurnEngine::handle_turn` into a
//! concrete user approval round-trip:
//!
//! 1. Extract the `ApprovalTicket` from the result.
//! 2. Render an `ApprovalPrompt` and delegate to an `ApprovalSurface`.
//! 3. Call `PolicyEngine::respond_approval` with the user's choice.
//! 4. On approve, re-run `handle_turn` with the original request — the
//!    freshly issued grant now covers the action, so the next evaluate
//!    returns `Decision::Allow` and the turn completes through the router.
//! 5. On reject, synthesise a denied-shape `TurnResult` that carries the
//!    original turn id so downstream (memory, print) sees one logical turn.
//!
//! This module owns the orchestration; `aether-l7-trust` owns the typed
//! resolution surface; `aether-l5-policy` owns the underlying grant issue /
//! respond mechanics. Neither L1 nor L5 needs to know about the demo's
//! stdin behaviour.

use std::sync::Arc;

use aether_l1_interaction::{BlockReason, TurnEngine, TurnRequest, TurnResult, TurnState};
use aether_l5_policy::{policy_engine::PolicyEngine, Decision, MonotonicTimestamp};
use aether_l7_trust::{
    approval_prompt_from_ticket, build_approval_response, ApprovalResolution, ApprovalSurface,
};

/// Outcome of the approval round-trip. Always ends in a `TurnResult` so the
/// caller can treat `Ask + approval` as a single logical turn.
#[derive(Debug)]
pub struct ApprovalOutcome {
    /// The final turn result (either the post-approval allowed result, or a
    /// synthesised denied result).
    pub result: TurnResult,
    /// Whether the user approved.
    pub approved: bool,
}

/// Drive the Ask-approval loop end-to-end.
///
/// - `policy`: used to call `respond_approval`.
/// - `engine`: used to re-run the turn after an approve.
/// - `surface`: the approval UX (real CLI, scripted test, future desktop bridge).
/// - `original_request`: the exact request that triggered the Ask; replayed
///   on approve so the covering grant hits.
/// - `ask_result`: the `TurnResult` returned by the first `handle_turn` call
///   — must carry a `Decision::Ask { ticket, .. }`.
/// - `responded_at`: monotonic clock the demo is already threading.
pub fn handle_ask(
    policy: &Arc<dyn PolicyEngine>,
    engine: &TurnEngine,
    surface: &dyn ApprovalSurface,
    original_request: TurnRequest,
    ask_result: TurnResult,
    responded_at: MonotonicTimestamp,
) -> Result<ApprovalOutcome, String> {
    let ticket = match &ask_result.policy_decision {
        Decision::Ask { ticket, .. } => ticket.clone(),
        other => return Err(format!("handle_ask called on non-Ask decision: {other:?}")),
    };

    let prompt = approval_prompt_from_ticket(ticket.clone(), None);
    let resolution = surface
        .resolve(&prompt)
        .map_err(|e| format!("approval surface failed: {e}"))?;
    let response = build_approval_response(&ticket, resolution, responded_at);
    policy
        .respond_approval(response)
        .map_err(|e| format!("respond_approval failed: {e}"))?;

    match resolution {
        ApprovalResolution::Approve => {
            // Re-run the same request. The fresh grant now covers it, so
            // evaluate should land in Allow and the router dispatches.
            let result = engine
                .handle_turn(original_request)
                .map_err(|e| format!("post-approval handle_turn failed: {e}"))?;
            Ok(ApprovalOutcome {
                result,
                approved: true,
            })
        }
        ApprovalResolution::Reject => {
            // User denied. Synthesise a denied `TurnResult` tied to the
            // original turn id so downstream printing / memory sees a single
            // logical turn. We cannot easily re-use the synthesised Deny
            // decision from the policy engine (respond_approval returns only
            // a `ChangeId`), so we reconstruct a faithful view locally using
            // the ticket's audit id.
            let audit_id = match &ask_result.policy_decision {
                Decision::Ask { audit_id, .. } => audit_id.clone(),
                _ => unreachable!("checked above"),
            };
            let denied = Decision::Deny {
                reason: aether_l5_policy::DenyReason::ModeDeny,
                audit_id,
            };
            let mut trace = ask_result.state_trace.clone();
            trace.push(TurnState::PolicyDenied);
            Ok(ApprovalOutcome {
                result: TurnResult {
                    turn_id: ask_result.turn_id.clone(),
                    final_state: TurnState::PolicyDenied,
                    policy_decision: denied,
                    route: None,
                    block: Some(BlockReason::Denied),
                    state_trace: trace,
                },
                approved: false,
            })
        }
    }
}

/// Narrow helper — is this result an Ask that needs an approval loop?
pub fn is_ask(result: &TurnResult) -> bool {
    matches!(&result.policy_decision, Decision::Ask { .. })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::adapter::{ModelRouterAdapter, ReflexModelRouter};
    use crate::memory::MemoryAwareRouter;
    use aether_l1_interaction::{TurnEngine, TurnRouter};
    use aether_l2_memory::{InMemorySessionMemoryStore, SessionMemoryStore};
    use aether_l4_router::RouterTier;
    use aether_l5_policy::{
        Capability, DefaultPolicyEngine, EngineConfig, InMemoryAuditStore, InMemoryGrantLedger,
        InMemorySink, MonotonicTimestamp, PersonaId, ResourceScope, SessionId,
    };
    use aether_l7_trust::FixedApprovalSurface;
    use std::sync::Arc;

    fn build_stack(
        resolution: ApprovalResolution,
    ) -> (
        Arc<dyn PolicyEngine>,
        TurnEngine,
        Arc<dyn SessionMemoryStore>,
        FixedApprovalSurface,
    ) {
        let persona = PersonaId("aurora".to_string());
        let cfg = EngineConfig::wave3_default(persona);
        let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
            cfg,
            Arc::new(InMemoryGrantLedger::new()),
            Arc::new(InMemoryAuditStore::new()),
            Arc::new(InMemorySink::new()),
        ));
        let store: Arc<dyn SessionMemoryStore> =
            Arc::new(InMemorySessionMemoryStore::new_default());
        let adapter =
            ModelRouterAdapter::new(ReflexModelRouter::new(), "reflex-stub", RouterTier::Reflex);
        let memory_router = MemoryAwareRouter::new(adapter, store.clone(), "test-session");
        let router: Arc<dyn TurnRouter> = Arc::new(memory_router);
        let engine = TurnEngine::new(policy.clone(), router);
        (policy, engine, store, FixedApprovalSurface(resolution))
    }

    fn files_create_request() -> TurnRequest {
        TurnRequest {
            session_id: SessionId("test-session".to_string()),
            persona: PersonaId("aurora".to_string()),
            task_id: None,
            original_utterance: "write /tmp/foo".to_string(),
            model_input_utterance: "write /tmp/foo".to_string(),
            capability: Capability::FilesCreate,
            resource: ResourceScope::Path("/tmp/foo".to_string()),
            emitted_at: MonotonicTimestamp(1),
            retrieval_provenance: None,
        }
    }

    #[test]
    fn ask_then_approve_resumes_turn_to_allow_via_grant() {
        let (policy, engine, _store, surface) = build_stack(ApprovalResolution::Approve);
        let req = files_create_request();

        // First turn: FilesCreate is Ask in wave3 preset.
        let first = engine.handle_turn(req.clone()).unwrap();
        assert!(is_ask(&first), "first turn should be Ask: {:?}", first);

        let outcome = handle_ask(
            &policy,
            &engine,
            &surface,
            req,
            first,
            MonotonicTimestamp(2),
        )
        .unwrap();
        assert!(outcome.approved);
        assert!(
            matches!(outcome.result.policy_decision, Decision::Allow { .. }),
            "post-approval should be Allow: {:?}",
            outcome.result.policy_decision
        );
        let route = outcome.result.route.expect("allow should dispatch router");
        assert!(route.response_text.contains("write /tmp/foo"));
    }

    #[test]
    fn ask_then_reject_yields_denied_result() {
        let (policy, engine, _store, surface) = build_stack(ApprovalResolution::Reject);
        let req = files_create_request();
        let first = engine.handle_turn(req.clone()).unwrap();
        assert!(is_ask(&first));

        let outcome = handle_ask(
            &policy,
            &engine,
            &surface,
            req,
            first,
            MonotonicTimestamp(2),
        )
        .unwrap();
        assert!(!outcome.approved);
        assert!(matches!(
            outcome.result.policy_decision,
            Decision::Deny { .. }
        ));
        assert_eq!(outcome.result.block, Some(BlockReason::Denied));
        assert!(outcome.result.route.is_none());
    }

    #[test]
    fn handle_ask_rejects_non_ask_results() {
        let (policy, engine, _store, surface) = build_stack(ApprovalResolution::Approve);
        // Synthesise a fake Allow result to feed in — handle_ask must refuse it.
        let allow_result = TurnResult {
            turn_id: aether_l1_interaction::TurnId("t".into()),
            final_state: TurnState::Completed,
            policy_decision: Decision::Allow {
                grant_ref: None,
                audit_id: aether_l5_policy::AuditId("a".into()),
            },
            route: None,
            block: None,
            state_trace: vec![],
        };
        let err = handle_ask(
            &policy,
            &engine,
            &surface,
            files_create_request(),
            allow_result,
            MonotonicTimestamp(2),
        )
        .unwrap_err();
        assert!(err.contains("non-Ask"));
    }
}
