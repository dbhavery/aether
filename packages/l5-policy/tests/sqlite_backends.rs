//! Wave 4.5 integration tests for the SQLite-backed L5 backends.
//!
//! These tests are only compiled and run when the `sqlite-backend` feature
//! is enabled: `cargo test -p aether-l5-policy --features sqlite-backend`.

#![cfg(feature = "sqlite-backend")]

use std::sync::Arc;

use aether_l5_policy::{
    common::TurnId,
    policy_engine::{ActionRequest, PolicyEngine},
    *,
};
use tempfile::TempDir;

fn temp_db(name: &str) -> (TempDir, std::path::PathBuf) {
    let dir = TempDir::new().unwrap();
    let p = dir.path().join(name);
    (dir, p)
}

/// Round-trip: open a durable backends pair, issue a grant, reopen the DB,
/// confirm the grant survived. This is the single load-bearing invariant
/// Wave 4.5 delivers — the one thing the in-memory path could never do.
#[test]
fn grant_survives_a_process_restart() {
    let (_tmp, path) = temp_db("survive.db");

    let persona = PersonaId("aurora".into());
    let grant = Grant {
        grant_id: GrantId("grant-1".into()),
        capability: Capability::FilesRead,
        resource_pattern: ResourceScope::Path("/tmp/aether".into()),
        persona_id: persona.clone(),
        approval_mode: ApprovalMode::Auto,
        duration: GrantDuration::Session,
        issued_at: MonotonicTimestamp(1_000_000),
        expires_at: None,
        preset_version_issued_under: 1,
        approval_scope: None,
    };

    // Cold open + issue.
    {
        let backends = DurableBackends::open(&path).expect("cold open");
        let id = backends.ledger.issue(grant.clone()).expect("issue");
        assert_eq!(id, grant.grant_id);
        drop(backends);
    }

    // Warm open — the grant must still be visible + cover the same scope.
    {
        let backends = DurableBackends::open(&path).expect("warm open");
        let snap = backends.ledger.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        });
        assert_eq!(snap.len(), 1, "one active grant should survive restart");
        assert_eq!(snap[0].grant_id, grant.grant_id);

        let covered = backends.ledger.covers(
            &Capability::FilesRead,
            &ResourceScope::Path("/tmp/aether/subdir/x".into()),
            &persona,
        );
        assert_eq!(covered, Some(grant.grant_id.clone()));
    }
}

/// Revoke across restart: after revoke + reopen, the grant is not active
/// and `covers` returns None.
#[test]
fn revoke_persists_across_restart() {
    let (_tmp, path) = temp_db("revoke.db");
    let persona = PersonaId("aurora".into());
    let grant = Grant {
        grant_id: GrantId("grant-revoked".into()),
        capability: Capability::FilesRead,
        resource_pattern: ResourceScope::None,
        persona_id: persona.clone(),
        approval_mode: ApprovalMode::Auto,
        duration: GrantDuration::Session,
        issued_at: MonotonicTimestamp(42),
        expires_at: None,
        preset_version_issued_under: 1,
        approval_scope: None,
    };

    {
        let b = DurableBackends::open(&path).unwrap();
        b.ledger.issue(grant.clone()).unwrap();
        b.ledger.revoke(&grant.grant_id, RevokeReason::UserRevoked);
    }
    {
        let b = DurableBackends::open(&path).unwrap();
        let active = b.ledger.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        });
        assert_eq!(active.len(), 0, "revoked grant must not resurface active");

        let all = b.ledger.snapshot(&GrantFilter::default());
        assert_eq!(
            all.len(),
            1,
            "revoked grant should still exist historically"
        );

        let cover = b
            .ledger
            .covers(&Capability::FilesRead, &ResourceScope::None, &persona);
        assert!(cover.is_none(), "revoked grant must not cover");
    }
}

