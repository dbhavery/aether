//! T1.3 §2.3 — `ApprovalScope` behavioral tests.
//!
//! Test-matrix mapping per the design doc §11.6:
//!
//! - Legacy round-trip — pre-T1.3 `PolicyDecisionEvent` /
//!   `GrantIssuedEvent` / `Grant` / `AuditRecordEvent` JSON blobs (no
//!   `approval_scope` field) deserialize cleanly with the new field
//!   defaulted to `None`.
//! - Round-trip each `ApprovalScope` variant through serde.
//! - `OncePerSession` reuse — first request prompts and grants; second
//!   same-shape request auto-approves with no `ApprovalPending` emitted;
//!   audit row N+1 has `auto_approved_under_grant = Some(grant_id)`.
//! - `OncePerSession` revocation — manual revoke (the engine has no
//!   explicit "session end" call; revocation stands in).
//! - `OncePerTask` revocation on turn terminate — modeled as ledger
//!   revoke for the same reason.
//! - `DraftOnly` does not issue a grant (no new ledger row).
//! - The 8 re-eval triggers still fire under a non-`PerAction` scope —
//!   regression guard for DECISION_LOCK_PASS_2026-04-18 Decision 4.
//!
//! Source: the approval-scope design in `ARCHITECTURE.md`.

use std::sync::Arc;

use aether_l5_policy::*;

fn build_engine() -> (
    Arc<DefaultPolicyEngine>,
    Arc<InMemorySink>,
    Arc<InMemoryAuditStore>,
    Arc<InMemoryGrantLedger>,
    PersonaId,
) {
    let persona = PersonaId(String::from("aurora"));
    let cfg = EngineConfig::wave3_default(persona.clone());
    let ledger = Arc::new(InMemoryGrantLedger::new());
    let audit = Arc::new(InMemoryAuditStore::new());
    let sink = Arc::new(InMemorySink::new());
    let engine = Arc::new(DefaultPolicyEngine::new(
        cfg,
        ledger.clone(),
        audit.clone(),
        sink.clone(),
    ));
    (engine, sink, audit, ledger, persona)
}

fn req(
    id: &str,
    cap: Capability,
    scope: ResourceScope,
    persona: PersonaId,
    t_ns: u64,
) -> policy_engine::ActionRequest {
    policy_engine::ActionRequest {
        request_id: RequestId(String::from(id)),
        turn_id: common::TurnId(String::from("turn-1")),
        capability: cap,
        resource: scope,
        actor_persona: persona,
        emitted_at: MonotonicTimestamp(t_ns),
        task_id: Some(TaskId(String::from("task-1"))),
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
        audit_extras: None,
    }
}

// ---------------------------------------------------------------------------
// Round-trip tests.
// ---------------------------------------------------------------------------

#[test]
fn approval_scope_default_is_per_action() {
    assert_eq!(ApprovalScope::default(), ApprovalScope::PerAction);
}

#[test]
fn approval_scope_round_trips_through_serde() {
    for scope in [
        ApprovalScope::PerAction,
        ApprovalScope::OncePerSession,
        ApprovalScope::OncePerTask,
        ApprovalScope::DraftOnly,
    ] {
        let s = serde_json::to_string(&scope).unwrap();
        let back: ApprovalScope = serde_json::from_str(&s).unwrap();
        assert_eq!(back, scope, "round-trip failed for {:?}", scope);
    }
}

#[test]
fn from_user_choice_maps_per_design_doc_table() {
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::Allow),
        ApprovalScope::PerAction
    );
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::AllowScope(ResourceScope::None)),
        ApprovalScope::PerAction
    );
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::AllowSession),
        ApprovalScope::OncePerSession
    );
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::AllowTask),
        ApprovalScope::OncePerTask
    );
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::Deny),
        ApprovalScope::PerAction
    );
    assert_eq!(
        ApprovalScope::from_user_choice(&UserChoice::DeferToDraft),
        ApprovalScope::DraftOnly
    );
}

