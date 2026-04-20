//! Wave 3.5 integration test — proves that `open_with_migrations` actually
//! executes the drafted DDL against a real SQLite file.
//!
//! Covers the audit question "do migrations truly run?" raised in the
//! Wave 3.5 plan, and the follow-up "are they idempotent across reopens?".

use aether_storage::{expected_head_id, open_with_migrations, MIGRATIONS};
use tempfile::TempDir;

/// Every table declared in `0001_init.sql` must exist after a cold open.
#[test]
fn cold_open_creates_all_policy_tables() {
    let tmp = TempDir::new().unwrap();
    let db_path = tmp.path().join("aether.db");

    let outcome = open_with_migrations(&db_path).expect("cold open should succeed");

    assert_eq!(
        outcome.applied,
        MIGRATIONS.iter().map(|m| m.id).collect::<Vec<_>>(),
        "cold open should apply every migration in the binary"
    );
    assert_eq!(outcome.path, db_path);

    // Every table enumerated in 0001_init.sql must be present.
    let expected_tables = [
        "policy_grants",
        "policy_audit_log",
        "policy_audit_checkpoints",
        "cost_counters",
        "schema_migrations",
    ];
    for table in expected_tables {
        let count: i64 = outcome
            .conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?1",
                [table],
                |r| r.get(0),
            )
            .unwrap_or_else(|e| panic!("failed to query for table '{table}': {e}"));
        assert_eq!(count, 1, "expected table '{table}' to exist after migrations");
    }
}

/// After a cold open, the append-only triggers on `policy_audit_log` must
/// reject `DELETE` from ordinary callers. This is the single invariant the
/// planning corpus calls load-bearing for the audit log.
#[test]
fn audit_log_rejects_delete() {
    let tmp = TempDir::new().unwrap();
    let outcome = open_with_migrations(tmp.path().join("aether.db")).unwrap();

    // Seed one row directly — normally this happens through the policy
    // engine, but we are asserting the SQL trigger, not the engine.
    outcome
        .conn
        .execute(
            "INSERT INTO policy_audit_log \
                (audit_id, timestamp, actor_persona, capability, resource, decision, change_id, record_hmac, payload) \
             VALUES ('a1', '2026-04-19T00:00:00Z', 'p', 'cap', '{}', 'allow', 'c1', X'00', '{}')",
            [],
        )
        .expect("seed row");

    let err = outcome
        .conn
        .execute("DELETE FROM policy_audit_log WHERE audit_id='a1'", [])
        .expect_err("DELETE must be rejected by the append-only trigger");

    assert!(
        err.to_string().to_lowercase().contains("append-only"),
        "expected trigger ABORT message, got: {err}"
    );
}

/// Reopening the same DB must be a no-op — every migration already recorded,
/// nothing applied a second time.
#[test]
fn warm_open_is_idempotent() {
    let tmp = TempDir::new().unwrap();
    let db_path = tmp.path().join("aether.db");

    let first = open_with_migrations(&db_path).unwrap();
    drop(first);

    let second = open_with_migrations(&db_path).expect("warm open should succeed");
    assert!(
        second.applied.is_empty(),
        "warm open should apply zero migrations, got {:?}",
        second.applied
    );

    // The head id helper should agree with what is actually on disk.
    let head_on_disk: String = second
        .conn
        .query_row(
            "SELECT id FROM schema_migrations ORDER BY id DESC LIMIT 1",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(head_on_disk, expected_head_id());
}
