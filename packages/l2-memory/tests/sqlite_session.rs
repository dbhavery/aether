//! P3 integration tests — `SqliteSessionMemoryStore` against a real
//! SQLite file (via `aether-storage::open_with_migrations`).
//!
//! Gated behind the `sqlite-backend` feature so the default test run
//! stays fast and driver-free.

#![cfg(feature = "sqlite-backend")]

use aether_l2_memory::{
    DurableSessionStore, MemoryRole, RecentMemoryConfig, RetentionPolicy, SessionMemoryStore,
    SqliteSessionMemoryStore, TurnMemoryRecord, DEFAULT_TABLE, DURABLE_TABLE,
};
use tempfile::TempDir;

fn rec(session: &str, role: MemoryRole, content: &str, ts: u64) -> TurnMemoryRecord {
    TurnMemoryRecord {
        session_id: session.to_string(),
        sequence: 0,
        role,
        content: content.to_string(),
        timestamp_ms: ts,
    }
}

#[test]
fn append_and_recent_round_trip_through_real_sqlite() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db"))
        .expect("durable session store open");
    let store = db.store.clone();

    store.append(rec("s1", MemoryRole::User, "hi", 10)).unwrap();
    store
        .append(rec("s1", MemoryRole::Assistant, "hello", 20))
        .unwrap();
    store
        .append(rec("s1", MemoryRole::User, "how are you", 30))
        .unwrap();

    let w = store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 3);
    assert_eq!(w.records[0].content, "hi");
    assert_eq!(w.records[1].content, "hello");
    assert_eq!(w.records[2].content, "how are you");
    assert_eq!(w.records[0].sequence, 1);
    assert_eq!(w.records[1].sequence, 2);
    assert_eq!(w.records[2].sequence, 3);
    assert_eq!(w.records[0].timestamp_ms, 10);
}

#[test]
fn records_survive_reopen_of_the_same_db_file() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");

    {
        let db = DurableSessionStore::open(&path).unwrap();
        db.store
            .append(rec("s1", MemoryRole::User, "first", 1))
            .unwrap();
        db.store
            .append(rec("s1", MemoryRole::Assistant, "second", 2))
            .unwrap();
    }

    let db2 = DurableSessionStore::open(&path).expect("reopen");
    let w = db2.store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 2);
    assert_eq!(w.records[0].content, "first");
    assert_eq!(w.records[1].content, "second");

    // Sequences must continue, not restart — append after reopen should
    // be 3, not 1.
    db2.store
        .append(rec("s1", MemoryRole::User, "third", 3))
        .unwrap();
    let w2 = db2.store.recent("s1").unwrap();
    assert_eq!(w2.records.len(), 3);
    assert_eq!(w2.records[2].sequence, 3);
    assert_eq!(w2.records[2].content, "third");
}

#[test]
fn clear_session_removes_only_target_session() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();

    store.append(rec("s1", MemoryRole::User, "x", 1)).unwrap();
    store.append(rec("s1", MemoryRole::User, "y", 2)).unwrap();
    store.append(rec("s2", MemoryRole::User, "z", 3)).unwrap();

    store.clear_session("s1").unwrap();

    let w1 = store.recent("s1").unwrap();
    let w2 = store.recent("s2").unwrap();
    assert!(w1.is_empty());
    assert_eq!(w2.records.len(), 1);
    assert_eq!(w2.records[0].content, "z");

    // After clear, fresh appends to s1 should start a new monotonic run
    // from 1 — the old rows are gone, so MAX(sequence) is NULL.
    store.append(rec("s1", MemoryRole::User, "new", 4)).unwrap();
    let w1b = store.recent("s1").unwrap();
    assert_eq!(w1b.records.len(), 1);
    assert_eq!(w1b.records[0].sequence, 1);
}