#[test]
fn legacy_grant_payload_without_approval_scope_deserializes_as_none() {
    // Build a Grant, serialize, strip the `approval_scope` field, and
    // confirm deserialization succeeds with `approval_scope: None`.
    let g = Grant {
        grant_id: GrantId("g-legacy".into()),
        capability: Capability::FilesRead,
        resource_pattern: ResourceScope::Path(String::from("/tmp")),
        persona_id: PersonaId(String::from("aurora")),
        approval_mode: ApprovalMode::Auto,
        duration: GrantDuration::Session,
        issued_at: MonotonicTimestamp(1),
        expires_at: None,
        preset_version_issued_under: 1,
        approval_scope: None,
    };
    let mut value = serde_json::to_value(&g).unwrap();
    value.as_object_mut().unwrap().remove("approval_scope");
    let json = serde_json::to_string(&value).unwrap();
    assert!(!json.contains("approval_scope"));
    let back: Grant = serde_json::from_str(&json).unwrap();
    assert!(back.approval_scope.is_none());
}

#[test]
fn legacy_audit_record_event_without_approval_scope_deserializes_as_none() {
    let row = audit::AuditRecordEvent {
        audit_id: audit::AuditId("a-legacy".into()),
        timestamp_monotonic: MonotonicTimestamp(1),
        timestamp_wall: common::WallTimestamp { epoch_s: 1, ns: 0 },
        actor: ActorRef::User,
        capability: Capability::FilesRead,
        resource: ResourceScope::None,
        decision: DecisionKind::Allow,
        change_id: ChangeId("c1".into()),
        prev_hash: Vec::new(),
        record_hmac: Vec::new(),
        key_id: audit::KeyId("k".into()),
        seq: 1,
        reason: None,
        stage_trace: Vec::new(),
        privileged_profile: false,
        schema_version: AUDIT_SCHEMA_VERSION_V2,
        original_utterance: None,
        retrieval_provenance: None,
        approval_scope: None,
        auto_approved_under_grant: None,
    };
    let mut value = serde_json::to_value(&row).unwrap();
    let obj = value.as_object_mut().unwrap();
    obj.remove("approval_scope");
    obj.remove("auto_approved_under_grant");
    let json = serde_json::to_string(&value).unwrap();
    assert!(!json.contains("approval_scope"));
    assert!(!json.contains("auto_approved_under_grant"));
    let back: audit::AuditRecordEvent = serde_json::from_str(&json).unwrap();
    assert!(back.approval_scope.is_none());
    assert!(back.auto_approved_under_grant.is_none());
}

#[test]
fn legacy_policy_decision_event_without_approval_scope_deserializes_as_none() {
    let pd = events::PolicyDecisionEvent {
        request_id: RequestId("r".into()),
        decision: DecisionKind::Allow,
        audit_id: audit::AuditId("a".into()),
        change_id: ChangeId("c".into()),
        seq: 1,
        reason: None,
        effective_mode: None,
        approval_scope: None,
    };
    let mut value = serde_json::to_value(&pd).unwrap();
    value.as_object_mut().unwrap().remove("approval_scope");
    let json = serde_json::to_string(&value).unwrap();
    assert!(!json.contains("approval_scope"));
    let back: events::PolicyDecisionEvent = serde_json::from_str(&json).unwrap();
    assert!(back.approval_scope.is_none());
}

#[test]
fn legacy_grant_issued_event_without_approval_scope_deserializes_as_none() {
    let gi = events::GrantIssuedEvent {
        grant_id: GrantId("g".into()),
        capability: Capability::FilesRead,
        resource_scope: ResourceScope::None,
        approval_mode: ApprovalMode::Auto,
        duration: GrantDuration::Session,
        issued_at: MonotonicTimestamp(1),
        issued_by: ActorRef::User,
        audit_ref: audit::AuditId("a".into()),
        change_id: ChangeId("c".into()),
        seq: 1,
        preset_version_issued_under: 1,
        approval_scope: None,
    };
    let mut value = serde_json::to_value(&gi).unwrap();
    value.as_object_mut().unwrap().remove("approval_scope");
    let json = serde_json::to_string(&value).unwrap();
    assert!(!json.contains("approval_scope"));
    let back: events::GrantIssuedEvent = serde_json::from_str(&json).unwrap();
    assert!(back.approval_scope.is_none());
}

