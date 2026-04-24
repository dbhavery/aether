//! P3 — Durable `SessionMemoryStore` backed by SQLite.
//!
//! Feature-gated behind the `sqlite-backend` cargo feature. The default
//! build of `aether-l2-memory` does not compile this module, keeping
//! cold builds unchanged for the in-memory preview.
//!
//! ## Semantics
//!
//! This store mirrors [`crate::InMemorySessionMemoryStore`]'s public
//! behaviour — assigns monotonic per-session sequences, isolates
//! sessions, and returns an oldest-first bounded `RecentMemoryWindow` —
//! but rows survive across process restarts.
//!
//! Two deliberate differences vs the in-memory store:
//!
//! 1. **`recent()` uses the bound as a read-side LIMIT**, not a
//!    write-side eviction policy. Old rows stay on disk. This matches
//!    the companion product surface ("what do you remember about me?")
//!    where durable history is the point; a future slice can add an
//!    explicit retention policy if disk usage becomes a concern.
//! 2. **`clear_session()` deletes rows.** Unlike the policy audit log
//!    (which rejects `DELETE` via triggers), a user must be able to
//!    forget their conversation. `0004_conversation_log.sql` therefore
//!    installs no append-only triggers.
//!
//! ## Wiring
//!
//! ```ignore
//! use std::sync::{Arc, Mutex};
//! use aether_storage::open_with_migrations;
//! use aether_l2_memory::{SqliteSessionMemoryStore, RecentMemoryConfig};
//!
//! let outcome = open_with_migrations("./aether.db")?;
//! let conn = Arc::new(Mutex::new(outcome.conn));
//! let store = SqliteSessionMemoryStore::new(
//!     conn,
//!     RecentMemoryConfig::default_narrow(),
//! );
//! ```
//!
//! `DurableSessionStore::open(path)` is the convenience equivalent of
//! L5's `DurableBackends::open(...)` — opens the DB, runs migrations,
//! wraps in `Arc<Mutex<_>>`.

#![cfg(feature = "sqlite-backend")]

use std::path::Path;
use std::sync::{Arc, Mutex};

use aether_storage::rusqlite::{params, Connection};
use aether_storage::OpenError;

use crate::error::L2Error;
use crate::session::{
    MemoryRole, RecentMemoryConfig, RecentMemoryWindow, SessionMemoryStore, TurnMemoryRecord,
};

/// Durable-store retention policy.
///
/// Unlike [`RecentMemoryConfig`], which governs **read-side windowing**
/// (how many rows to return from `recent()`), `RetentionPolicy` controls
/// **write-side eviction**: which rows stay on disk.
///
/// Two orthogonal dials, each optional. Applying both is a logical OR:
/// a row is evicted if it fails *either* cap.
///
/// - `max_rows_per_session` — keep only the N newest rows per session.
///   Pruning happens automatically on every `append`, so growth is
///   bounded in the steady state.
/// - `max_age_ms` — prune rows whose `timestamp_ms` is older than
///   `now - max_age_ms`. Applied only by the explicit
///   [`SqliteSessionMemoryStore::prune_session`] /
///   [`SqliteSessionMemoryStore::prune_all`] maintenance calls, because
///   `append` does not have a trusted wall clock of its own (timestamps
///   come from callers and we don't want a silently-misconfigured
///   caller to retroactively drop everyone's history).
///
/// ### Applies to every role equally
///
/// Retention prunes **old state**, full stop. Persona-switch banners,
/// approval summaries, user turns, and assistant turns are treated
/// identically — retention is not a place to special-case message
/// types. Callers who need a specific record to survive should not
/// rely on retention to preserve it.
#[derive(Debug, Clone, Copy)]
pub struct RetentionPolicy {
    /// Maximum rows retained per session. `None` = unbounded.
    pub max_rows_per_session: Option<usize>,
    /// Maximum age in milliseconds. `None` = unbounded. Only applied
    /// by explicit `prune_session` / `prune_all` calls.
    pub max_age_ms: Option<u64>,
}

impl RetentionPolicy {
    /// No retention — append-only forever. Matches the pre-P4
    /// behaviour and is the safest choice for development.
    pub const fn unbounded() -> Self {
        Self {
            max_rows_per_session: None,
            max_age_ms: None,
        }
    }