#[test]
fn recent_bounds_to_config_max_turns_without_dropping_rows_on_disk() {
    let tmp = TempDir::new().unwrap();
    // Small limit so we can assert both "what comes back" and "disk
    // keeps everything" in the same test.
    let cfg = RecentMemoryConfig {
        max_turns: 3,
        max_chars: 10_000,
    };
    let db = DurableSessionStore::open_with_config(tmp.path().join("aether.db"), cfg).unwrap();
    let store = db.store.clone();

    for i in 0..6 {
        store
            .append(rec(
                "s1",
                MemoryRole::User,
                &format!("msg-{i}"),
                (i + 1) as u64,
            ))
            .unwrap();
    }

    // recent() returns at most max_turns, oldest-first.
    let w = store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 3);
    assert_eq!(w.records[0].content, "msg-3");
    assert_eq!(w.records[2].content, "msg-5");

    // Raw count on disk: all six rows must still be present. Durable
    // memory is write-preserving; the read path bounds, not the writer.
    let conn = db.conn.lock().unwrap();
    let on_disk: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM conversation_log WHERE session_id = 's1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(on_disk, 6);
}

#[test]
fn unknown_session_returns_empty_window_not_error() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let w = db.store.recent("never-used").unwrap();
    assert!(w.is_empty());
    assert_eq!(w.session_id, "never-used");
}

// --- P4: retention policy ---

#[test]
fn row_cap_retention_evicts_oldest_on_write() {
    let tmp = TempDir::new().unwrap();
    let retention = RetentionPolicy {
        max_rows_per_session: Some(3),
        max_age_ms: None,
    };
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig::default_narrow(),
        retention,
    )
    .expect("open with retention");
    let store = db.store.clone();

    for i in 0..7 {
        store
            .append(rec(
                "s1",
                MemoryRole::User,
                &format!("msg-{i}"),
                (i + 1) as u64,
            ))
            .unwrap();
    }

    // On-disk count bounded to retention cap.
    let conn = db.conn.lock().unwrap();
    let on_disk: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM conversation_log WHERE session_id = 's1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(on_disk, 3, "retention must cap rows on disk");

    // The surviving rows must be the three newest (highest sequences).
    let sequences: Vec<i64> = conn
        .prepare(
            "SELECT sequence FROM conversation_log WHERE session_id = 's1' \
             ORDER BY sequence ASC",
        )
        .unwrap()
        .query_map([], |r| r.get::<_, i64>(0))
        .unwrap()
        .collect::<Result<_, _>>()
        .unwrap();
    assert_eq!(sequences, vec![5, 6, 7]);
}

#[test]
fn row_cap_retention_is_per_session_not_global() {
    let tmp = TempDir::new().unwrap();
    let retention = RetentionPolicy {
        max_rows_per_session: Some(2),
        max_age_ms: None,
    };
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig::default_narrow(),
        retention,
    )
    .unwrap();
    let store = db.store.clone();

    for i in 0..4 {
        store
            .append(rec("a", MemoryRole::User, &format!("a{i}"), i as u64 + 1))
            .unwrap();
    }
    for i in 0..4 {
        store
            .append(rec("b", MemoryRole::User, &format!("b{i}"), i as u64 + 100))
            .unwrap();
    }

    // Each session capped independently.
    let conn = db.conn.lock().unwrap();
    let a_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM conversation_log WHERE session_id = 'a'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    let b_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM conversation_log WHERE session_id = 'b'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(a_count, 2);
    assert_eq!(b_count, 2);
}

#[test]
fn age_based_prune_session_drops_only_old_rows() {
    let tmp = TempDir::new().unwrap();
    let retention = RetentionPolicy {
        max_rows_per_session: None,
        max_age_ms: Some(1_000),
    };
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig {
            max_turns: 100,
            max_chars: 10_000,
        },
        retention,
    )
    .unwrap();
    let store = db.store.clone();
    let concrete = db.concrete().expect("concrete store available");

    // Four rows. "old" rows have ts 0, 100 — well below the cutoff.
    // "new" rows have ts 10_000, 20_000 — above the cutoff so they
    // must survive. max_age_ms = 1_000, now = 10_500 → cutoff = 9_500.
    store
        .append(rec("s1", MemoryRole::User, "old-a", 0))
        .unwrap();
    store
        .append(rec("s1", MemoryRole::User, "old-b", 100))
        .unwrap();
    store
        .append(rec("s1", MemoryRole::User, "new-a", 10_000))
        .unwrap();
    store
        .append(rec("s1", MemoryRole::User, "new-b", 20_000))
        .unwrap();

    let removed = concrete.prune_session("s1", 10_500).unwrap();
    assert_eq!(removed, 2, "prune should remove both old rows");

    let w = store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 2);
    assert_eq!(w.records[0].content, "new-a");
    assert_eq!(w.records[1].content, "new-b");
}

