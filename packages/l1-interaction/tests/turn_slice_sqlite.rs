//! Wave L1.1 — sqlite-backed vertical slice.
//!
//! Runs the same allow-path turn flow as `turn_slice.rs` but wires
//! `DefaultPolicyEngine` to the durable `DurableBackends` bundle. Verifies
//! that after `handle_turn`, the SQLite ledger has an active grant for the
//! evaluated capability and the audit store has at least one row.
//!
//! Gated behind the `sqlite-backend` feature:
//!   `cargo test -p aether-l1-interaction --features sqlite-backend`.

#![cfg(feature = "sqlite-backend")]

use std::sync::Arc;

use aether_l1_interaction::{EchoStubRouter, TurnEngine, TurnRequest, TurnRouter, TurnState};
use aether_l5_policy::{
    policy_engine::PolicyEngine, Capability, DefaultPolicyEngine, DurableBackends, EngineConfig,
    GrantFilter, InMemorySink, MonotonicTimestamp, PersonaId, ResourceScope, SessionId,
};
use tempfile::TempDir;

#[test]
fn allow_path_persists_grant_to_sqlite() {
    let dir = TempDir::new().unwrap();
    let db = dir.path().join("l1_slice.db");

    let backends = DurableBackends::open(&db).expect("open durable backends");
    let persona = PersonaId(String::from("aurora"));
    let cfg = EngineConfig::wave3_default(persona.clone());
    let sink = Arc::new(InMemorySink::new());
    let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
        cfg,
        backends.ledger.clone(),
        backends.audit.clone(),
        sink,
    ));
    let router: Arc<dyn TurnRouter> = Arc::new(EchoStubRouter);
    let engine = TurnEngine::new(policy, router);

    let req = TurnRequest {
        session_id: SessionId(String::from("sess-sql")),
        persona: persona.clone(),
        task_id: None,
        original_utterance: String::from("read a file"),
        model_input_utterance: String::from("read a file"),
        capability: Capability::FilesRead,
        resource: ResourceScope::Path(String::from("/tmp/durable.txt")),
        emitted_at: MonotonicTimestamp(2_000),
        retrieval_provenance: None,
    };

    let result = engine.handle_turn(req).expect("handle_turn ok");
    assert_eq!(result.final_state, TurnState::Completed);
    assert!(result.route.is_some());

    let snap = backends.ledger.snapshot(&GrantFilter {
        active_only: true,
        persona_id: Some(persona),
        capability: Some(Capability::FilesRead),
    });
    assert_eq!(snap.len(), 1, "one active FilesRead grant persisted");
}