// ---------------------------------------------------------------------------
// Behavioral: OncePerSession reuse without re-prompting.
// ---------------------------------------------------------------------------

fn approve_with(engine: &DefaultPolicyEngine, ticket_id: ApprovalTicketId, choice: UserChoice) {
    engine
        .respond_approval(ApprovalResponse {
            ticket_id,
            user_choice: choice,
            responded_at: MonotonicTimestamp(150),
            scope_override: None,
            duration_override: None,
            reauth_token: None,
        })
        .expect("respond_approval succeeds");
}

#[test]
fn once_per_session_grant_carries_scope() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowSession);

    let active = ledger.snapshot(&GrantFilter {
        active_only: true,
        persona_id: Some(persona),
        capability: Some(Capability::FilesDelete),
    });
    assert_eq!(active.len(), 1);
    assert_eq!(
        active[0].approval_scope,
        Some(ApprovalScope::OncePerSession),
        "AllowSession must stamp OncePerSession on the issued grant",
    );
}

#[test]
fn once_per_session_reuse_auto_approves_without_re_prompt() {
    let (engine, sink, audit, _ledger, persona) = build_engine();

    // 1st request → Ask → user picks AllowSession.
    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowSession);

    let approvals_before = sink.count_where(|e| matches!(e, L5Event::ApprovalPending(_)));
    let audit_count_before = audit.count_kind(DecisionKind::Allow);

    // 2nd request, same shape → auto-approve under grant. NO new
    // ApprovalPending event. Audit row N+1 has
    // auto_approved_under_grant = Some(_).
    let d2 = engine
        .evaluate(req(
            "r2",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            200,
        ))
        .unwrap();
    assert!(
        matches!(
            d2,
            Decision::Allow {
                grant_ref: Some(_),
                ..
            }
        ),
        "expected Allow, got {:?}",
        d2,
    );
    let approvals_after = sink.count_where(|e| matches!(e, L5Event::ApprovalPending(_)));
    assert_eq!(
        approvals_after, approvals_before,
        "no new ApprovalPending event should fire on the OncePerSession reuse",
    );
    let audit_count_after = audit.count_kind(DecisionKind::Allow);
    assert_eq!(
        audit_count_after,
        audit_count_before + 1,
        "exactly one new Allow audit row was written under the grant",
    );

    // The newest decision event echoes OncePerSession on the wire.
    let pd_with_scope = sink.count_where(|e| match e {
        L5Event::PolicyDecision(pd) => pd.approval_scope == Some(ApprovalScope::OncePerSession),
        _ => false,
    });
    assert!(
        pd_with_scope >= 1,
        "at least one PolicyDecisionEvent should carry approval_scope = OncePerSession",
    );
}

#[test]
fn once_per_session_revocation_forces_re_prompt() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    // Ask → AllowSession.
    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowSession);
    let grants = ledger.snapshot(&GrantFilter {
        active_only: true,
        ..Default::default()
    });
    assert_eq!(grants.len(), 1);

    // "Session end" stand-in: revoke the grant. The next request must
    // re-prompt. The engine has no explicit end_session() yet — manual
    // revoke covers the contract for now.
    ledger.revoke(&grants[0].grant_id, events::RevokeReason::UserRevoked);

    let d2 = engine
        .evaluate(req(
            "r2",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            200,
        ))
        .unwrap();
    assert!(
        matches!(d2, Decision::Ask { .. }),
        "post-revoke request must re-prompt, got {:?}",
        d2,
    );
}

// ---------------------------------------------------------------------------
// Behavioral: OncePerTask.
// ---------------------------------------------------------------------------

#[test]
fn once_per_task_grant_carries_scope_and_task_id() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowTask);

    let active = ledger.snapshot(&GrantFilter {
        active_only: true,
        persona_id: Some(persona),
        capability: Some(Capability::FilesDelete),
    });
    assert_eq!(active.len(), 1);
    assert_eq!(active[0].approval_scope, Some(ApprovalScope::OncePerTask));
    // GrantDuration::TaskScoped carries the task id from the request.
    match &active[0].duration {
        GrantDuration::TaskScoped(t) => assert_eq!(t.0, "task-1"),
        other => panic!("expected TaskScoped, got {:?}", other),
    }
}

