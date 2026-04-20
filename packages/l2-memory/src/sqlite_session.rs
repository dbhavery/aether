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

/// SQLite-backed [`SessionMemoryStore`].
#[derive(Debug)]
pub struct SqliteSessionMemoryStore {
    conn: Arc<Mutex<Connection>>,
    config: RecentMemoryConfig,
}

impl SqliteSessionMemoryStore {
    /// Build a store from a shared connection. Callers are expected to
    /// have already run migrations via
    /// [`aether_storage::open_with_migrations`]; the relevant migration
    /// is `0004_conversation_log.sql`.
    pub fn new(conn: Arc<Mutex<Connection>>, config: RecentMemoryConfig) -> Self {
        Self { conn, config }
    }

    /// Build with [`RecentMemoryConfig::default_narrow`].
    pub fn new_default(conn: Arc<Mutex<Connection>>) -> Self {
        Self::new(conn, RecentMemoryConfig::default_narrow())
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
        let max: Option<i64> = conn
            .query_row(
                "SELECT MAX(sequence) FROM conversation_log WHERE session_id = ?1",
                params![session_id],
                |r| r.get::<_, Option<i64>>(0),
            )
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
        conn.execute(
            "INSERT INTO conversation_log \
                (session_id, sequence, role, content, timestamp_ms) \
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                record.session_id,
                seq as i64,
                role,
                record.content,
                record.timestamp_ms as i64,
            ],
        )
        .map_err(|e| L2Error::Storage(format!("append: {e}")))?;
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
        let mut stmt = conn
            .prepare(
                "SELECT sequence, role, content, timestamp_ms \
                 FROM conversation_log \
                 WHERE session_id = ?1 \
                 ORDER BY sequence DESC \
                 LIMIT ?2",
            )
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
        conn.execute(
            "DELETE FROM conversation_log WHERE session_id = ?1",
            params![session_id],
        )
        .map_err(|e| L2Error::Storage(format!("clear_session: {e}")))?;
        Ok(())
    }
}

/// Convenience builder that mirrors L5's `DurableBackends::open`: open
/// the DB, run migrations, wrap the connection, return a ready store.
pub struct DurableSessionStore {
    /// The store itself, as a trait object for dependency-injection sites
    /// that accept `Arc<dyn SessionMemoryStore>`.
    pub store: Arc<dyn SessionMemoryStore>,
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
    /// window config.
    pub fn open_with_config(
        path: impl AsRef<Path>,
        config: RecentMemoryConfig,
    ) -> Result<Self, OpenError> {
        let outcome = aether_storage::open_with_migrations(path)?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        let store: Arc<dyn SessionMemoryStore> =
            Arc::new(SqliteSessionMemoryStore::new(conn.clone(), config));
        Ok(Self { store, conn })
    }
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
