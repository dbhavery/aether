//! Wave L1.1 vertical-slice tests.
//!
//! Exercise `TurnEngine::handle_turn` end-to-end against a real
//! `DefaultPolicyEngine` (in-memory backends) and a stub router.

use std::sync::Arc;

use aether_l1_interaction::{
    BlockReason, EchoStubRouter, TurnEngine, TurnRequest, TurnRouter, TurnState,
};
use aether_l5_policy::{
    Capability, Decision, DefaultPolicyEngine, EngineConfig, InMemoryAuditStore,
    InMemoryGrantLedger, InMemorySink, MonotonicTimestamp, PersonaId, ResourceScope, SessionId,
};

fn build_policy() -> Arc<DefaultPolicyEngine> {
    let persona = PersonaId(String::from("aurora"));
    let cfg = EngineConfig::wave3_default(persona);
    let ledger = Arc::new(InMemoryGrantLedger::new());
    let audit = Arc::new(InMemoryAuditStore::new());
    let sink = Arc::new(InMemorySink::new());
    Arc::new(DefaultPolicyEngine::new(cfg, ledger, audit, sink))
}

fn request(cap: Capability, resource: ResourceScope) -> TurnRequest {
    TurnRequest {
        session_id: SessionId(String::from("sess-1")),
        persona: PersonaId(String::from("aurora")),
        task_id: None,
        original_utterance: String::from("hello aether"),
        model_input_utterance: String::from("hello aether"),
        capability: cap,
        resource,
        emitted_at: MonotonicTimestamp(1_000),
        retrieval_provenance: None,
    }
}

#[test]
fn allow_path_reaches_router_and_completes() {
    let policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine> = build_policy();
    let router: Arc<dyn TurnRouter> = Arc::new(EchoStubRouter);
    let engine = TurnEngine::new(policy, router);

    let result = engine
        .handle_turn(request(
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/x.txt")),
        ))
        .expect("handle_turn should succeed on allow path");

    assert_eq!(result.final_state, TurnState::Completed);
    assert!(matches!(result.policy_decision, Decision::Allow { .. }));
    let route = result.route.expect("route outcome on allow path");
    assert_eq!(route.provider, "stub-echo");
    assert_eq!(route.response_text, "echo: hello aether");
    // Engine-measured latency is always stamped on the Allow path, even
    // when the underlying router reports no latency of its own.
    assert!(
        route.latency_ms.is_some(),
        "latency_ms should be stamped by TurnEngine::handle_turn"
    );
    // Reflex stub does no inference, so no token counts should surface.
    assert!(route.tokens.is_none());
    assert!(result.block.is_none());
    assert_eq!(
        result.state_trace,
        vec![
            TurnState::Idle,
            TurnState::AwaitingPolicyApproval,
            TurnState::RouterDispatched,
            TurnState::Completed,
        ]
    );
}

#[test]
fn deny_path_blocks_before_router() {
    let policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine> = build_policy();
    let router: Arc<dyn TurnRouter> = Arc::new(EchoStubRouter);
    let engine = TurnEngine::new(policy, router);

    // ShellExec is Deny in the wave3 preset.
    let result = engine
        .handle_turn(request(
            Capability::ShellExec,
            ResourceScope::Path(String::from("/bin/echo")),
        ))
        .expect("handle_turn returns Ok even on deny");

    assert_eq!(result.final_state, TurnState::PolicyDenied);
    assert!(matches!(result.policy_decision, Decision::Deny { .. }));
    assert_eq!(result.block, Some(BlockReason::Denied));
    assert!(result.route.is_none());
}

#[test]
fn ask_path_is_terminal_for_this_slice() {
    let policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine> = build_policy();
    let router: Arc<dyn TurnRouter> = Arc::new(EchoStubRouter);
    let engine = TurnEngine::new(policy, router);

    // FilesCreate is Ask in the wave3 preset.
    let result = engine
        .handle_turn(request(
            Capability::FilesCreate,
            ResourceScope::Path(String::from("/tmp/new.txt")),
        ))
        .expect("handle_turn returns Ok on ask path");

    assert_eq!(result.final_state, TurnState::AwaitingPolicyApproval);
    assert!(matches!(result.policy_decision, Decision::Ask { .. }));
    assert_eq!(result.block, Some(BlockReason::AwaitingApproval));
    assert!(result.route.is_none());
}

/// ADR-0009 §Decision 4 + §Decision 5: when the two utterance channels
/// diverge (caller pre-augmented `model_input_utterance` with a retrieval
/// block), the L1 engine forwards EXACTLY `model_input_utterance` to the
/// router. A capturing-router fixture proves the router never sees the
/// `original_utterance` value when the two differ.
#[test]
fn allow_path_forwards_model_input_utterance_not_original() {
    use std::sync::Mutex;

    struct CapturingRouter(Mutex<Option<String>>);
    impl TurnRouter for CapturingRouter {
        fn dispatch(
            &self,
            _turn_id: &aether_l1_interaction::TurnId,
            prompt: &str,
            _decision: &Decision,
        ) -> Result<aether_l1_interaction::RouteOutcome, aether_l1_interaction::L1Error> {
            *self.0.lock().unwrap() = Some(prompt.to_string());
            Ok(aether_l1_interaction::RouteOutcome {
                tier: "reflex".into(),
                provider: "capturing-stub".into(),
                response_text: "ok".into(),
                latency_ms: None,
                tokens: None,
            })
        }
    }

    let policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine> = build_policy();
    let captured = Arc::new(CapturingRouter(Mutex::new(None)));
    let router: Arc<dyn TurnRouter> = captured.clone();
    let engine = TurnEngine::new(policy, router);

    let req = TurnRequest {
        session_id: SessionId(String::from("sess-1")),
        persona: PersonaId(String::from("aurora")),
        task_id: None,
        original_utterance: String::from("what did we say about sourdough?"),
        model_input_utterance: String::from(
            "Relevant context (retrieval):\n- (durable) sourdough starter notes\n\nwhat did we say about sourdough?",
        ),
        capability: Capability::FilesRead,
        resource: ResourceScope::Path(String::from("/tmp/x")),
        emitted_at: MonotonicTimestamp(1_000),
        retrieval_provenance: None,
    };

    let result = engine.handle_turn(req).expect("allow path");
    assert_eq!(result.final_state, TurnState::Completed);

    let prompt_seen = captured
        .0
        .lock()
        .unwrap()
        .clone()
        .expect("router was called");
    assert!(
        prompt_seen.starts_with("Relevant context (retrieval):"),
        "router must receive the augmented model_input, got: {prompt_seen:?}",
    );
    assert!(
        !prompt_seen.eq("what did we say about sourdough?"),
        "router must not receive the bare original_utterance when augmentation is present",
    );
}

#[test]
fn unsupported_capability_returns_needs_upgrade_block() {
    let policy: Arc<dyn aether_l5_policy::policy_engine::PolicyEngine> = build_policy();
    let router: Arc<dyn TurnRouter> = Arc::new(EchoStubRouter);
    let engine = TurnEngine::new(policy, router);

    // BrowserOpen is absent from the wave3 preset.
    let result = engine
        .handle_turn(request(
            Capability::BrowserOpen,
            ResourceScope::Path(String::from("https://example.com")),
        ))
        .expect("handle_turn returns Ok on needs-upgrade path");

    assert_eq!(result.final_state, TurnState::PolicyDenied);
    assert!(matches!(
        result.policy_decision,
        Decision::NeedsUpgrade { .. }
    ));
    assert_eq!(result.block, Some(BlockReason::NeedsUpgrade));
}