    /// Default bounded retention for the shipped companion: keep the
    /// 500 most recent rows per session, no age cap. Chosen so even a
    /// talkative user takes weeks to hit the ceiling, but the SQLite
    /// file cannot grow unbounded across years of use.
    pub const fn default_bounded() -> Self {
        Self {
            max_rows_per_session: Some(500),
            max_age_ms: None,
        }
    }
}

impl Default for RetentionPolicy {
    fn default() -> Self {
        Self::default_bounded()
    }
}

/// Default table name for the store — the Session-lane log.
/// `SqliteSessionMemoryStore::new*` constructors use this; per-domain
/// stores (e.g. Durable) use [`Self::with_table`] + its migration-created
/// sibling table. See ADR-0004.
pub const DEFAULT_TABLE: &str = "conversation_log";

/// Table name for the Durable-domain log, introduced in migration
/// `0005_durable_log.sql`. Shape-identical to [`DEFAULT_TABLE`]; pair
/// with [`Self::with_table`] (ADR-0004 §Decisions 1, 4).
pub const DURABLE_TABLE: &str = "durable_log";

/// SQLite-backed [`SessionMemoryStore`].
#[derive(Debug)]
pub struct SqliteSessionMemoryStore {
    conn: Arc<Mutex<Connection>>,
    config: RecentMemoryConfig,
    retention: RetentionPolicy,
    table_name: &'static str,
}

impl SqliteSessionMemoryStore {
    /// Build a store targeting the default `conversation_log` table with
    /// explicit read window and the [`RetentionPolicy::default_bounded`]
    /// retention policy. Use [`Self::new_with_retention`] for custom
    /// retention, or [`Self::with_table`] for per-domain stores
    /// (ADR-0004).
    pub fn new(conn: Arc<Mutex<Connection>>, config: RecentMemoryConfig) -> Self {
        Self::new_with_retention(conn, config, RetentionPolicy::default_bounded())
    }

    /// Build a store targeting `DEFAULT_TABLE` with explicit read window
    /// and retention policy.
    pub fn new_with_retention(
        conn: Arc<Mutex<Connection>>,
        config: RecentMemoryConfig,
        retention: RetentionPolicy,
    ) -> Self {
        Self::with_table(conn, config, retention, DEFAULT_TABLE)
    }

    /// Build a store targeting an arbitrary log table. Per ADR-0004,
    /// this is the constructor used by per-domain stores (Durable today;
    /// ADR-0005 will add Projects/Artifacts). The caller must ensure the
    /// table exists with the conversation-log shape; the store does not
    /// run migrations.
    pub fn with_table(
        conn: Arc<Mutex<Connection>>,
        config: RecentMemoryConfig,
        retention: RetentionPolicy,
        table_name: &'static str,
    ) -> Self {
        Self {
            conn,
            config,
            retention,
            table_name,
        }
    }

    /// Build with [`RecentMemoryConfig::default_narrow`] and
    /// [`RetentionPolicy::default_bounded`] on `DEFAULT_TABLE`.
    pub fn new_default(conn: Arc<Mutex<Connection>>) -> Self {
        Self::new(conn, RecentMemoryConfig::default_narrow())
    }

