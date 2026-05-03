-- Companion storage — migration 0003 (audit-chain hash + HMAC sealing)
-- Scope: additive. Activates the chain/HMAC pipeline that 0002 prepared.
--
-- Rationale:
--   - 0001 declared `prev_hash` and `record_hmac` on `policy_audit_log` and
--     wired the append-only triggers.
--   - 0002 added `payload` + `key_id` columns and created the
--     `policy_audit_chain_head` singleton.
--   - 0003 adds the one column still missing for full chain verification:
--     `event_hash` — SHA-256 of (prev_hash || canonical_payload) for this
--     row. Together with `prev_hash` and `record_hmac`, a verifier can walk
--     the log and detect any mutation of the payload or break in the chain
--     linkage.
--
-- Compatibility:
--   - `event_hash` is nullable so existing rows (written under Wave 4.5
--     before sealing shipped) remain readable. New rows written by the
--     Wave 4.6 `SqliteAuditStore` populate it unconditionally.
--   - Upgrade path for pre-existing unsealed rows is a future wave
--     (`0004_audit_seal_backfill.sql`); until then, `verify_chain()` skips
--     rows whose `event_hash IS NULL`, reports their count, and only fails
--     on actual mismatches for sealed rows.

BEGIN;

ALTER TABLE policy_audit_log ADD COLUMN event_hash BLOB;

CREATE INDEX IF NOT EXISTS idx_policy_audit_event_hash
    ON policy_audit_log(event_hash);

INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0003_audit_seal', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
