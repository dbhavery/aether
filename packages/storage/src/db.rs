//! SQLite open + migration runner.
//!
//! Wave 3.5 narrow scope: open (or create) a SQLite database at a given path,
//! apply every entry in [`MIGRATIONS`] that has not yet been recorded in the
//! `schema_migrations` table, and return the live connection.
//!
//! This module intentionally does **not** provide any L5-specific helpers —
//! switching L5's in-memory ledger / audit store onto SQLite-backed
//! implementations is deferred to a later wave. This entry point is the
//! substrate only.
//!
//! ## Pragmas
//!
//! Every connection opened through [`open_with_migrations`] gets the
//! connection-level pragmas listed in `migrations/0001_init.sql` header:
//!
//! - `journal_mode = WAL`
//! - `synchronous  = NORMAL`
//! - `foreign_keys = ON`
//! - `temp_store   = MEMORY`
//! - `busy_timeout = 5000`
//!
//! These are applied *before* running migrations.

use std::path::{Path, PathBuf};

use rusqlite::Connection;

use crate::migrations::{Migration, MIGRATIONS};

/// Outcome of an [`open_with_migrations`] call.
#[derive(Debug)]
pub struct OpenOutcome {
    /// Live SQLite connection.
    pub conn: Connection,
    /// Path the connection was opened against.
    pub path: PathBuf,
    /// Migration ids that were applied during this open. Empty on a warm open.
    pub applied: Vec<&'static str>,
}

/// Errors surfaced by the open / migration pipeline.
#[derive(Debug, thiserror::Error)]
pub enum OpenError {
    /// Underlying SQLite / driver error.
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),

    /// A migration that was previously recorded is not present in the
    /// in-binary [`MIGRATIONS`] slice. Running a downgrade binary against a
    /// newer database is the usual cause.
    #[error("unknown migration '{found}' recorded in database; binary has no such migration")]
    UnknownRecordedMigration {
        /// Migration id found on disk that this binary does not recognize.
        found: String,
    },

    /// The migrations recorded in the database diverge from the in-binary
    /// list at some position — for example, the ordering changed or an
    /// earlier migration was swapped out.
    #[error("migration order mismatch at position {position}: database has '{found}', binary has '{expected}'")]
    OrderMismatch {
        /// Zero-based position in the ordered migration list.
        position: usize,
        /// Migration id recorded in the database at that position.
        found: String,
        /// Migration id the binary expected at that position.
        expected: &'static str,
    },
}

/// Open (or create) a SQLite database at `path` and apply all pending
/// migrations from [`MIGRATIONS`].
///
/// On a cold open against an empty file, every migration runs and is
/// recorded. On a warm open where the `schema_migrations` table already
/// matches the prefix of [`MIGRATIONS`], the function is a no-op beyond
/// applying connection pragmas.
pub fn open_with_migrations(path: impl AsRef<Path>) -> Result<OpenOutcome, OpenError> {
    let path_ref = path.as_ref();
    let conn = Connection::open(path_ref)?;

    apply_pragmas(&conn)?;

    let applied = run_pending_migrations(&conn, MIGRATIONS)?;

    Ok(OpenOutcome {
        conn,
        path: path_ref.to_path_buf(),
        applied,
    })
}

fn apply_pragmas(conn: &Connection) -> Result<(), rusqlite::Error> {
    // journal_mode returns a row; use query_row to consume it.
    let _journal: String = conn.query_row("PRAGMA journal_mode = WAL", [], |row| row.get(0))?;
    conn.execute_batch(
        "PRAGMA synchronous  = NORMAL;\n\
         PRAGMA foreign_keys = ON;\n\
         PRAGMA temp_store   = MEMORY;\n\
         PRAGMA busy_timeout = 5000;",
    )?;
    Ok(())
}

/// Run any migrations that are not yet recorded in `schema_migrations`.
///
/// If the database already carries some recorded migrations, they must
/// exactly match the prefix of `set` (same ids, same order). Divergence is
/// surfaced as [`OpenError::OrderMismatch`] or
/// [`OpenError::UnknownRecordedMigration`] — we never silently skip.
fn run_pending_migrations(
    conn: &Connection,
    set: &[Migration],
) -> Result<Vec<&'static str>, OpenError> {
    // Bootstrap schema_migrations so we can read it even on an empty DB.
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_migrations (\n\
             id         TEXT PRIMARY KEY,\n\
             applied_at TEXT NOT NULL\n\
         );",
    )?;

    let recorded: Vec<String> = {
        let mut stmt = conn.prepare("SELECT id FROM schema_migrations ORDER BY id ASC")?;
        let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        out
    };

    // Verify recorded prefix matches binary ordering.
    for (idx, found) in recorded.iter().enumerate() {
        match set.get(idx) {
            Some(m) if m.id == found.as_str() => continue,
            Some(m) => {
                return Err(OpenError::OrderMismatch {
                    position: idx,
                    found: found.clone(),
                    expected: m.id,
                });
            }
            None => {
                return Err(OpenError::UnknownRecordedMigration {
                    found: found.clone(),
                });
            }
        }
    }

    let mut applied: Vec<&'static str> = Vec::new();
    for m in set.iter().skip(recorded.len()) {
        // Each migration file already wraps itself in BEGIN/COMMIT and inserts
        // its own row into schema_migrations. `execute_batch` runs the whole
        // script in one shot.
        conn.execute_batch(m.sql).map_err(|e| {
            tracing::error!(migration = m.id, "migration failed");
            e
        })?;
        applied.push(m.id);
    }

    Ok(applied)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migration_runner_bails_on_unknown_recorded_migration() {
        // Simulate a downgrade: binary only knows of 0001_init, but the DB
        // thinks 9999_future ran.
        let conn = Connection::open_in_memory().unwrap();
        apply_pragmas(&conn).unwrap();
        conn.execute_batch(
            "CREATE TABLE schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL);\n\
             INSERT INTO schema_migrations VALUES ('9999_future', '2026-04-19T00:00:00.000Z');",
        )
        .unwrap();

        let err = run_pending_migrations(&conn, MIGRATIONS).unwrap_err();
        matches!(
            err,
            OpenError::OrderMismatch { .. } | OpenError::UnknownRecordedMigration { .. }
        );
    }
}
