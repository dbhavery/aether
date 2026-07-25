//! Wave L1.1 — first vertical turn FSM slice.
//!
//! This module implements a minimal, real turn state machine that drives one
//! request end-to-end: build an `ActionRequest`, call `PolicyEngine::evaluate`,
//! then either dispatch to a router (stub) or return a blocked result.
//!
//! ## Minimal FSM
//!
//! ```text
//!   Idle
//!     │ handle_turn(req)  (utterance is supplied up front — no audio path yet)
//!     ▼
//!   AwaitingPolicyApproval
//!     │ policy.evaluate(...)
//!     ├── Allow       ─► RouterDispatched ─► Completed
//!     ├── Ask         ─► AwaitingPolicyApproval (terminal for this slice)
//!     ├── DraftOnly   ─► Deflected (terminal for this slice)
//!     ├── Deny        ─► PolicyDenied (terminal)
//!     └── NeedsUpgrade─► PolicyDenied (terminal)
//! ```
//!
//! The 19-state enum in `engine.rs` is a superset. This slice only touches
//! the states the vertical path actually needs; future waves fill in Listening,
//! EndOfUserSpeech, ReflexClassifying, Drafting, Speaking, BargeIn, Repairing,
//! TimedOut, Errored.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use serde::{Deserialize, Serialize};

use aether_l5_policy::{
    policy_engine::{ActionRequest, PolicyEngine},
    Capability, Decision, MonotonicTimestamp, PersonaId, RequestId, ResourceScope, SessionId,
    TaskId,
};

use crate::engine::{TurnId, TurnState};
use crate::error::L1Error;

/// A single-turn request flowing into L1. The input is deliberately narrow:
/// one utterance, one session, one persona, one target capability + resource.
/// Broader shape (intent hints, multi-turn context, media tracks) lands in
/// later waves.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TurnRequest {
    /// Session correlation.
    pub session_id: SessionId,
    /// Persona acting on this turn.
    pub persona: PersonaId,
    /// Optional task correlation for task-scoped grants.
    pub task_id: Option<TaskId>,
    /// Raw user utterance.
    pub utterance: String,
    /// Capability the turn intends to invoke.
    pub capability: Capability,
    /// Target resource scope.
    pub resource: ResourceScope,
    /// Monotonic emit time. Callers that don't care can pass
    /// `MonotonicTimestamp(0)`.
    pub emitted_at: MonotonicTimestamp,
}

/// What the router reported after a successful dispatch. Strings are used here
/// so L1 need not import L4 types (layer-boundary rule §1.4 of the repo
/// CLAUDE.md); the stub or real router is free to project its own richer
/// types into this shape.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RouteOutcome {
    /// Router tier label (e.g. `"reflex"`, `"local-small"`, `"remote-standard"`).
    pub tier: String,
    /// Provider id (e.g. `"stub-echo"`).
    pub provider: String,
    /// Final text response surfaced to the caller.
    pub response_text: String,
}

/// Why a turn ended without reaching the router.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum BlockReason {
    /// L5 returned `Ask`; user approval is required before proceeding.
    AwaitingApproval,
    /// L5 returned `Deny` or a degraded-mode refusal.
    Denied,
    /// L5 returned `NeedsUpgrade`.
    NeedsUpgrade,
    /// L5 returned `DraftOnly`; execution must not produce side effects.
    DraftOnly,
}

/// Structured result of a single `handle_turn` invocation. Successful and
/// blocked outcomes share one type so callers can branch on `final_state`
/// without unwrapping two layers of `Result`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TurnResult {
    /// Turn id allocated by the engine.
    pub turn_id: TurnId,
    /// Terminal turn-state this turn ended in.
    pub final_state: TurnState,
    /// Policy decision returned by L5 (always present; every path calls L5).
    pub policy_decision: Decision,
    /// Router outcome if the Allow path was reached.
    pub route: Option<RouteOutcome>,
    /// Block reason if the turn stopped before reaching the router.
    pub block: Option<BlockReason>,
    /// Ordered trace of state transitions this turn went through. Useful for
    /// test assertions and future tracing export.
    pub state_trace: Vec<TurnState>,
}

/// Minimal router interface consumed by L1 for this vertical slice.
///
/// L1 does **not** depend on `aether-l4-router` — that would be a forbidden
/// sibling-to-sibling edge. Instead, L1 defines this narrow trait and the
/// caller (an app binary, an integration test, or a future orchestration
/// layer) supplies an implementation. A real L4 adapter lives outside L1.
pub trait TurnRouter: Send + Sync {
    /// Dispatch a prompt for a turn that L5 has already allowed. The
    /// `decision` is passed in so the router can honour grant/audit context
    /// without re-calling L5.
    fn dispatch(
        &self,
        turn_id: &TurnId,
        prompt: &str,
        decision: &Decision,
    ) -> Result<RouteOutcome, L1Error>;
}

