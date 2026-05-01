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
        approval_scope: None,
        auto_approved_under_grant: None,
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
    assert_eq!(
        back.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V2
    );
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
    assert_eq!(
        back.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V2
    );
    assert!(back.original_utterance.is_none());
    assert!(back.retrieval_provenance.is_none());
}

// ---------------------------------------------------------------------------
// HIGH-1 regression — version-aware canonical_bytes preserves v1 chains.
//
// Before the fix in this commit, `canonical_bytes` always serialized the
// wide ADR-0009 shape (with `schema_version`, `original_utterance`,
// `retrieval_provenance`). A row sealed pre-`f378ea5` was hashed over the
// narrow shape and would re-verify to a different hash post-deploy →
// false-positive `AuditVerifyError` on every legacy row.
//
// These tests pin the fix:
//   1. v1 rows hash over a narrow canonical payload that omits the three
//      ADR-0009 v2 fields entirely.
//   2. A chain whose first row is v1 and second row is v2 verifies cleanly
//      end-to-end (cross-schema replay).
//   3. Future schema versions (v3+) are treated as wide for forward-compat.
// ---------------------------------------------------------------------------

fn make_row_v1(id: &str, t: u64) -> AuditRecordEvent {
    let mut row = make_row(id, t);
    row.schema_version = aether_l5_policy::AUDIT_SCHEMA_VERSION_V1;
    row.original_utterance = None;
    row.retrieval_provenance = None;
    row
}

#[test]
fn canonical_bytes_for_v1_row_omits_adr0009_fields() {
    use aether_l5_policy::canonical_bytes;
    let row = make_row_v1("v1-narrow", 1);
    let bytes = canonical_bytes(&row).expect("canonicalize v1");
    let s = std::str::from_utf8(&bytes).expect("utf8");
    assert!(
        !s.contains("schema_version"),
        "v1 canonical bytes must not contain 'schema_version': {s}"
    );
    assert!(
        !s.contains("original_utterance"),
        "v1 canonical bytes must not contain 'original_utterance': {s}"
    );
    assert!(
        !s.contains("retrieval_provenance"),
        "v1 canonical bytes must not contain 'retrieval_provenance': {s}"
    );
}

#[test]
fn canonical_bytes_for_v2_row_includes_adr0009_fields() {
    use aether_l5_policy::canonical_bytes;
    let row = make_row("v2-wide", 1);
    let bytes = canonical_bytes(&row).expect("canonicalize v2");
    let s = std::str::from_utf8(&bytes).expect("utf8");
    assert!(s.contains("schema_version"));
    assert!(s.contains("original_utterance"));
    assert!(s.contains("retrieval_provenance"));
}

#[test]
fn cross_schema_chain_replay_verifies_v1_then_v2() {
    // Simulates the production migration scenario: a row was sealed
    // before ADR-0009 (v1, narrow canonicalization), then a row is
    // sealed after the upgrade (v2, wide canonicalization). Both must
    // re-verify under the post-fix verifier.
    let (_tmp, path) = temp("seal_cross_schema.db");
    let b = DurableBackends::open(&path).unwrap();
    b.audit.append(&make_row_v1("legacy-v1", 1)).unwrap();
    b.audit.append(&make_row("modern-v2", 2)).unwrap();
    b.audit
        .verify_chain()
        .expect("v1→v2 chain must verify after HIGH-1 fix");
}

/// Forward-compatibility: a hypothetical v3 row (or any version > v2)
/// canonicalizes through the wide path. A v3-aware deserializer that
/// dropped unknown fields would land here. This locks the
/// "anything-not-v1 is wide" dispatch so a future schema bump does not
/// silently revert to the narrow shape and break v2 chains.
#[test]
fn canonical_bytes_for_future_versions_uses_v2_shape() {
    use aether_l5_policy::canonical_bytes;
    let mut row = make_row("future-v3", 1);
    row.schema_version = 3;
    let bytes = canonical_bytes(&row).expect("canonicalize v3-as-v2");
    let s = std::str::from_utf8(&bytes).expect("utf8");
    assert!(s.contains("\"schema_version\":3"));
    assert!(s.contains("original_utterance"));
    assert!(s.contains("retrieval_provenance"));
}

