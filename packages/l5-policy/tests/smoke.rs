//! Smoke tests for the Wave 2 L5 scaffold.
//!
//! These assert *shape* only. There is no evaluator logic to test yet.

use aether_l5_policy::*;

#[test]
fn decision_needs_upgrade_is_top_level_variant() {
    // Decision 1 (2026-04-18): NeedsUpgrade is peer to Deny, not inside DenyReason.
    let d = Decision::NeedsUpgrade {
        capability_path: capability::CapabilityPath(String::from("files.read")),
        audit_id: AuditId(String::from("audit-1")),
        suggested_preset: None,
    };
    assert_eq!(d.kind(), decision::DecisionKind::NeedsUpgrade);
}

#[test]
fn draft_only_has_source_discriminant() {
    // Decision 2 (2026-04-18): DraftOnly { source: DraftSource }.
    let sys = Decision::DraftOnly {
        audit_id: AuditId(String::from("a")),
        source: DraftSource::System,
        reason: None,
    };
    let user = Decision::DraftOnly {
        audit_id: AuditId(String::from("b")),
        source: DraftSource::UserChoice,
        reason: None,
    };
    assert_ne!(sys.kind(), user.kind());
}

#[test]
fn user_choice_includes_defer_to_draft() {
    // Decision 2 path: UserChoice::DeferToDraft must exist for L7 approval flow.
    let _c = approval::UserChoice::DeferToDraft;
}

#[test]
fn re_eval_trigger_list_has_eight_entries() {
    // Decision 4 (2026-04-18).
    assert_eq!(decision::ReEvalTrigger::ALL.len(), 8);
}

#[test]
fn capability_enum_includes_decision3_additions() {
    // Decision 3 (2026-04-18).
    let _a = Capability::AuditExport;
    let _b = Capability::CostCapAdmin;
}

#[test]
fn policy_ipc_error_is_serializable() {
    // Stable code string used by TS bindings.
    let err = ipc::PolicyIpcError::Invalid {
        msg: "unknown_capability".into(),
    };
    let j = serde_json::to_string(&err).unwrap();
    assert!(j.contains("\"code\":\"invalid\""));
}

#[test]
fn l5_event_kind_round_trips_through_l5_event() {
    // Every L5Event has a matching kind.
    let action = events::ActionRequestEvent {
        request_id: RequestId(String::from("r")),
        capability: Capability::FilesRead,
        resource: ResourceScope::Path(String::from("/tmp")),
        actor_persona: PersonaId(String::from("p")),
        emitted_at: MonotonicTimestamp(0),
        change_id: ChangeId(String::from("c")),
        seq: 0,
    };
    let e = L5Event::ActionRequest(action);
    assert_eq!(e.kind(), L5EventKind::ActionRequest);
}