/// Turn orchestration engine. Owns monotonic counters for turn/request ids
/// and the two injected collaborators it needs to complete a turn end-to-end.
pub struct TurnEngine {
    policy: Arc<dyn PolicyEngine>,
    router: Arc<dyn TurnRouter>,
    turn_ctr: AtomicU64,
    request_ctr: AtomicU64,
}

impl TurnEngine {
    /// Construct a new engine.
    pub fn new(policy: Arc<dyn PolicyEngine>, router: Arc<dyn TurnRouter>) -> Self {
        Self {
            policy,
            router,
            turn_ctr: AtomicU64::new(1),
            request_ctr: AtomicU64::new(1),
        }
    }

    /// Drive one turn through the minimal FSM.
    pub fn handle_turn(&self, request: TurnRequest) -> Result<TurnResult, L1Error> {
        let turn_id = self.next_turn_id();
        let mut trace: Vec<TurnState> = Vec::with_capacity(5);

        trace.push(TurnState::Idle);
        trace.push(TurnState::AwaitingPolicyApproval);

        let action = ActionRequest {
            request_id: self.next_request_id(),
            turn_id: aether_l5_policy::common::TurnId(turn_id.0.clone()),
            capability: request.capability.clone(),
            resource: request.resource.clone(),
            actor_persona: request.persona.clone(),
            emitted_at: request.emitted_at,
            task_id: request.task_id.clone(),
            provenance_tags: Vec::new(),
            intended_route: None,
            risk_class_hint: None,
        };

        let decision = self
            .policy
            .evaluate(action)
            .map_err(|e| L1Error::Policy(e.to_string()))?;

        match &decision {
            Decision::Allow { .. } => {
                trace.push(TurnState::RouterDispatched);
                let outcome = self
                    .router
                    .dispatch(&turn_id, &request.utterance, &decision)?;
                trace.push(TurnState::Completed);
                Ok(TurnResult {
                    turn_id,
                    final_state: TurnState::Completed,
                    policy_decision: decision,
                    route: Some(outcome),
                    block: None,
                    state_trace: trace,
                })
            }
            Decision::Ask { .. } => {
                // Terminal for this slice — approval UX lives in L7; the next
                // wave will re-enter the FSM via `respond_approval` and drive
                // the follow-on evaluate → dispatch arc.
                Ok(TurnResult {
                    turn_id,
                    final_state: TurnState::AwaitingPolicyApproval,
                    policy_decision: decision,
                    route: None,
                    block: Some(BlockReason::AwaitingApproval),
                    state_trace: trace,
                })
            }
            Decision::Deny { .. } => {
                trace.push(TurnState::PolicyDenied);
                Ok(TurnResult {
                    turn_id,
                    final_state: TurnState::PolicyDenied,
                    policy_decision: decision,
                    route: None,
                    block: Some(BlockReason::Denied),
                    state_trace: trace,
                })
            }
            Decision::NeedsUpgrade { .. } => {
                trace.push(TurnState::PolicyDenied);
                Ok(TurnResult {
                    turn_id,
                    final_state: TurnState::PolicyDenied,
                    policy_decision: decision,
                    route: None,
                    block: Some(BlockReason::NeedsUpgrade),
                    state_trace: trace,
                })
            }
            Decision::DraftOnly { .. } => {
                trace.push(TurnState::Deflected);
                Ok(TurnResult {
                    turn_id,
                    final_state: TurnState::Deflected,
                    policy_decision: decision,
                    route: None,
                    block: Some(BlockReason::DraftOnly),
                    state_trace: trace,
                })
            }
        }
    }

    fn next_turn_id(&self) -> TurnId {
        TurnId(format!(
            "turn-{}",
            self.turn_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }

    fn next_request_id(&self) -> RequestId {
        RequestId(format!(
            "req-{}",
            self.request_ctr.fetch_add(1, Ordering::Relaxed)
        ))
    }
}

/// Trivial echo router used in tests and dev harnesses. Always succeeds, always
/// returns a reflex-tier "echo" response. Callers that want a different stub
/// behaviour can implement `TurnRouter` directly.
pub struct EchoStubRouter;

impl TurnRouter for EchoStubRouter {
    fn dispatch(
        &self,
        _turn_id: &TurnId,
        prompt: &str,
        _decision: &Decision,
    ) -> Result<RouteOutcome, L1Error> {
        Ok(RouteOutcome {
            tier: String::from("reflex"),
            provider: String::from("stub-echo"),
            response_text: format!("echo: {prompt}"),
        })
    }
}