// ---------------------------------------------------------------------------
// ADR-0009 code-review finding #1 — mixed v1/v2 audit-DB integration tests.
//
// The pre-existing `cross_schema_chain_replay_verifies_v1_then_v2` test
// exercises the seal/verify path for a v1→v2 sequence but never reads the
// rows back through `AuditStore::query`. The `audit_recent` Trust-drawer
// projection (apps/desktop/src-tauri/src/commands.rs) is fed by exactly
// that projection, so a defect in v1 deserialization on the read path —
// e.g. a future serde-attribute change that broke the implicit-v1 default —
// would slip past every existing test.
//
// These tests close that gap by:
//   1. Putting both a v1 row (engine-sealed v1) and a v2 row (engine-sealed
//      v2 with populated `original_utterance` + `retrieval_provenance`)
//      into the same audit DB, then reading them back via `query` and
//      asserting per-row `schema_version` + field population.
//   2. Splicing a true legacy on-disk payload — the JSON literally lacks
//      `schema_version` / `original_utterance` / `retrieval_provenance`,
//      mirroring a row written by a pre-ADR-0009 build before the writer
//      ever stamped v2 — alongside an engine-sealed v2 row, then querying
//      both back. This pins the wire-shape contract: absent fields ⇒ v1.
//   3. Tampering with the v1 and v2 payloads independently and asserting
//      `verify_chain` reports the break, exercising the security-fix
//      branching in `canonical_bytes` from both sides (review §6 #4).
// ---------------------------------------------------------------------------

/// Engine-sealed v1 + engine-sealed v2 in the same DB read back through
/// `query` with per-row schema awareness preserved.
#[test]
fn mixed_v1_v2_rows_query_back_with_correct_schema_versions() {
    use aether_l5_policy::{AuditFilter, RetrievalProvenance, RetrievedMemoryRef};

    let (_tmp, path) = temp("mixed_v1_v2_query.db");

    // Write phase.
    {
        let b = DurableBackends::open(&path).unwrap();

        // v1 row — pre-ADR-0009 shape; the writer's canonical_bytes
        // dispatches on schema_version, so this row is sealed under
        // CanonicalAuditPayloadV1.
        b.audit
            .append(&make_row_v1("legacy-row", 100))
            .expect("append v1");

        // v2 row — current shape with both new fields populated, sealed
        // under CanonicalAuditPayloadV2.
        let mut v2 = make_row("modern-row", 200);
        v2.original_utterance = Some(String::from("did i pay rent?"));
        v2.retrieval_provenance = Some(RetrievalProvenance::new(
            true,
            vec![RetrievedMemoryRef {
                memory_id: String::from("mem-rent-42"),
                domain: String::from("durable"),
                score: 0.93,
            }],
        ));
        b.audit.append(&v2).expect("append v2");

        b.audit
            .verify_chain()
            .expect("mixed v1+v2 chain verifies under writer-side seal");
    }

    // Read phase — reopen to prove durability + projection round-trip.
    let b = DurableBackends::open(&path).unwrap();
    let rows = b.audit.query(&AuditFilter::default(), 100);
    assert_eq!(rows.len(), 2, "both rows must surface through query");

    let legacy = rows
        .iter()
        .find(|r| r.audit_id == AuditId("legacy-row".into()))
        .expect("v1 row present");
    assert_eq!(
        legacy.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V1,
        "v1 row must report schema_version=1 after read-back",
    );
    assert!(
        legacy.original_utterance.is_none(),
        "v1 row must not carry original_utterance",
    );
    assert!(
        legacy.retrieval_provenance.is_none(),
        "v1 row must not carry retrieval_provenance",
    );

    let modern = rows
        .iter()
        .find(|r| r.audit_id == AuditId("modern-row".into()))
        .expect("v2 row present");
    assert_eq!(
        modern.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V2,
        "v2 row must report schema_version=2 after read-back",
    );
    assert_eq!(
        modern.original_utterance.as_deref(),
        Some("did i pay rent?"),
        "v2 row must round-trip original_utterance verbatim",
    );
    let prov = modern
        .retrieval_provenance
        .as_ref()
        .expect("v2 row must carry retrieval_provenance");
    assert!(prov.block_present);
    assert_eq!(prov.hits.len(), 1);
    assert_eq!(prov.hits[0].memory_id, "mem-rent-42");

    // Chain still verifies after restart — exercises canonical_bytes
    // dispatch on the verify side, per row, with mixed schema versions.
    b.audit
        .verify_chain()
        .expect("mixed-schema chain re-verifies across restart");
}