/// Audit row survives a restart and filters honor `since` / `until`.
#[test]
fn audit_rows_survive_restart_and_filter_by_time_window() {
    use aether_l5_policy::audit::KeyId;

    let (_tmp, path) = temp_db("audit.db");

    let early = AuditRecordEvent {
        audit_id: AuditId("a-early".into()),
        timestamp_monotonic: MonotonicTimestamp(100),
        timestamp_wall: common::WallTimestamp {
            epoch_s: 1_700_000_000,
            ns: 0,
        },
        actor: ActorRef::User,
        capability: Capability::FilesRead,
        resource: ResourceScope::None,
        decision: DecisionKind::Allow,
        change_id: ChangeId("change-1".into()),
        prev_hash: Vec::new(),
        record_hmac: vec![0u8; 16],
        key_id: KeyId("kid-1".into()),
        seq: 1u64,
        reason: None,
        stage_trace: Vec::new(),
        privileged_profile: false,
        schema_version: aether_l5_policy::AUDIT_SCHEMA_VERSION_V2,
        original_utterance: None,
        retrieval_provenance: None,
        approval_scope: None,
        auto_approved_under_grant: None,
    };
    let late = AuditRecordEvent {
        audit_id: AuditId("a-late".into()),
        timestamp_monotonic: MonotonicTimestamp(500),
        ..early.clone()
    };

    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&early).unwrap();
        b.audit.append(&late).unwrap();
    }
    {
        let b = DurableBackends::open(&path).unwrap();
        let all = b.audit.query(&AuditFilter::default(), 100);
        assert_eq!(all.len(), 2);

        let only_late = b.audit.query(
            &AuditFilter {
                since: Some(MonotonicTimestamp(300)),
                ..Default::default()
            },
            100,
        );
        assert_eq!(only_late.len(), 1);
        assert_eq!(only_late[0].audit_id, AuditId("a-late".into()));

        b.audit
            .verify_chain()
            .expect("chain verify is Ok for Wave 4.5");
    }
}

/// Append-only invariant — the 0001 trigger rejects DELETE even when the
/// caller holds the SqliteAuditStore. Proves we inherited the 0001
/// guarantee and didn't bypass it.
#[test]
fn sqlite_audit_store_cannot_delete_rows() {
    use aether_l5_policy::audit::KeyId;

    let (_tmp, path) = temp_db("append_only.db");
    let row = AuditRecordEvent {
        audit_id: AuditId("only".into()),
        timestamp_monotonic: MonotonicTimestamp(1),
        timestamp_wall: common::WallTimestamp { epoch_s: 1, ns: 0 },
        actor: ActorRef::System,
        capability: Capability::MemoryRead,
        resource: ResourceScope::None,
        decision: DecisionKind::Allow,
        change_id: ChangeId("c".into()),
        prev_hash: Vec::new(),
        record_hmac: vec![1u8; 16],
        key_id: KeyId("k".into()),
        seq: 1u64,
        reason: None,
        stage_trace: Vec::new(),
        privileged_profile: false,
        schema_version: aether_l5_policy::AUDIT_SCHEMA_VERSION_V2,
        original_utterance: None,
        retrieval_provenance: None,
        approval_scope: None,
        auto_approved_under_grant: None,
    };

    let b = DurableBackends::open(&path).unwrap();
    b.audit.append(&row).unwrap();

    let conn = b.conn.lock().unwrap();
    let err = conn
        .execute("DELETE FROM policy_audit_log WHERE audit_id='only'", [])
        .expect_err("0001 trigger must reject DELETE");
    assert!(
        err.to_string().to_lowercase().contains("append-only"),
        "unexpected error: {err}"
    );
}

/// Engine smoke: the refactored `DefaultPolicyEngine` accepts the SQLite
/// backends as trait objects and runs evaluate() end-to-end. No behavioral
/// assertion beyond "it doesn't panic and returns a Decision"; the full
/// evaluator behavior is covered by engine_slice.rs against in-memory.
#[test]
fn engine_accepts_sqlite_backends_and_evaluates() {
    let (_tmp, path) = temp_db("engine.db");
    let persona = PersonaId("aurora".into());
    let backends = DurableBackends::open(&path).unwrap();

    let cfg = EngineConfig::wave3_default(persona.clone());
    let sink = Arc::new(InMemorySink::new());
    let engine = DefaultPolicyEngine::new(
        cfg,
        backends.ledger.clone(),
        backends.audit.clone(),
        sink.clone(),
    );

    let req = ActionRequest {
        request_id: RequestId("r".into()),
        turn_id: TurnId("t".into()),
        capability: Capability::MemoryRead,
        resource: ResourceScope::None,
        actor_persona: persona,
        emitted_at: MonotonicTimestamp(10),
        task_id: Some(TaskId("task".into())),
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
        audit_extras: None,
    };

    // Don't care which exact decision — just that the engine operates.
    let _ = engine.evaluate(req);
}
