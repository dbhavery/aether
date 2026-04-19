//! Wave 3 engine-slice tests.
//!
//! Test-matrix mapping (see
//! `planning/plans/implementation_prep/test_matrix_master.md` §2.5):
//!
//! - `L5-T01` — evaluate a capability with no grant → `Ask` ticket emitted.
//!   Covered by `ask_mode_without_grant_emits_ask_ticket`.
//! - `L5-T02` — revoke grant mid-turn → subsequent evaluate deny / re-ask.
//!   Covered by `revoked_grant_is_not_reused` (Decision 4 trigger 7).
//! - `L5-T05` — emergency revoke-all → all grants cleared.
//!   Covered by `emergency_revoke_clears_all_grants`.
//! - Decision 4 trigger 8 (TTL expiry) — covered by
//!   `ttl_expiry_drops_grant_before_next_evaluate`.
//! - Decision 2 — `UserChoice::DeferToDraft` resolves to
//!   `Decision::DraftOnly { source: UserChoice }`. Covered by
//!   `defer_to_draft_resolves_to_draft_only_user_choice`.
//! - Decision 1 — `NeedsUpgrade(CapabilityPath)` is top-level. Covered by
//!   `capability_outside_preset_returns_needs_upgrade`.

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
    }
}

fn count_events<F: Fn(&L5Event) -> bool>(sink: &InMemorySink, f: F) -> usize {
    sink.count_where(f)
}

