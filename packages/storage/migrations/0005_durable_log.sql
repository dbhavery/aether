-- Companion storage — migration 0005 (durable log)
-- Scope: additive. Introduces the durable-domain log table backing
-- Memory V2's Durable lane. Shape-identical to `conversation_log`
-- (migration 0004) except for the table name — this isolation keeps
-- per-domain retention sweeps, forget semantics, and embedding
-- lifecycle from cross-contaminating Session rows.
--
-- See `docs/adr/ADR-0004-durable-store-shape.md` for the full decision
-- record. Key consequences driving this migration:
--   - The shell wires a second `SqliteSessionMemoryStore` instance
--     targeted at this table via the parameterized
--     `SqliteSessionMemoryStore::with_table` constructor.
--   - `memory.json::retention_days.durable = 30` becomes enforceable —
--     the existing retention sweep gains a `durable_log` prune path.
--   - Embedding rows for Durable memory items pair via `memory_id`
--     and are cascaded on per-item forget (flat-file store,
--     `EmbeddingStore::delete`).
--
-- Schema (matches `conversation_log`):
--   session_id    TEXT NOT NULL  — lane identifier. Single-profile today
--                                  uses the constant "durable"; a future
--                                  multi-profile release swaps to a real
--                                  profile_id with no migration cost.
--   sequence      INTEGER NOT NULL — per-lane monotonic ordinal.
--   role          TEXT NOT NULL  — 'user' | 'assistant' | 'system'.
--   content       TEXT NOT NULL  — raw utterance / reply / system note.
--   timestamp_ms  INTEGER NOT NULL — caller-supplied wall-clock ms.
--
-- Index mirrors `conversation_log`'s — the retention sweep uses
-- (session_id, timestamp_ms) for prune-before queries.

BEGIN;

CREATE TABLE IF NOT EXISTS durable_log (
    session_id   TEXT    NOT NULL,
    sequence     INTEGER NOT NULL,
    role         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    PRIMARY KEY (session_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_durable_log_session_timestamp
    ON durable_log(session_id, timestamp_ms);

INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0005_durable_log', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
