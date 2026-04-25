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
        schema_version: aether_l5_policy::AUDIT_SCHEMA_VERSION_V2,
        original_utterance: None,
        retrieval_provenance: None,
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

// ---------------------------------------------------------------------------
// ADR-0009 schema-version round-trip tests.
// ---------------------------------------------------------------------------

/// A pre-ADR-0009 wire payload (no `schema_version`,
/// `original_utterance`, or `retrieval_provenance` fields) must
/// deserialize cleanly as a v1 row. Per ADR-0009 §Open items
/// resolution: absence of `schema_version` means implicit v1.
#[test]
fn v1_payload_without_new_fields_deserializes_as_v1() {
    // Build the legacy wire shape by serializing a v2 row, then
    // stripping the three new fields from the JSON value. This
    // sidesteps the manual-JSON brittleness of guessing how every
    // nested newtype/enum encodes.
    let template = make_row("legacy-1", 100);
    let mut value = serde_json::to_value(&template).unwrap();
    let obj = value.as_object_mut().unwrap();
    obj.remove("schema_version");
    obj.remove("original_utterance");
    obj.remove("retrieval_provenance");
    let v1_json = serde_json::to_string(&value).unwrap();
    // Sanity: the legacy wire shape really is missing all three new
    // fields — otherwise the test isn't proving what it claims.
    assert!(!v1_json.contains("schema_version"));
    assert!(!v1_json.contains("original_utterance"));
    assert!(!v1_json.contains("retrieval_provenance"));

    let row: AuditRecordEvent =
        serde_json::from_str(&v1_json).expect("v1 payload must deserialize");
    assert_eq!(
        row.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V1,
        "absent schema_version field must default to v1"
    );
    assert!(row.original_utterance.is_none());
    assert!(row.retrieval_provenance.is_none());
}

/// A v2 row carrying retrieval provenance round-trips through serde
/// without losing the new fields.
#[test]
fn v2_row_with_provenance_round_trips_through_serde() {
    use aether_l5_policy::{RetrievalProvenance, RetrievedMemoryRef};

    let mut row = make_row("v2-row", 7);
    row.original_utterance = Some(String::from("what about sourdough?"));
    row.retrieval_provenance = Some(RetrievalProvenance {
        block_present: true,
        hits: vec![
            RetrievedMemoryRef {
                memory_id: String::from("mem-sess-12"),
                domain: String::from("durable"),
                score: 0.81,
            },
            RetrievedMemoryRef {
                memory_id: String::from("mem-sess-44"),
                domain: String::from("facts"),
                score: 0.72,
            },
        ],
    });

    let bytes = serde_json::to_vec(&row).unwrap();
    let back: AuditRecordEvent = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(back.schema_version, aether_l5_policy::AUDIT_SCHEMA_VERSION_V2);
    assert_eq!(
        back.original_utterance.as_deref(),
        Some("what about sourdough?")
    );
    let prov = back.retrieval_provenance.expect("provenance survives");
    assert!(prov.block_present);
    assert_eq!(prov.hits.len(), 2);
    assert_eq!(prov.hits[0].memory_id, "mem-sess-12");
    assert!((prov.hits[0].score - 0.81).abs() < 1e-6);
}

/// A v2 row with `retrieval_provenance: None` (e.g. a non-conversation
/// capability that still flowed through a v2-aware writer) round-trips
/// — the field is genuinely optional, not just defaulted.
#[test]
fn v2_row_without_provenance_round_trips_through_serde() {
    let row = make_row("v2-empty", 9);
    let bytes = serde_json::to_vec(&row).unwrap();
    let back: AuditRecordEvent = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(back.schema_version, aether_l5_policy::AUDIT_SCHEMA_VERSION_V2);
    assert!(back.original_utterance.is_none());
    assert!(back.retrieval_provenance.is_none());
}
