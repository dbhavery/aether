//! Embedded migration corpus.
//!
//! Wave 3 keeps the driver wire-up deferred (no `rustup` on the dev machine at
//! time of writing). The SQL files live in `packages/storage/migrations/` and
//! are surfaced here as `&'static str` so any future driver (rusqlite, sqlx)
//! can execute them without a filesystem dependency.

/// Single migration entry.
#[derive(Debug, Clone, Copy)]
pub struct Migration {
    /// Ordinal + name, e.g. `"0001_init"`. Must be strictly increasing.
    pub id: &'static str,
    /// Raw SQL to execute in one transaction.
    pub sql: &'static str,
}

/// Initial DDL — L5 policy tables + schema_migrations bookkeeping.
pub const MIGRATION_0001_INIT: Migration = Migration {
    id: "0001_init",
    sql: include_str!("../migrations/0001_init.sql"),
};

/// Wave 4.5 — audit-chain groundwork + `payload` columns enabling the
/// `SqliteGrantLedger` / `SqliteAuditStore` backends to store full Rust
/// structs as JSON alongside the granular query columns from 0001.
pub const MIGRATION_0002_AUDIT_CHAIN: Migration = Migration {
    id: "0002_audit_chain",
    sql: include_str!("../migrations/0002_audit_chain.sql"),
};

/// Wave 4.6 — audit hash-chain + HMAC sealing. Adds `event_hash` column
/// and an index so `SqliteAuditStore::verify_chain` can walk the log in
/// order and detect tampering.
pub const MIGRATION_0003_AUDIT_SEAL: Migration = Migration {
    id: "0003_audit_seal",
    sql: include_str!("../migrations/0003_audit_seal.sql"),
};

/// P3 — Durable conversation log backing
/// `aether_l2_memory::SqliteSessionMemoryStore` (feature-gated).
pub const MIGRATION_0004_CONVERSATION_LOG: Migration = Migration {
    id: "0004_conversation_log",
    sql: include_str!("../migrations/0004_conversation_log.sql"),
};

/// ADR-0004 — Durable-domain log table for Memory V2's Durable lane.
/// Shape-identical to `conversation_log`; routed by the shell's
/// `DomainStoreRegistry` via `SqliteSessionMemoryStore::with_table`.
pub const MIGRATION_0005_DURABLE_LOG: Migration = Migration {
    id: "0005_durable_log",
    sql: include_str!("../migrations/0005_durable_log.sql"),
};

/// T1.3 §2.3 — `policy_grants.approval_scope` column. Additive; NULL =
/// legacy = PerAction-equivalent at read time. See
/// the approval-scope design in `ARCHITECTURE.md`.
pub const MIGRATION_0006_POLICY_GRANTS_APPROVAL_SCOPE: Migration = Migration {
    id: "0006_policy_grants_approval_scope",
    sql: include_str!("../migrations/0006_policy_grants_approval_scope.sql"),
};

/// Ordered, append-only migration set. New migrations push to the tail.
pub const MIGRATIONS: &[Migration] = &[
    MIGRATION_0001_INIT,
    MIGRATION_0002_AUDIT_CHAIN,
    MIGRATION_0003_AUDIT_SEAL,
    MIGRATION_0004_CONVERSATION_LOG,
    MIGRATION_0005_DURABLE_LOG,
    MIGRATION_0006_POLICY_GRANTS_APPROVAL_SCOPE,
];

/// Return the expected schema-version id after applying every known migration.
pub fn expected_head_id() -> &'static str {
    MIGRATIONS.last().map(|m| m.id).unwrap_or("pre-genesis")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrations_are_monotonically_ordered() {
        let ids: Vec<_> = MIGRATIONS.iter().map(|m| m.id).collect();
        let mut sorted = ids.clone();
        sorted.sort_unstable();
        assert_eq!(
            ids, sorted,
            "MIGRATIONS must be declared in ascending order"
        );
    }

    #[test]
    fn migration_sql_is_non_empty() {
        for m in MIGRATIONS {
            assert!(!m.sql.trim().is_empty(), "migration {} has empty SQL", m.id);
            assert!(
                m.sql.contains("schema_migrations"),
                "migration {} must touch schema_migrations bookkeeping",
                m.id
            );
        }
    }

    #[test]
    fn head_id_matches_last_entry() {
        assert_eq!(expected_head_id(), "0006_policy_grants_approval_scope");
    }
}