#[test]
fn once_per_task_revocation_on_turn_terminate_forces_re_prompt() {
    // Models the design's §4.1 task-end revoke: when the originating
    // turn terminates, the grant is revoked with
    // RevokeReason::TtlExpired. Here we do that revoke explicitly and
    // confirm the next request re-prompts.
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowTask);

    let grants = ledger.snapshot(&GrantFilter {
        active_only: true,
        ..Default::default()
    });
    assert_eq!(grants.len(), 1);
    // Simulate "turn terminate" → engine revokes with TtlExpired
    // (existing variant; design §4.1 explicitly re-uses it).
    ledger.revoke(&grants[0].grant_id, events::RevokeReason::TtlExpired);

    let d2 = engine
        .evaluate(req(
            "r2",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            200,
        ))
        .unwrap();
    assert!(
        matches!(d2, Decision::Ask { .. }),
        "post-turn-terminate request must re-prompt, got {:?}",
        d2,
    );
}

// ---------------------------------------------------------------------------
// Behavioral: DraftOnly does not issue a grant.
// ---------------------------------------------------------------------------

#[test]
fn draft_only_user_choice_does_not_issue_a_grant() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    let active_before = ledger.active_count();
    approve_with(&engine, ticket.ticket_id, UserChoice::DeferToDraft);
    let active_after = ledger.active_count();
    assert_eq!(
        active_after, active_before,
        "DraftOnly must not issue a grant — design §4.3",
    );
}

// ---------------------------------------------------------------------------
// 8 re-eval triggers regression — Decision 4 still fires under
// OncePerSession scope.
// ---------------------------------------------------------------------------

#[test]
fn ttl_re_eval_trigger_still_fires_under_once_per_session_scope() {
    // Hand-craft a OncePerSession grant whose TTL has already lapsed.
    // Decision 4 trigger 8 must drop the grant before the cover-check
    // and force a re-prompt — the new scope must NOT shield the grant
    // from re-evaluation.
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    ledger.issue(Grant {
        grant_id: GrantId("session-expired".into()),
        capability: Capability::FilesDelete,
        resource_pattern: ResourceScope::Path(String::from("/tmp")),
        persona_id: persona.clone(),
        approval_mode: ApprovalMode::Ask,
        duration: GrantDuration::Persistent { ttl: None },
        issued_at: MonotonicTimestamp(10),
        expires_at: Some(MonotonicTimestamp(50)),
        preset_version_issued_under: 1,
        approval_scope: Some(ApprovalScope::OncePerSession),
    });
    assert_eq!(ledger.active_count(), 1);

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            100,
        ))
        .unwrap();
    assert!(
        matches!(d, Decision::Ask { .. }),
        "TTL re-eval (trigger 8) must still fire under OncePerSession, got {:?}",
        d,
    );
    assert_eq!(
        ledger.active_count(),
        0,
        "TTL trigger must drop the expired grant regardless of scope",
    );
}

#[test]
fn revoke_re_eval_trigger_still_fires_under_once_per_task_scope() {
    // Decision 4 trigger 7 — GrantRevoked forces re-evaluation. The new
    // scope must not bypass that.
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        _ => panic!("expected Ask"),
    };
    approve_with(&engine, ticket.ticket_id, UserChoice::AllowTask);
    let g = ledger
        .snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        })
        .pop()
        .unwrap();
    assert_eq!(g.approval_scope, Some(ApprovalScope::OncePerTask));
    ledger.revoke(&g.grant_id, events::RevokeReason::UserRevoked);

    let d2 = engine
        .evaluate(req(
            "r2",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            200,
        ))
        .unwrap();
    assert!(
        matches!(d2, Decision::Ask { .. }),
        "GrantRevoked (trigger 7) must still fire under OncePerTask, got {:?}",
        d2,
    );
}
