# @aether/storage

**Status:** Wave 1 scaffold — layout type only, no driver yet.

SQLite schema, migrations, encryption-at-rest, audit-chain primitives. Consumed by L2 (memory) and L5 (policy).

## References

- `ARCHITECTURE.md` — the storage substrate and the L2/L5 layers it serves.
- `docs/adr/ADR-0004-durable-store-shape.md` — the durable store shape.

## Wave 1 contents

- `StorageLayout` — where the DB files live per X3 §7.
- `StorageError` — error surface shape.
- No driver (`rusqlite` / `sqlx` decision deferred — see `docs/adr/ADR-0004-durable-store-shape.md`).
- No `migrations/` yet.

## Next wave

Wave 2 lands the driver, `Store` trait, versioned migration files, and the audit-chain helper. L2 and L5 then depend on this crate.