    /// Table this store writes to. Exposed for diagnostics and tests;
    /// immutable after construction.
    pub fn table_name(&self) -> &'static str {
        self.table_name
    }

    /// Retention policy this store will apply. Exposed for diagnostics
    /// and tests; policy is immutable after construction.
    pub fn retention(&self) -> RetentionPolicy {
        self.retention
    }

    /// Apply the age-based retention dial for `session_id` against
    /// `now_ms`. Rows whose `timestamp_ms` is older than
    /// `now_ms - max_age_ms` are deleted. No-op if `max_age_ms` is
    /// `None`. Returns the count of rows removed.
    pub fn prune_session(&self, session_id: &str, now_ms: u64) -> Result<usize, L2Error> {
        let Some(max_age_ms) = self.retention.max_age_ms else {
            return Ok(0);
        };
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let cutoff = now_ms.saturating_sub(max_age_ms) as i64;
        let sql = format!(
            "DELETE FROM {} WHERE session_id = ?1 AND timestamp_ms < ?2",
            self.table_name
        );
        let removed = conn
            .execute(&sql, params![session_id, cutoff])
            .map_err(|e| L2Error::Storage(format!("prune_session: {e}")))?;
        Ok(removed)
    }

    /// Explicit, configuration-free "delete everything older than
    /// `cutoff_ms`" for one session. Used by the user-facing "Forget
    /// history older than N days" surface, which computes the cutoff
    /// at the point of action and does not depend on
    /// `retention.max_age_ms` being set.
    pub fn prune_older_than(&self, session_id: &str, cutoff_ms: u64) -> Result<usize, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let sql = format!(
            "DELETE FROM {} WHERE session_id = ?1 AND timestamp_ms < ?2",
            self.table_name
        );
        let removed = conn
            .execute(&sql, params![session_id, cutoff_ms as i64])
            .map_err(|e| L2Error::Storage(format!("prune_older_than: {e}")))?;
        Ok(removed)
    }

    /// Apply the age-based retention dial to every session in the
    /// store. Useful for boot-time maintenance. Returns total rows
    /// removed. No-op if `max_age_ms` is `None`.
    pub fn prune_all(&self, now_ms: u64) -> Result<usize, L2Error> {
        let Some(max_age_ms) = self.retention.max_age_ms else {
            return Ok(0);
        };
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let cutoff = now_ms.saturating_sub(max_age_ms) as i64;
        let sql = format!("DELETE FROM {} WHERE timestamp_ms < ?1", self.table_name);
        let removed = conn
            .execute(&sql, params![cutoff])
            .map_err(|e| L2Error::Storage(format!("prune_all: {e}")))?;
        Ok(removed)
    }

    /// Enforce `max_rows_per_session` on the given session by trimming
    /// the oldest rows. Called automatically after every `append`;
    /// exposed publicly so tests and maintenance tasks can also call
    /// it directly. Returns the count of rows removed.
    fn enforce_row_cap(&self, conn: &Connection, session_id: &str) -> Result<usize, L2Error> {
        let Some(max_rows) = self.retention.max_rows_per_session else {
            return Ok(0);
        };
        if max_rows == 0 {
            // Treat 0 as "keep nothing beyond the write itself" —
            // degenerate but legal; skip to avoid nuking the row we
            // just inserted.
            return Ok(0);
        }
        // Delete rows where sequence is below `(max_sequence - max_rows + 1)`.
        // SQLite handles the subquery efficiently because `(session_id,
        // sequence)` is the primary key (declared in migration 0004 / 0005).
        let sql = format!(
            "DELETE FROM {0} \
             WHERE session_id = ?1 AND sequence <= ( \
                 SELECT MAX(sequence) - ?2 FROM {0} \
                 WHERE session_id = ?1 \
             )",
            self.table_name
        );
        let removed = conn
            .execute(&sql, params![session_id, max_rows as i64])
            .map_err(|e| L2Error::Storage(format!("enforce_row_cap: {e}")))?;
        Ok(removed)
    }

    /// Expose the shared connection so callers can run adjacent queries
    /// (future: retention policy, telemetry reads). Same pattern as
    /// `DurableBackends::conn`.
    pub fn conn(&self) -> Arc<Mutex<Connection>> {
        self.conn.clone()
    }

    fn next_sequence(&self, conn: &Connection, session_id: &str) -> Result<u64, L2Error> {
        // SQLite's MAX() returns NULL for no rows, which rusqlite maps to
        // `Option<i64>` here. Treat NULL / missing as `0` so the next
        // sequence is `1`, mirroring the in-memory store.
        let sql = format!(
            "SELECT MAX(sequence) FROM {} WHERE session_id = ?1",
            self.table_name
        );
        let max: Option<i64> = conn
            .query_row(&sql, params![session_id], |r| r.get::<_, Option<i64>>(0))
            .map_err(|e| L2Error::Storage(format!("next_sequence: {e}")))?;
        Ok((max.unwrap_or(0) as u64) + 1)
    }
}