#[test]
fn age_based_prune_all_applies_across_sessions() {
    let tmp = TempDir::new().unwrap();
    let retention = RetentionPolicy {
        max_rows_per_session: None,
        max_age_ms: Some(1_000),
    };
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig::default_narrow(),
        retention,
    )
    .unwrap();
    let store = db.store.clone();
    let concrete = db.concrete().unwrap();

    // now = 20_500, max_age_ms = 1_000 → cutoff = 19_500.
    // "old" rows at 0 / 500 are below cutoff, "new" rows at 20_000 /
    // 20_100 are above.
    store
        .append(rec("a", MemoryRole::User, "a-old", 0))
        .unwrap();
    store
        .append(rec("a", MemoryRole::User, "a-new", 20_000))
        .unwrap();
    store
        .append(rec("b", MemoryRole::User, "b-old", 500))
        .unwrap();
    store
        .append(rec("b", MemoryRole::User, "b-new", 20_100))
        .unwrap();

    let removed = concrete.prune_all(20_500).unwrap();
    assert_eq!(removed, 2, "two old rows across two sessions");
    assert_eq!(store.recent("a").unwrap().records.len(), 1);
    assert_eq!(store.recent("b").unwrap().records.len(), 1);
}

#[test]
fn prune_is_noop_when_age_dial_unset() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::default_bounded(), // max_age_ms = None
    )
    .unwrap();
    let concrete = db.concrete().unwrap();
    db.store
        .append(rec("s1", MemoryRole::User, "x", 1))
        .unwrap();
    assert_eq!(concrete.prune_session("s1", 10_000_000).unwrap(), 0);
    assert_eq!(concrete.prune_all(10_000_000).unwrap(), 0);
    assert_eq!(db.store.recent("s1").unwrap().records.len(), 1);
}

#[test]
fn unbounded_retention_leaves_all_rows_on_disk() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open_with_retention(
        tmp.path().join("aether.db"),
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::unbounded(),
    )
    .unwrap();
    for i in 0..20 {
        db.store
            .append(rec("s1", MemoryRole::User, &format!("m{i}"), i as u64))
            .unwrap();
    }
    let conn = db.conn.lock().unwrap();
    let n: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM conversation_log WHERE session_id = 's1'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(n, 20);
}

// ----- remove / update (Memory V2 step 4 surface) -----

#[test]
fn remove_deletes_row_and_survives_reopen() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");
    {
        let db = DurableSessionStore::open(&path).unwrap();
        let store = db.store.clone();
        store.append(rec("s1", MemoryRole::User, "a", 1)).unwrap();
        store.append(rec("s1", MemoryRole::User, "b", 2)).unwrap();
        store.append(rec("s1", MemoryRole::User, "c", 3)).unwrap();
        assert!(store.remove("s1", 2).unwrap());
    }
    // Reopen and verify the row is actually gone from disk.
    let db = DurableSessionStore::open(&path).unwrap();
    let w = db.store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 2);
    assert!(w.records.iter().all(|r| r.sequence != 2));
    assert_eq!(w.records[0].content, "a");
    assert_eq!(w.records[1].content, "c");
}

#[test]
fn remove_unknown_row_returns_false_not_error() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();
    // No rows at all.
    assert!(!store.remove("s1", 1).unwrap());
    store.append(rec("s1", MemoryRole::User, "x", 1)).unwrap();
    // Wrong sequence.
    assert!(!store.remove("s1", 99).unwrap());
    // Wrong session.
    assert!(!store.remove("other", 1).unwrap());
    assert_eq!(store.recent("s1").unwrap().records.len(), 1);
}

