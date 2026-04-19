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

/// Ordered, append-only migration set. New migrations push to the tail.
pub const MIGRATIONS: &[Migration] = &[MIGRATION_0001_INIT];

/// Return the expected schema-version id after applying every known migration.
pub fn expected_head_id() -> &'static str {
    MIGRATIONS
        .last()
        .map(|m| m.id)
        .unwrap_or("pre-genesis")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migrations_are_monotonically_ordered() {
        let ids: Vec<_> = MIGRATIONS.iter().map(|m| m.id).collect();
        let mut sorted = ids.clone();
        sorted.sort_unstable();
        assert_eq!(ids, sorted, "MIGRATIONS must be declared in ascending order");
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
        assert_eq!(expected_head_id(), "0001_init");
    }
}