impl SessionMemoryStore for SqliteSessionMemoryStore {
    fn append(&self, record: TurnMemoryRecord) -> Result<(), L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let seq = self.next_sequence(&conn, &record.session_id)?;
        let role = role_wire(record.role);
        let sql = format!(
            "INSERT INTO {} \
                (session_id, sequence, role, content, timestamp_ms) \
             VALUES (?1, ?2, ?3, ?4, ?5)",
            self.table_name
        );
        conn.execute(
            &sql,
            params![
                record.session_id,
                seq as i64,
                role,
                record.content,
                record.timestamp_ms as i64,
            ],
        )
        .map_err(|e| L2Error::Storage(format!("append: {e}")))?;
        // Steady-state row-count retention. Runs inside the same lock
        // so eviction is atomic with respect to concurrent reads.
        // Age-based retention is NOT applied here — see the
        // `RetentionPolicy` doc for why.
        self.enforce_row_cap(&conn, &record.session_id)?;
        Ok(())
    }

    fn recent(&self, session_id: &str) -> Result<RecentMemoryWindow, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        // Pull a bounded tail of rows from the end. The in-memory store
        // also enforces `max_chars`, but applying it symmetrically here
        // would complicate the SQL without changing behaviour for the
        // window sizes v0 actually uses (tens of turns). Deferred.
        let limit = self.config.max_turns.max(1) as i64;
        let sql = format!(
            "SELECT sequence, role, content, timestamp_ms \
             FROM {} \
             WHERE session_id = ?1 \
             ORDER BY sequence DESC \
             LIMIT ?2",
            self.table_name
        );
        let mut stmt = conn
            .prepare(&sql)
            .map_err(|e| L2Error::Storage(format!("recent prepare: {e}")))?;
        let rows = stmt
            .query_map(params![session_id, limit], |r| {
                let seq: i64 = r.get(0)?;
                let role_str: String = r.get(1)?;
                let content: String = r.get(2)?;
                let ts: i64 = r.get(3)?;
                Ok((seq, role_str, content, ts))
            })
            .map_err(|e| L2Error::Storage(format!("recent query: {e}")))?;

        // Collect (DESC) then reverse to oldest-first — cheaper than
        // ORDER BY ASC combined with a LIMIT relative to the end.
        let mut collected: Vec<TurnMemoryRecord> = Vec::new();
        for row in rows {
            let (seq, role_str, content, ts) =
                row.map_err(|e| L2Error::Storage(format!("recent row: {e}")))?;
            collected.push(TurnMemoryRecord {
                session_id: session_id.to_string(),
                sequence: seq as u64,
                role: role_from_wire(&role_str)
                    .ok_or_else(|| L2Error::Storage(format!("unknown role: {role_str}")))?,
                content,
                timestamp_ms: ts as u64,
            });
        }
        collected.reverse();

        // Secondary `max_chars` trim, applied oldest-first to mirror the
        // in-memory store's behaviour.
        let cap = self.config.max_chars;
        let mut total: usize = collected.iter().map(|r| r.content.len()).sum();
        while total > cap && collected.len() > 1 {
            let dropped = collected.remove(0);
            total = total.saturating_sub(dropped.content.len());
        }

        Ok(RecentMemoryWindow {
            session_id: session_id.to_string(),
            records: collected,
        })
    }

    fn clear_session(&self, session_id: &str) -> Result<(), L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let sql = format!("DELETE FROM {} WHERE session_id = ?1", self.table_name);
        conn.execute(&sql, params![session_id])
            .map_err(|e| L2Error::Storage(format!("clear_session: {e}")))?;
        Ok(())
    }

    fn remove(&self, session_id: &str, sequence: u64) -> Result<bool, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let sql = format!(
            "DELETE FROM {} WHERE session_id = ?1 AND sequence = ?2",
            self.table_name
        );
        let affected = conn
            .execute(&sql, params![session_id, sequence as i64])
            .map_err(|e| L2Error::Storage(format!("remove: {e}")))?;
        Ok(affected > 0)
    }

    fn update(
        &self,
        session_id: &str,
        sequence: u64,
        new_content: String,
    ) -> Result<bool, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        // Only `content` is rewritten. `role`, `timestamp_ms`, and
        // `sequence` are preserved — Memory V2 treats an "edited fact"
        // as the same item with revised text, not a new turn.
        let sql = format!(
            "UPDATE {} SET content = ?3 WHERE session_id = ?1 AND sequence = ?2",
            self.table_name
        );
        let affected = conn
            .execute(&sql, params![session_id, sequence as i64, new_content])
            .map_err(|e| L2Error::Storage(format!("update: {e}")))?;
        Ok(affected > 0)
    }

    fn prune_before(&self, session_id: &str, cutoff_ms: u64) -> Result<usize, L2Error> {
        // Delegates to the existing `prune_older_than` helper so the
        // trait call path and the explicit "forget older than N days"
        // UI call path share one implementation.
        self.prune_older_than(session_id, cutoff_ms)
    }

    fn list_sessions(&self) -> Result<Vec<String>, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let sql = format!("SELECT DISTINCT session_id FROM {}", self.table_name);
        let mut stmt = conn
            .prepare(&sql)
            .map_err(|e| L2Error::Storage(format!("list_sessions prepare: {e}")))?;
        let rows = stmt
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(|e| L2Error::Storage(format!("list_sessions query: {e}")))?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r.map_err(|e| L2Error::Storage(format!("list_sessions row: {e}")))?);
        }
        Ok(out)
    }

    fn fetch_one(
        &self,
        session_id: &str,
        sequence: u64,
    ) -> Result<Option<TurnMemoryRecord>, L2Error> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| L2Error::Internal(format!("sqlite memory lock poisoned: {e}")))?;
        let sql = format!(
            "SELECT role, content, timestamp_ms FROM {} \
             WHERE session_id = ?1 AND sequence = ?2",
            self.table_name
        );
        use aether_storage::rusqlite::Error as RusqliteError;
        let result: Result<(String, String, i64), RusqliteError> =
            conn.query_row(&sql, params![session_id, sequence as i64], |r| {
                Ok((r.get(0)?, r.get(1)?, r.get(2)?))
            });
        match result {
            Ok((role_str, content, ts)) => {
                let role = role_from_wire(&role_str)
                    .ok_or_else(|| L2Error::Storage(format!("unknown role: {role_str}")))?;
                Ok(Some(TurnMemoryRecord {
                    session_id: session_id.to_string(),
                    sequence,
                    role,
                    content,
                    timestamp_ms: ts as u64,
                }))
            }
            Err(RusqliteError::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(L2Error::Storage(format!("fetch_one: {e}"))),
        }
    }
}