// -------------------------------------------------------------------------
// Happy path: FilesRead is Auto. First eval → Allow + GrantIssued + audit.
// -------------------------------------------------------------------------
#[test]
fn safe_capability_allows_and_issues_session_grant() {
    let (engine, sink, audit, ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .expect("evaluate should succeed");

    assert!(matches!(d, Decision::Allow { grant_ref: Some(_), .. }));
    assert_eq!(d.kind(), DecisionKind::Allow);
    assert_eq!(
        ledger.snapshot(&GrantFilter { active_only: true, persona_id: Some(persona.clone()), capability: Some(Capability::FilesRead) }).len(),
        1,
        "one session grant issued for the Auto capability"
    );

    // Audit row was written before Allow returned.
    assert_eq!(audit.count_kind(DecisionKind::Allow), 1);

    // Event family emitted: ActionRequest, AuditRecord, GrantIssued, PolicyDecision.
    assert_eq!(count_events(&sink, |e| matches!(e, L5Event::ActionRequest(_))), 1);
    assert_eq!(count_events(&sink, |e| matches!(e, L5Event::AuditRecord(_))), 1);
    assert_eq!(count_events(&sink, |e| matches!(e, L5Event::GrantIssued(_))), 1);
    assert_eq!(count_events(&sink, |e| matches!(e, L5Event::PolicyDecision(_))), 1);
}

#[test]
fn second_evaluate_reuses_existing_grant_and_does_not_issue_new() {
    let (engine, sink, _audit, ledger, persona) = build_engine();

    let _ = engine
        .evaluate(req(
            "r1",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let d = engine
        .evaluate(req(
            "r2",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            200,
        ))
        .unwrap();

    assert!(matches!(d, Decision::Allow { grant_ref: Some(_), .. }));
    assert_eq!(
        ledger.snapshot(&GrantFilter { active_only: true, persona_id: Some(persona.clone()), capability: Some(Capability::FilesRead) }).len(),
        1,
        "still exactly one grant — the Auto-mode fast path reused it"
    );
    // Only one GrantIssued in the event stream.
    assert_eq!(count_events(&sink, |e| matches!(e, L5Event::GrantIssued(_))), 1);
}

// -------------------------------------------------------------------------
// L5-T01: Ask mode, no grant → Ask ticket emitted.
// -------------------------------------------------------------------------
#[test]
fn ask_mode_without_grant_emits_ask_ticket() {
    let (engine, sink, audit, _ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/doomed.txt")),
            persona,
            100,
        ))
        .unwrap();

    match d {
        Decision::Ask { ticket, .. } => {
            assert_eq!(ticket.capability, Capability::FilesDelete);
        }
        other => panic!("expected Ask, got {:?}", other),
    }
    assert_eq!(audit.count_kind(DecisionKind::Ask), 1);
    assert_eq!(
        count_events(&sink, |e| matches!(e, L5Event::ApprovalPending(_))),
        1
    );
}

// -------------------------------------------------------------------------
// Decision 2: DeferToDraft resolves to DraftOnly { source: UserChoice }.
// -------------------------------------------------------------------------
#[test]
fn defer_to_draft_resolves_to_draft_only_user_choice() {
    let (engine, sink, audit, _ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/doomed.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    let ticket = match d {
        Decision::Ask { ticket, .. } => ticket,
        other => panic!("expected Ask, got {:?}", other),
    };

    let _ = engine
        .respond_approval(approval::ApprovalResponse {
            ticket_id: ticket.ticket_id,
            user_choice: approval::UserChoice::DeferToDraft,
            responded_at: MonotonicTimestamp(150),
            scope_override: None,
            duration_override: None,
            reauth_token: None,
        })
        .expect("respond_approval succeeds");

    // A follow-up PolicyDecision event with DraftOnlyUserChoice was emitted.
    let draft_user_events = sink.count_where(|e| matches!(
        e,
        L5Event::PolicyDecision(pd) if pd.decision == DecisionKind::DraftOnlyUserChoice
    ));
    assert_eq!(draft_user_events, 1);
    assert_eq!(audit.count_kind(DecisionKind::DraftOnlyUserChoice), 1);
}

// -------------------------------------------------------------------------
// Approval round-trip: user Allows → grant issued → next eval short-circuits.
// -------------------------------------------------------------------------
#[test]
fn allow_approval_issues_grant_that_covers_future_evaluates() {
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

    engine
        .respond_approval(approval::ApprovalResponse {
            ticket_id: ticket.ticket_id,
            user_choice: approval::UserChoice::AllowTask,
            responded_at: MonotonicTimestamp(150),
            scope_override: None,
            duration_override: None,
            reauth_token: None,
        })
        .unwrap();

    assert_eq!(ledger.active_len(), 1);

    // Second evaluate on same path → Allow via grant_ref.
    let d2 = engine
        .evaluate(req(
            "r2",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            200,
        ))
        .unwrap();
    assert!(matches!(d2, Decision::Allow { grant_ref: Some(_), .. }));
}

// -------------------------------------------------------------------------
// L5-T02 slice: revoked grant is not reused; next evaluate re-Asks.
// (Decision 4, trigger 7 — GrantRevoked forces re-eval.)
// -------------------------------------------------------------------------
#[test]
fn revoked_grant_is_not_reused() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    // Ask flow → approve → grant active.
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
    engine
        .respond_approval(approval::ApprovalResponse {
            ticket_id: ticket.ticket_id,
            user_choice: approval::UserChoice::AllowSession,
            responded_at: MonotonicTimestamp(150),
            scope_override: None,
            duration_override: None,
            reauth_token: None,
        })
        .unwrap();
    let grants = ledger.snapshot(&GrantFilter {
        active_only: true,
        persona_id: Some(persona.clone()),
        capability: Some(Capability::FilesDelete),
    });
    assert_eq!(grants.len(), 1);

    // Revoke it.
    ledger.revoke(&grants[0].grant_id, events::RevokeReason::UserRevoked);
    assert_eq!(ledger.active_len(), 0);

    // Next evaluate must NOT reuse the revoked grant; returns Ask again.
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
        "expected Ask after revoke, got {:?}",
        d2
    );
}

// -------------------------------------------------------------------------
// Decision 4 trigger 8: TTL expiry fires at top of evaluate.
// -------------------------------------------------------------------------
#[test]
fn ttl_expiry_drops_grant_before_next_evaluate() {
    let (engine, _sink, _audit, ledger, persona) = build_engine();

    // Hand-craft an expired grant directly on the ledger.
    ledger.issue(Grant {
        grant_id: GrantId(String::from("pre-seeded")),
        capability: Capability::FilesDelete,
        resource_pattern: ResourceScope::Path(String::from("/tmp")),
        persona_id: persona.clone(),
        approval_mode: ApprovalMode::Ask,
        duration: GrantDuration::Persistent { ttl: None },
        issued_at: MonotonicTimestamp(10),
        expires_at: Some(MonotonicTimestamp(50)), // already past
        preset_version_issued_under: 1,
    });
    assert_eq!(ledger.active_len(), 1);

    // Evaluate with "now" after expiry → expire_ttl fires → grant revoked →
    // evaluator must return Ask, not Allow.
    let d = engine
        .evaluate(req(
            "r1",
            Capability::FilesDelete,
            ResourceScope::Path(String::from("/tmp/x.txt")),
            persona,
            1000,
        ))
        .unwrap();

    assert!(matches!(d, Decision::Ask { .. }));
    assert_eq!(ledger.active_len(), 0);
}

// -------------------------------------------------------------------------
// L5-T05: emergency revoke-all clears every active grant.
// -------------------------------------------------------------------------
#[test]
fn emergency_revoke_clears_all_grants() {
    let (engine, sink, _audit, ledger, persona) = build_engine();

    // Seed two Auto grants (FilesRead) by running the evaluator twice on
    // different paths. `Auto` issues a new session grant each time because the
    // second scope doesn't overlap the first.
    engine
        .evaluate(req(
            "r1",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona.clone(),
            100,
        ))
        .unwrap();
    engine
        .evaluate(req(
            "r2",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/var/b.txt")),
            persona.clone(),
            200,
        ))
        .unwrap();
    assert_eq!(ledger.active_len(), 2);

    let receipt = engine
        .emergency_revoke(events::EmergencyScope::All)
        .unwrap();
    assert_eq!(receipt.revoked_count, 2);
    assert_eq!(ledger.active_len(), 0);
    assert_eq!(
        sink.count_where(|e| matches!(e, L5Event::EmergencyRevokeAll(_))),
        1
    );
}

// -------------------------------------------------------------------------
// Decision 1: NeedsUpgrade(CapabilityPath) is top-level when preset misses.
// -------------------------------------------------------------------------
#[test]
fn capability_outside_preset_returns_needs_upgrade() {
    let (engine, _sink, audit, _ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::BrowserOpen, // intentionally absent from wave3_default preset
            ResourceScope::Url(String::from("https://example.com/")),
            persona,
            100,
        ))
        .unwrap();

    assert_eq!(d.kind(), DecisionKind::NeedsUpgrade);
    match d {
        Decision::NeedsUpgrade { suggested_preset, .. } => {
            assert!(suggested_preset.is_some(), "operator-preset suggestion expected");
        }
        _ => unreachable!(),
    }
    assert_eq!(audit.count_kind(DecisionKind::NeedsUpgrade), 1);
}

