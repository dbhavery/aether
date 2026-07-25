-- Companion storage — migration 0006 (policy_grants approval_scope)
-- Scope: additive. Per the T1.3 approval-scope design
-- (ARCHITECTURE.md), the L5 grant ledger
-- gains a new `approval_scope` axis describing the temporal extent over
-- which a user-issued approval applies. The Rust `Grant` struct carries
-- it as Option<ApprovalScope> with #[serde(default)], so the
-- `payload` JSON column (added in migration 0002) already round-trips
-- the field for the SqliteGrantLedger.
--
-- This migration adds a dedicated TEXT column on the table so the column
-- is filterable / indexable / queryable without parsing the JSON
-- payload — matching the precedent set by the `approval_mode` column
-- in 0001 (which is also redundant with the JSON payload but
-- separately indexable).
--
-- NULL semantics: a NULL value in this column denotes a legacy
-- (pre-T1.3) grant. The Rust read-side treats `approval_scope IS NULL`
-- as semantically equivalent to `Some(ApprovalScope::PerAction)` — the
-- same fall-through behaviour the engine had before this enum existed.
--
-- Non-null values are the serialized enum-variant names produced by
-- `serde_json::to_string(&ApprovalScope::*)` without the surrounding
-- quotes (i.e. the variant identifier as a bare TEXT value):
--   'PerAction' | 'OncePerSession' | 'OncePerTask' | 'DraftOnly'
--
-- Wave 5+ may add an index on this column if the trust-center filter
-- query proves slow under realistic grant counts; today's grant volume
-- (≤ low hundreds per session) is small enough that a seq-scan is
-- fine. Defer the index until the read-side telemetry justifies it.

BEGIN;

ALTER TABLE policy_grants ADD COLUMN approval_scope TEXT NULL;

INSERT OR IGNORE INTO schema_migrations (id, applied_at)
VALUES ('0006_policy_grants_approval_scope', strftime('%Y-%m-%dT%H:%M:%fZ','now'));

COMMIT;