/// Convenience builder that mirrors L5's `DurableBackends::open`: open
/// the DB, run migrations, wrap the connection, return a ready store.
pub struct DurableSessionStore {
    /// The store itself, as a trait object for dependency-injection sites
    /// that accept `Arc<dyn SessionMemoryStore>`.
    pub store: Arc<dyn SessionMemoryStore>,
    /// Concrete typed handle to the SQLite store so callers can reach
    /// retention maintenance (`prune_session`, `prune_all`) and future
    /// feature APIs without downcasting the trait object. `None` only
    /// in the degenerate case where a caller built the struct with a
    /// non-SQLite trait object for tests.
    concrete: Option<Arc<SqliteSessionMemoryStore>>,
    /// The shared connection, for callers that need to run adjacent
    /// queries or attach additional feature tables later.
    pub conn: Arc<Mutex<Connection>>,
}

impl DurableSessionStore {
    /// Open (or create) a SQLite DB at `path`, run migrations, and
    /// return a session-memory store sharing the live connection.
    pub fn open(path: impl AsRef<Path>) -> Result<Self, OpenError> {
        Self::open_with_config(path, RecentMemoryConfig::default_narrow())
    }

    /// Same as [`DurableSessionStore::open`] but with an explicit
    /// window config. Uses [`RetentionPolicy::default_bounded`] for
    /// retention; use [`Self::open_with_retention`] to override.
    pub fn open_with_config(
        path: impl AsRef<Path>,
        config: RecentMemoryConfig,
    ) -> Result<Self, OpenError> {
        Self::open_with_retention(path, config, RetentionPolicy::default_bounded())
    }

