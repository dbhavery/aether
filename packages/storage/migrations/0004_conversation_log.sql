-- Companion storage — migration 0004 (conversation log)
-- Scope: additive. Introduces the durable session-memory table backing
-- `aether_l2_memory::SqliteSessionMemoryStore` (feature-gated behind the
-- `sqlite-backend` cargo feature on `aether-l2-memory`).
--
-- Rationale:
--   - The shell's in-memory `InMemorySessionMemoryStore` loses continuity
--     across app restarts. For a "what do you remember about me?" product
--     surface we need durable append semantics.
--   - Conversation rows are *not* append-only in the audit sense — users
--     must be able to clear their session ("forget this"). We therefore
--     do NOT install the reject-UPDATE / reject-DELETE triggers that
--     `policy_audit_log` uses. Deletes are the clear_session path.
--   - Row contents are plain TEXT because L2 is not a privacy-classified
--     surface yet. The privacy-class / provenance work lives in the
--     richer `MemoryKernel` (later wave).
--
-- Schema:
--   session_id    TEXT NOT NULL  — session correlation key (application-
--                                  chosen; `desktop-session` for v0).
--   sequence      INTEGER NOT NULL — per-session monotonic ordinal the
--                                    store assigns on append. Unique
--                                    within a session.
--   role          TEXT NOT NULL  — 'user' | 'assistant' | 'system'.
--   content       TEXT NOT NULL  — raw utterance / reply / system note.
--   timestamp_ms  INTEGER NOT NULL — caller-supplied wall-clock ms.
--
-- Index:
--   (session_id, sequence) uniquely identifies a row and is the natural
--   ORDER BY for the `recent()` query path. DESC scan + LIMIT N gives us
--   the bounded-window snapshot the in-memory store produces.

BEGIN;

CREATE TABLE IF NOT EXISTS conversation_log (
    session_id   TEXT    NOT NULL,
    sequence     INTEGER NOT NULL,
    role         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    PRIMARY KEY (session_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_conversation_log_session_timestamp
    ON conversation_log(session_id, timestamp_ms);

INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0004_conversation_log', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