// -------------------------------------------------------------------------
// ShellExec capability is preset-denied → Decision::Deny { ModeDeny }.
// -------------------------------------------------------------------------
#[test]
fn shell_exec_is_mode_denied() {
    let (engine, _sink, audit, _ledger, persona) = build_engine();

    let d = engine
        .evaluate(req(
            "r1",
            Capability::ShellExec,
            ResourceScope::None,
            persona,
            100,
        ))
        .unwrap();

    match d {
        Decision::Deny { reason: DenyReason::ModeDeny, .. } => {}
        other => panic!("expected Deny(ModeDeny), got {:?}", other),
    }
    assert_eq!(audit.count_kind(DecisionKind::Deny), 1);
}

// -------------------------------------------------------------------------
// Audit write happens BEFORE Allow returns (L5 §5 invariant).
// -------------------------------------------------------------------------
#[test]
fn audit_row_is_committed_before_allow_returns() {
    let (engine, _sink, audit, _ledger, persona) = build_engine();

    assert_eq!(audit.len(), 0);
    let _ = engine
        .evaluate(req(
            "r1",
            Capability::FilesRead,
            ResourceScope::Path(String::from("/tmp/a.txt")),
            persona,
            100,
        ))
        .unwrap();
    // At the moment the evaluate returned the row is already queryable.
    assert_eq!(audit.len(), 1);
    assert_eq!(audit.count_kind(DecisionKind::Allow), 1);
}