    /// Open with an explicit read window AND an explicit retention
    /// policy. Returns both the trait-object store and the concrete
    /// typed store so callers that want the retention maintenance
    /// surface (prune_session / prune_all) can reach it without
    /// downcasting.
    pub fn open_with_retention(
        path: impl AsRef<Path>,
        config: RecentMemoryConfig,
        retention: RetentionPolicy,
    ) -> Result<Self, OpenError> {
        let outcome = aether_storage::open_with_migrations(path)?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        let concrete = Arc::new(SqliteSessionMemoryStore::new_with_retention(
            conn.clone(),
            config,
            retention,
        ));
        let store: Arc<dyn SessionMemoryStore> = concrete.clone();
        Ok(Self {
            store,
            concrete: Some(concrete),
            conn,
        })
    }

    /// Best-effort accessor for the concrete SQLite-backed store.
    /// Present when the `DurableSessionStore` was constructed via the
    /// `open_*` builders; absent only in contrived tests that stand up
    /// their own trait-object store. Used by the shell to surface the
    /// retention maintenance API without downcasting.
    pub fn concrete(&self) -> Option<Arc<SqliteSessionMemoryStore>> {
        self.concrete.clone()
    }

    /// Open a DB and return a pair of stores targeting the Session and
    /// Durable log tables respectively, sharing one connection.
    ///
    /// The Session store targets [`DEFAULT_TABLE`] (`conversation_log`);
    /// the Durable store targets [`DURABLE_TABLE`] (`durable_log`). Both
    /// tables are guaranteed to exist after this call — migration `0005`
    /// is additive and runs automatically via `open_with_migrations`.
    ///
    /// The two stores MAY share the same `RecentMemoryConfig` (turns +
    /// char window) but typically carry different retention:
    /// - Session — `RetentionPolicy::default_bounded` (500-row cap).
    /// - Durable — `RetentionPolicy::unbounded` at the row-cap dial;
    ///   age-based pruning is driven by the shell's retention sweep
    ///   using `memory.json::retention_days.durable` (30 days default).
    ///
    /// Returns both stores plus the shared connection so the shell can
    /// retain them in a registry keyed by `MemoryDomain`. Per ADR-0004
    /// this is the canonical per-domain opener; future ADR-0005 will
    /// extend the API to include Projects / Artifacts.
    pub fn open_session_and_durable(
        path: impl AsRef<Path>,
        config: RecentMemoryConfig,
        session_retention: RetentionPolicy,
        durable_retention: RetentionPolicy,
    ) -> Result<SessionAndDurableStores, OpenError> {
        let outcome = aether_storage::open_with_migrations(path)?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        let session = Arc::new(SqliteSessionMemoryStore::with_table(
            conn.clone(),
            config,
            session_retention,
            DEFAULT_TABLE,
        ));
        let durable = Arc::new(SqliteSessionMemoryStore::with_table(
            conn.clone(),
            config,
            durable_retention,
            DURABLE_TABLE,
        ));
        Ok(SessionAndDurableStores {
            session,
            durable,
            conn,
        })
    }
}

/// Return shape for [`DurableSessionStore::open_session_and_durable`].
/// Exposed as a struct (not a tuple) so the shell-side registry wiring
/// is self-documenting and future ADR-0005 additions (projects,
/// artifacts) are straightforward field adds.
pub struct SessionAndDurableStores {
    /// Session-lane store, targets `conversation_log`.
    pub session: Arc<SqliteSessionMemoryStore>,
    /// Durable-lane store, targets `durable_log`.
    pub durable: Arc<SqliteSessionMemoryStore>,
    /// Shared connection for future per-domain additions.
    pub conn: Arc<Mutex<Connection>>,
}

fn role_wire(role: MemoryRole) -> &'static str {
    match role {
        MemoryRole::User => "user",
        MemoryRole::Assistant => "assistant",
        MemoryRole::System => "system",
    }
}

fn role_from_wire(raw: &str) -> Option<MemoryRole> {
    match raw {
        "user" => Some(MemoryRole::User),
        "assistant" => Some(MemoryRole::Assistant),
        "system" => Some(MemoryRole::System),
        _ => None,
    }
}