/// True legacy on-disk payload — JSON literally lacks the three new
/// fields, mirroring what a pre-ADR-0009 writer actually wrote — read
/// back alongside a modern v2 row.
///
/// The engine-sealed v1 test above proves the dispatch covers
/// `schema_version: 1` set explicitly. This test proves the dispatch
/// also covers the *implicit* v1 case: a payload where the field is
/// missing entirely. That's the actual upgrade scenario for users
/// running a build prior to commit `f378ea5`.
#[test]
fn legacy_on_disk_payload_without_v2_fields_queries_back_as_v1() {
    use aether_l5_policy::AuditFilter;

    let (_tmp, path) = temp("legacy_payload_strip.db");

    // Seed: write a v1 row through the engine, then a v2 row, so the
    // chain head + hashes are valid.
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit
            .append(&make_row_v1("legacy-strip", 1))
            .expect("seed v1");
        b.audit
            .append(&make_row("modern-strip", 2))
            .expect("seed v2");

        // Now strip the three v2 fields from the v1 row's stored
        // payload, mimicking a row written by a pre-ADR-0009 build that
        // never knew the fields existed. The chain hash remains valid
        // because the v1 canonical form already excludes all three.
        //
        // We have to drop the append-only triggers to do this — the
        // production system would never run this UPDATE; it's a stand-in
        // for "what's actually on disk in a user's pre-upgrade DB".
        let conn = b.conn.lock().unwrap();
        conn.execute_batch(
            "DROP TRIGGER IF EXISTS policy_audit_log_no_update; \
             DROP TRIGGER IF EXISTS policy_audit_log_no_delete;",
        )
        .unwrap();

        let payload: String = conn
            .query_row(
                "SELECT payload FROM policy_audit_log WHERE audit_id = 'legacy-strip'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        let mut value: serde_json::Value = serde_json::from_str(&payload).unwrap();
        let obj = value.as_object_mut().unwrap();
        obj.remove("schema_version");
        obj.remove("original_utterance");
        obj.remove("retrieval_provenance");
        let stripped = serde_json::to_string(&value).unwrap();
        // Sanity — the on-disk payload now matches the legacy wire shape.
        assert!(!stripped.contains("schema_version"));
        assert!(!stripped.contains("original_utterance"));
        assert!(!stripped.contains("retrieval_provenance"));
        conn.execute(
            "UPDATE policy_audit_log SET payload = ?1 WHERE audit_id = 'legacy-strip'",
            aether_storage::rusqlite::params![stripped],
        )
        .unwrap();
    }

    // Read-back: query both rows and prove the projection deserializes
    // the legacy payload as v1 implicitly while preserving v2 fields on
    // the modern row.
    let b = DurableBackends::open(&path).unwrap();
    let rows = b.audit.query(&AuditFilter::default(), 100);
    assert_eq!(rows.len(), 2, "both rows surface through query");

    let legacy = rows
        .iter()
        .find(|r| r.audit_id == AuditId("legacy-strip".into()))
        .expect("legacy row present");
    assert_eq!(
        legacy.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V1,
        "absent schema_version on the wire must default to v1",
    );
    assert!(legacy.original_utterance.is_none());
    assert!(legacy.retrieval_provenance.is_none());

    let modern = rows
        .iter()
        .find(|r| r.audit_id == AuditId("modern-strip".into()))
        .expect("modern row present");
    assert_eq!(
        modern.schema_version,
        aether_l5_policy::AUDIT_SCHEMA_VERSION_V2,
    );
}