#[test]
fn update_replaces_content_preserves_role_timestamp_and_sequence() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();

    store
        .append(rec("s1", MemoryRole::Assistant, "original", 42))
        .unwrap();
    assert!(store.update("s1", 1, "edited".to_string()).unwrap());

    let w = store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 1);
    assert_eq!(w.records[0].content, "edited");
    assert_eq!(w.records[0].sequence, 1);
    assert_eq!(w.records[0].role, MemoryRole::Assistant);
    assert_eq!(w.records[0].timestamp_ms, 42);
}

#[test]
fn update_unknown_row_returns_false_not_error() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();

    assert!(!store.update("never", 1, "x".into()).unwrap());
    store
        .append(rec("s1", MemoryRole::User, "orig", 1))
        .unwrap();
    assert!(!store.update("s1", 999, "x".into()).unwrap());
    assert_eq!(store.recent("s1").unwrap().records[0].content, "orig");
}

#[test]
fn update_survives_reopen() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");
    {
        let db = DurableSessionStore::open(&path).unwrap();
        let store = db.store.clone();
        store.append(rec("s1", MemoryRole::User, "v1", 1)).unwrap();
        assert!(store.update("s1", 1, "v2".to_string()).unwrap());
    }
    let db = DurableSessionStore::open(&path).unwrap();
    let w = db.store.recent("s1").unwrap();
    assert_eq!(w.records.len(), 1);
    assert_eq!(w.records[0].content, "v2");
}

// ---------- ADR-0004: per-domain table parameterization ----------

#[test]
fn default_table_constants_are_stable() {
    // Rot-guard: the shell's DomainStoreRegistry (ADR-0004 §3) keys the
    // Durable entry on this literal, and migration 0005 creates the
    // table with this exact name. A rename requires a migration + a
    // shell-side registry audit.
    assert_eq!(DEFAULT_TABLE, "conversation_log");
    assert_eq!(DURABLE_TABLE, "durable_log");
}

#[test]
fn with_table_targets_the_named_table_and_isolates_rows() {
    // Two stores sharing one DB but targeting different tables should
    // NOT see each other's rows. This is the core per-domain isolation
    // promise ADR-0004 makes.
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db"))
        .expect("durable session store open");
    let conn = db.conn.clone();
    let config = RecentMemoryConfig::default_narrow();
    let retention = RetentionPolicy::unbounded();

    let session_store =
        SqliteSessionMemoryStore::with_table(conn.clone(), config, retention, DEFAULT_TABLE);
    let durable_store =
        SqliteSessionMemoryStore::with_table(conn.clone(), config, retention, DURABLE_TABLE);

    assert_eq!(session_store.table_name(), DEFAULT_TABLE);
    assert_eq!(durable_store.table_name(), DURABLE_TABLE);

    session_store
        .append(rec("s1", MemoryRole::User, "session-only", 10))
        .unwrap();
    durable_store
        .append(rec("s1", MemoryRole::User, "durable-only", 20))
        .unwrap();

    let ses = session_store.recent("s1").unwrap();
    let dur = durable_store.recent("s1").unwrap();

    assert_eq!(ses.records.len(), 1, "session store sees only its row");
    assert_eq!(ses.records[0].content, "session-only");
    assert_eq!(dur.records.len(), 1, "durable store sees only its row");
    assert_eq!(dur.records[0].content, "durable-only");
}

#[test]
fn open_session_and_durable_returns_both_stores_on_shared_conn() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");
    let pair = DurableSessionStore::open_session_and_durable(
        &path,
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::default_bounded(),
        RetentionPolicy::unbounded(),
    )
    .expect("open_session_and_durable");

    assert_eq!(pair.session.table_name(), DEFAULT_TABLE);
    assert_eq!(pair.durable.table_name(), DURABLE_TABLE);
    assert_eq!(
        pair.session.retention().max_rows_per_session,
        Some(500),
        "Session store carries default bounded retention"
    );
    assert!(
        pair.durable.retention().max_rows_per_session.is_none(),
        "Durable store carries unbounded row-cap retention"
    );

    // Write into each and verify cross-store isolation survives reopen.
    pair.session
        .append(rec("s1", MemoryRole::User, "in-session", 1))
        .unwrap();
    pair.durable
        .append(rec("durable", MemoryRole::User, "in-durable", 2))
        .unwrap();
    drop(pair);

    let pair2 = DurableSessionStore::open_session_and_durable(
        &path,
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::default_bounded(),
        RetentionPolicy::unbounded(),
    )
    .expect("reopen");
    assert_eq!(
        pair2.session.recent("s1").unwrap().records[0].content,
        "in-session"
    );
    assert_eq!(
        pair2.durable.recent("durable").unwrap().records[0].content,
        "in-durable"
    );
    // Crucially: neither store sees the other's session_id rows.
    assert!(pair2.session.recent("durable").unwrap().records.is_empty());
    assert!(pair2.durable.recent("s1").unwrap().records.is_empty());
}

