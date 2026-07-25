//! Wave 4.6 — audit hash-chain + HMAC sealing tests.
//!
//! These tests exercise the sealing path end-to-end: append sealed rows,
//! verify the chain, then tamper (payload, key, chain-head rollback) and
//! confirm `verify_chain` reports a specific error.

#![cfg(feature = "sqlite-backend")]

use aether_l5_policy::{
    audit::{AuditId, AuditRecordEvent, KeyId},
    capability::{Capability, ResourceScope},
    common::{ActorRef, ChangeId, MonotonicTimestamp, WallTimestamp},
    decision::DecisionKind,
    storage_hooks::AuditVerifyError,
    DurableBackends, HmacKey,
};
use tempfile::TempDir;

fn make_row(id: &str, t: u64) -> AuditRecordEvent {
    AuditRecordEvent {
        audit_id: AuditId(id.into()),
        timestamp_monotonic: MonotonicTimestamp(t),
        timestamp_wall: WallTimestamp {
            epoch_s: 1_700_000_000,
            ns: 0,
        },
        actor: ActorRef::System,
        capability: Capability::FilesRead,
        resource: ResourceScope::None,
        decision: DecisionKind::Allow,
        change_id: ChangeId("c".into()),
        prev_hash: Vec::new(),
        record_hmac: Vec::new(),
        key_id: KeyId("caller-supplied".into()),
        seq: t,
        reason: None,
        stage_trace: Vec::new(),
        privileged_profile: false,
    }
}

fn temp(name: &str) -> (TempDir, std::path::PathBuf) {
    let d = TempDir::new().unwrap();
    let p = d.path().join(name);
    (d, p)
}

#[test]
fn verify_chain_passes_on_fresh_sealed_log() {
    let (_tmp, path) = temp("seal_ok.db");
    let b = DurableBackends::open(&path).unwrap();
    b.audit.append(&make_row("a-1", 1)).unwrap();
    b.audit.append(&make_row("a-2", 2)).unwrap();
    b.audit.append(&make_row("a-3", 3)).unwrap();
    b.audit.verify_chain().expect("fresh chain verifies");
}

#[test]
fn verify_chain_detects_payload_tampering() {
    let (_tmp, path) = temp("seal_tamper_payload.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row("a-1", 1)).unwrap();
        b.audit.append(&make_row("a-2", 2)).unwrap();
        b.audit.verify_chain().expect("clean chain");

        // Tamper: rewrite row 1's payload to a different audit_id without
        // updating the hash. The append-only triggers forbid UPDATE on
        // policy_audit_log, so we have to drop them first to simulate
        // out-of-band tampering (e.g. someone editing the DB file with
        // another tool). That's exactly what the chain is supposed to
        // catch.
        let conn = b.conn.lock().unwrap();
        conn.execute_batch(
            "DROP TRIGGER IF EXISTS policy_audit_log_no_update; \
             DROP TRIGGER IF EXISTS policy_audit_log_no_delete;",
        )
        .unwrap();
        let tampered_payload = serde_json::to_string(&make_row("a-1-FAKE", 1)).unwrap();
        conn.execute(
            "UPDATE policy_audit_log SET payload = ?1 WHERE audit_id = 'a-1'",
            aether_storage::rusqlite::params![tampered_payload],
        )
        .unwrap();
    }

    let b = DurableBackends::open(&path).unwrap();
    let err = b
        .audit
        .verify_chain()
        .expect_err("tampered payload must fail verify");
    assert!(
        matches!(err, AuditVerifyError::ChainBreak { .. }),
        "expected ChainBreak, got {err:?}"
    );
}

#[test]
fn verify_chain_detects_wrong_key() {
    let (_tmp, path) = temp("seal_wrong_key.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row("a-1", 1)).unwrap();
        b.audit.append(&make_row("a-2", 2)).unwrap();
    }
    // Reopen with a deliberately different key.
    let wrong = HmacKey::from_bytes([0xEEu8; 32], KeyId("wrong-key".into()));
    let b = DurableBackends::open_with_key(&path, wrong).unwrap();
    let err = b
        .audit
        .verify_chain()
        .expect_err("verification must fail under wrong key");
    assert!(
        matches!(err, AuditVerifyError::HmacMismatch { .. }),
        "expected HmacMismatch, got {err:?}"
    );
}

#[test]
fn verify_chain_detects_chain_head_rollback() {
    let (_tmp, path) = temp("seal_rollback.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row("a-1", 1)).unwrap();
        b.audit.append(&make_row("a-2", 2)).unwrap();
        // Rollback: point the chain head at a zero hash.
        let conn = b.conn.lock().unwrap();
        conn.execute(
            "UPDATE policy_audit_chain_head SET head_hash = ?1 WHERE id = 1",
            aether_storage::rusqlite::params![vec![0u8; 32]],
        )
        .unwrap();
    }
    let b = DurableBackends::open(&path).unwrap();
    let err = b
        .audit
        .verify_chain()
        .expect_err("rolled-back head must fail verify");
    assert!(matches!(err, AuditVerifyError::ChainBreak { .. }));
}

#[test]
fn second_insertion_chains_from_prior_head_across_restart() {
    let (_tmp, path) = temp("seal_resume.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row("a-1", 1)).unwrap();
    }
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row("a-2", 2)).unwrap();
        b.audit
            .verify_chain()
            .expect("chain continues correctly across restart");
    }
}