/// Tamper detection on a v1 row — mutating the payload in place must
/// break the chain even though v1 canonicalization excludes the v2
/// fields. Exercises the `canonical_bytes` dispatch on the v1 branch
/// from the verify side.
#[test]
fn tampering_v1_row_payload_breaks_chain() {
    use aether_l5_policy::storage_hooks::AuditVerifyError;

    let (_tmp, path) = temp("mixed_tamper_v1.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row_v1("v1-victim", 1)).unwrap();
        b.audit.append(&make_row("v2-follower", 2)).unwrap();
        b.audit.verify_chain().expect("clean mixed chain");

        // Tamper: mutate the v1 row's audit_id inside the stored
        // payload. Drop append-only triggers to simulate out-of-band
        // tampering.
        let conn = b.conn.lock().unwrap();
        conn.execute_batch(
            "DROP TRIGGER IF EXISTS policy_audit_log_no_update; \
             DROP TRIGGER IF EXISTS policy_audit_log_no_delete;",
        )
        .unwrap();
        let tampered = serde_json::to_string(&make_row_v1("v1-FORGED", 1)).unwrap();
        conn.execute(
            "UPDATE policy_audit_log SET payload = ?1 WHERE audit_id = 'v1-victim'",
            aether_storage::rusqlite::params![tampered],
        )
        .unwrap();
    }

    let b = DurableBackends::open(&path).unwrap();
    let err = b
        .audit
        .verify_chain()
        .expect_err("tampered v1 payload must fail chain verify");
    assert!(
        matches!(err, AuditVerifyError::ChainBreak { .. }),
        "expected ChainBreak on v1 tamper, got {err:?}",
    );
}

/// Tamper detection on a v2 row's `original_utterance` field — the
/// HIGH-1 fix put this field inside the canonical payload so a mutation
/// here must break the chain. Locks review §6 #4 explicitly: HMAC
/// coverage of the new ADR-0009 fields is no longer "implicit by
/// bytes-changing", it's a named contract.
#[test]
fn tampering_v2_original_utterance_breaks_chain() {
    use aether_l5_policy::storage_hooks::AuditVerifyError;

    let (_tmp, path) = temp("mixed_tamper_v2.db");
    {
        let b = DurableBackends::open(&path).unwrap();
        b.audit.append(&make_row_v1("v1-anchor", 1)).unwrap();

        let mut v2 = make_row("v2-victim", 2);
        v2.original_utterance = Some(String::from("the truth"));
        b.audit.append(&v2).unwrap();
        b.audit.verify_chain().expect("clean chain");

        // Tamper: rewrite the v2 row's original_utterance to a different
        // string. record_hmac stays the same — that's the whole point;
        // the verifier should detect the divergence between stored hmac
        // and re-computed hmac over the mutated canonical bytes.
        let conn = b.conn.lock().unwrap();
        conn.execute_batch(
            "DROP TRIGGER IF EXISTS policy_audit_log_no_update; \
             DROP TRIGGER IF EXISTS policy_audit_log_no_delete;",
        )
        .unwrap();
        let payload: String = conn
            .query_row(
                "SELECT payload FROM policy_audit_log WHERE audit_id = 'v2-victim'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        let mut value: serde_json::Value = serde_json::from_str(&payload).unwrap();
        value
            .as_object_mut()
            .unwrap()
            .insert("original_utterance".into(), serde_json::json!("a lie"));
        let mutated = serde_json::to_string(&value).unwrap();
        conn.execute(
            "UPDATE policy_audit_log SET payload = ?1 WHERE audit_id = 'v2-victim'",
            aether_storage::rusqlite::params![mutated],
        )
        .unwrap();
    }

    let b = DurableBackends::open(&path).unwrap();
    let err = b
        .audit
        .verify_chain()
        .expect_err("v2 original_utterance mutation must fail chain verify");
    assert!(
        matches!(err, AuditVerifyError::ChainBreak { .. }),
        "expected ChainBreak on v2 original_utterance tamper, got {err:?}",
    );
}