#[test]
fn durable_store_retention_prunes_only_its_own_table() {
    // If the shell sweeps Durable with a 30-day cutoff, Session rows of
    // the same age must survive. Regression test for the "shared
    // table = cross-contamination" bug ADR-0004 Option (a) would have
    // introduced.
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");
    let pair = DurableSessionStore::open_session_and_durable(
        &path,
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::unbounded(),
        RetentionPolicy::unbounded(),
    )
    .expect("open pair");
    pair.session
        .append(rec("s1", MemoryRole::User, "session-ancient", 1_000))
        .unwrap();
    pair.durable
        .append(rec("durable", MemoryRole::User, "durable-ancient", 1_000))
        .unwrap();

    // 30-day TTL means cutoff = now - 30d. We use a synthetic cutoff
    // above both timestamps to guarantee both ancient rows are "older"
    // than the cutoff.
    let cutoff = 10_000u64;
    let removed = pair.durable.prune_older_than("durable", cutoff).unwrap();
    assert_eq!(removed, 1, "durable row evicted");
    assert_eq!(
        pair.session.recent("s1").unwrap().records.len(),
        1,
        "session row must NOT be evicted by a durable-lane sweep"
    );
    assert_eq!(
        pair.durable.recent("durable").unwrap().records.len(),
        0,
        "durable lane is empty after its own sweep"
    );
}

// ---------- ADR-0005: fetch_one ----------

#[test]
fn fetch_one_returns_row_when_present() {
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();

    store
        .append(rec("s1", MemoryRole::User, "first", 100))
        .unwrap();
    store
        .append(rec("s1", MemoryRole::Assistant, "second", 200))
        .unwrap();

    let hit = store.fetch_one("s1", 2).unwrap().expect("row exists");
    assert_eq!(hit.content, "second");
    assert_eq!(hit.sequence, 2);
    assert_eq!(hit.timestamp_ms, 200);
    assert_eq!(hit.role, MemoryRole::Assistant);
}

#[test]
fn fetch_one_returns_none_when_missing() {
    // Core ADR-0005 contract: a stale embedding row whose memory has
    // been evicted must surface as Ok(None), not Err. The orchestrator
    // drops the hit and continues.
    let tmp = TempDir::new().unwrap();
    let db = DurableSessionStore::open(tmp.path().join("aether.db")).unwrap();
    let store = db.store.clone();
    assert!(store.fetch_one("s1", 999).unwrap().is_none());
    store
        .append(rec("s1", MemoryRole::User, "only", 1))
        .unwrap();
    assert!(store.fetch_one("s1", 999).unwrap().is_none());
    assert!(store.fetch_one("never-used", 1).unwrap().is_none());
}

#[test]
fn fetch_one_honours_table_parameterization() {
    // Two lanes sharing a DB: fetch_one on the durable store must not
    // find a session-lane row, and vice versa.
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("aether.db");
    let pair = DurableSessionStore::open_session_and_durable(
        &path,
        RecentMemoryConfig::default_narrow(),
        RetentionPolicy::unbounded(),
        RetentionPolicy::unbounded(),
    )
    .unwrap();

    pair.session
        .append(rec("s1", MemoryRole::User, "ses", 1))
        .unwrap();
    pair.durable
        .append(rec("s1", MemoryRole::User, "dur", 1))
        .unwrap();

    let ses = pair.session.fetch_one("s1", 1).unwrap().unwrap();
    let dur = pair.durable.fetch_one("s1", 1).unwrap().unwrap();
    assert_eq!(ses.content, "ses");
    assert_eq!(dur.content, "dur");
}
