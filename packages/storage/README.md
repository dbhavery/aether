# @aether/storage

**Status:** Wave 1 scaffold — layout type only, no driver yet.

SQLite schema, migrations, encryption-at-rest, audit-chain primitives. Consumed by L2 (memory) and L5 (policy).

## References

- file:///C:/Users/dbhav/Projects/aether/planning/plans/implementation_prep/sqlite_schema_pack.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/L5_policy_engine_system_design.md
- file:///C:/Users/dbhav/Projects/aether/planning/plans/L2_memory_kernel_system_design.md

## Wave 1 contents

- `StorageLayout` — where the DB files live per X3 §7.
- `StorageError` — error surface shape.
- No driver (`rusqlite` / `sqlx` decision deferred — see `planning/OPEN_QUESTIONS.md`).
- No `migrations/` yet.

## Next wave

Wave 2 lands the driver, `Store` trait, versioned migration files, and the audit-chain helper. L2 and L5 then depend on this crate.
