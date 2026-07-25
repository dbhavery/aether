-- Companion storage — migration 0002 (audit-chain groundwork + L5 payload columns)
-- Scope: additive. No destructive changes to 0001.
--
-- Rationale:
--   - L5 Wave 4.5 wires SqliteGrantLedger + SqliteAuditStore behind a
--     cargo feature flag. The in-memory Rust structs (`Grant`,
--     `AuditRecordEvent`) carry richer data than the 0001 schema could
--     fully granularize. Rather than reshape 0001's column-level layout,
--     we add a `payload` column to each L5 table and let the Rust backends
--     serialize the full struct as JSON. The existing granular columns
--     stay for query-path indexing and future migrations.
--   - The audit chain head is set up as a singleton table so future waves
--     can do O(1) boot-time chain-tip reads. Columns are nullable until
--     the first row is written.
--   - `key_id` + `privileged_profile` columns on `policy_audit_log` carry
--     the two `AuditRecordEvent` fields that belong in query-path indexing
--     rather than buried inside the JSON payload.

BEGIN;

-- ============================================================
-- policy_grants: payload carrier for SqliteGrantLedger
-- ============================================================
ALTER TABLE policy_grants ADD COLUMN payload TEXT;

-- ============================================================
-- policy_audit_log: hash-chain groundwork + payload extension
-- ============================================================
-- 0001 already declared `payload TEXT NOT NULL` on policy_audit_log.
ALTER TABLE policy_audit_log ADD COLUMN key_id TEXT;
ALTER TABLE policy_audit_log ADD COLUMN privileged_profile INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_policy_audit_key_id
    ON policy_audit_log(key_id);

-- ============================================================
-- policy_audit_chain_head: singleton tracking the rolling chain tip
-- ============================================================
-- Written by future hash-chain wave. Wave 4.5 creates the row so the
-- update path is an UPDATE, not an INSERT+UPDATE race.
CREATE TABLE IF NOT EXISTS policy_audit_chain_head (
    id              INTEGER PRIMARY KEY CHECK (id = 1),  -- enforce singleton
    head_audit_id   TEXT,                                -- null before first row
    head_hash       BLOB,                                -- null before first row
    updated_at      TEXT NOT NULL
);

INSERT OR IGNORE INTO policy_audit_chain_head (id, head_audit_id, head_hash, updated_at)
VALUES (1, NULL, NULL, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- ============================================================
-- Migration bookkeeping
-- ============================================================
INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0002_audit_chain', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
