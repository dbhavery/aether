-- Aether storage — migration 0001 (init)
-- Scope: L5 policy engine tables + one forward-looking shell for L2 memory items.
-- Source: ARCHITECTURE.md §3a-3d (policy)
--         ARCHITECTURE.md §3e (memory, stubbed)
-- Status: ready-to-execute DDL. rusqlite wire-up lands in Wave 3.5 once rustup
--         is installed on the dev machine. Until then, aether-storage surfaces
--         this file as a `&'static str` via `MigrationSet`.
--
-- Pragmas to apply at every connection open (executed by the driver wrapper,
-- not this file):
--   PRAGMA journal_mode = WAL;
--   PRAGMA synchronous  = NORMAL;
--   PRAGMA foreign_keys = ON;
--   PRAGMA temp_store   = MEMORY;
--   PRAGMA busy_timeout = 5000;

BEGIN;

-- ============================================================
-- L5 — policy grants (§3a)
-- ============================================================
CREATE TABLE IF NOT EXISTS policy_grants (
    grant_id            TEXT PRIMARY KEY,
    capability          TEXT NOT NULL,
    resource_scope      TEXT NOT NULL,         -- JSON: {"kind":"...","pattern":"..."}
    approval_mode       TEXT NOT NULL,
    duration_kind       TEXT NOT NULL,
    duration_param      TEXT,                  -- JSON
    issued_at           TEXT NOT NULL,         -- ISO-8601
    expires_at          TEXT,                  -- ISO-8601, nullable
    issued_by           TEXT NOT NULL,         -- 'user' | 'persona' | 'system'
    issued_by_ref       TEXT NOT NULL,
    audit_ref           TEXT NOT NULL,
    revoked_at          TEXT,
    revoked_reason      TEXT,
    actor_persona       TEXT NOT NULL,
    preset_version      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_policy_grants_capability    ON policy_grants(capability);
CREATE INDEX IF NOT EXISTS idx_policy_grants_actor_persona ON policy_grants(actor_persona);
CREATE INDEX IF NOT EXISTS idx_policy_grants_expires_at    ON policy_grants(expires_at);
CREATE INDEX IF NOT EXISTS idx_policy_grants_active
    ON policy_grants(actor_persona, capability)
    WHERE revoked_at IS NULL;

-- ============================================================
-- L5 — policy_audit_log (§3b) — APPEND-ONLY via triggers
-- ============================================================
CREATE TABLE IF NOT EXISTS policy_audit_log (
    audit_id         TEXT PRIMARY KEY,          -- ULID / UUIDv7
    timestamp        TEXT NOT NULL,
    actor_persona    TEXT NOT NULL,
    capability       TEXT NOT NULL,
    resource         TEXT NOT NULL,             -- JSON
    decision         TEXT NOT NULL,             -- 'allow'|'deny'|'ask'|'draft_only_system'|'draft_only_user'|'needs_upgrade'
    deny_reason      TEXT,
    change_id        TEXT NOT NULL,
    prev_hash        BLOB,
    record_hmac      BLOB NOT NULL,
    grant_ref        TEXT,
    payload          TEXT NOT NULL              -- JSON (full event body)
);
CREATE INDEX IF NOT EXISTS idx_policy_audit_timestamp     ON policy_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_policy_audit_change_id     ON policy_audit_log(change_id);
CREATE INDEX IF NOT EXISTS idx_policy_audit_capability    ON policy_audit_log(capability);
CREATE INDEX IF NOT EXISTS idx_policy_audit_actor_persona ON policy_audit_log(actor_persona);

-- Append-only invariant. Hard-stop any UPDATE/DELETE from non-privileged callers.
CREATE TRIGGER IF NOT EXISTS policy_audit_log_no_update
BEFORE UPDATE ON policy_audit_log
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS policy_audit_log_no_delete
BEFORE DELETE ON policy_audit_log
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_log is append-only');
END;

-- ============================================================
-- L5 — policy_audit_checkpoints (§3c)
-- ============================================================
CREATE TABLE IF NOT EXISTS policy_audit_checkpoints (
    checkpoint_id   TEXT PRIMARY KEY,
    up_to_audit_id  TEXT NOT NULL,
    head_hash       BLOB NOT NULL,
    head_hmac       BLOB NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_audit_checkpoints_created ON policy_audit_checkpoints(created_at);

-- ============================================================
-- L5 — cost_counters (§3d)
-- ============================================================
CREATE TABLE IF NOT EXISTS cost_counters (
    provider_id         TEXT NOT NULL,
    window_kind         TEXT NOT NULL,
    window_start        TEXT NOT NULL,
    tokens_used         INTEGER NOT NULL DEFAULT 0,
    dollars_used_cents  INTEGER NOT NULL DEFAULT 0,
    cap_tokens          INTEGER,
    cap_dollars_cents   INTEGER,
    last_updated        TEXT NOT NULL,
    PRIMARY KEY (provider_id, window_kind, window_start)
);
CREATE INDEX IF NOT EXISTS idx_cost_counters_provider ON cost_counters(provider_id);
CREATE INDEX IF NOT EXISTS idx_cost_counters_window   ON cost_counters(window_kind, window_start);

-- ============================================================
-- Migration bookkeeping
-- ============================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    id         TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0001_init', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
