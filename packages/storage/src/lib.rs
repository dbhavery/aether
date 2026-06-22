//! # aether-storage
//!
//! Local persistence substrate. **Wave 1 scaffold — no driver yet.**
//!
//! Canonical reference: `ARCHITECTURE.md` and
//! `docs/adr/ADR-0004-durable-store-shape.md` (the durable store shape, the L5
//! grants/audit tables, and the L2 memory store).
//!
//! ## Layout (per schema pack §2)
//!
//! - `aether.db` — primary user data (memory, persona, sessions, routing,
//!   grants, BYOK metadata, approvals, degraded events).
//! - `aether_audit.db` — append-only audit log + chain-head checkpoints.
//! - `aether_cost.db` (optional, likely collapsed into `aether.db` for v1).
//!
//! ## Invariants (enforced in later waves)
//!
//! - WAL mode, single-writer rule (Tauri `single-instance`).
//! - `PRAGMA foreign_keys = ON` on every open.
//! - Audit log is append-only; writes go through a hash-chain trigger.
//! - Secrets, blobs, and embeddings are **not** stored here — see schema pack §1.

#![deny(unsafe_code)]
#![warn(missing_docs)]

pub mod db;
pub mod migrations;

pub use db::{open_with_migrations, OpenError, OpenOutcome};
pub use migrations::{expected_head_id, Migration, MIGRATIONS};

// Re-export the rusqlite driver so downstream crates (notably
// `aether-l5-policy`'s `SqliteGrantLedger` / `SqliteAuditStore`) can use
// `Connection` + friends without adding a direct `rusqlite` dep. This is
// the supported integration point; do not add `rusqlite` directly to
// engine crates.
pub use rusqlite;

use std::path::PathBuf;

/// Set of DB handles Aether opens at startup.
#[derive(Debug, Clone)]
pub struct StorageLayout {
    /// Path to `aether.db`.
    pub primary: PathBuf,
    /// Path to `aether_audit.db`.
    pub audit: PathBuf,
    /// Optional `aether_cost.db`. `None` means cost lives inside `primary`.
    pub cost: Option<PathBuf>,
}

impl StorageLayout {
    /// Default layout for Aether Pro under `%APPDATA%/Aether/Pro/data/`.
    pub fn default_pro(data_root: impl Into<PathBuf>) -> Self {
        let root: PathBuf = data_root.into();
        Self {
            primary: root.join("aether.db"),
            audit: root.join("aether_audit.db"),
            cost: None,
        }
    }
}

/// Storage-layer error shape. Will expand in Wave 2 once a driver is picked.
#[derive(Debug, thiserror::Error)]
pub enum StorageError {
    /// Schema / migration version mismatch.
    #[error("schema version mismatch: expected {expected}, found {found}")]
    SchemaMismatch {
        /// Expected schema version.
        expected: u32,
        /// Found schema version.
        found: u32,
    },
    /// Audit chain hash mismatch — tampering or corruption.
    #[error("audit chain broken at row {row_id}")]
    AuditChainBroken {
        /// Row id where the break was detected.
        row_id: u64,
    },
    /// Placeholder while the driver is unchosen.
    #[error("storage driver not yet implemented — Wave 2+")]
    NotImplemented,
}

// Wave 3.5 landed the substrate: `rusqlite` is wired, `open_with_migrations`
// applies both `0001_init.sql` and `0002_audit_chain.sql` at startup. See
// `tests/migration_runs.rs` for coverage.
//
// Wave 4.5 consumes the substrate: `aether-l5-policy` exposes
// `SqliteGrantLedger` + `SqliteAuditStore` behind the `sqlite-backend`
// cargo feature and uses the re-exported `rusqlite::Connection` above.
//
// Still deferred for later waves:
// - Full hash-chain + HMAC trigger set (draft placeholder table exists via
//   0002 but the trigger pipeline is future work).
// - A `Store` trait abstracting driver choice (rusqlite vs sqlx) if one
//   becomes useful.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_pro_layout_joins_expected_files() {
        let layout = StorageLayout::default_pro(r"C:\fake\root");
        assert!(layout.primary.ends_with("aether.db"));
        assert!(layout.audit.ends_with("aether_audit.db"));
        assert!(layout.cost.is_none());
    }
}
