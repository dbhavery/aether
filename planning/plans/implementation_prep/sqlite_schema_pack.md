# SQLite Schema Pack — Aether Local Store (DRAFT)

> **Status:** DRAFT — not yet ratified. All DDL below is illustrative and subject to change pending resolution of open questions (§11).
> **Scope:** Local persistence for Aether Pro (Tauri desktop app). Single-user, single-device primary; Phase-5 sync is out of scope for this draft.
> **Primary sources:**
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L5_policy_engine_system_design.md (§7 grants, §8 audit, §9 cost counters)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L2_memory_kernel_system_design.md (§7 memory tables)
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L6_persona_compiler_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L1_interaction_timing_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/L4_model_router_system_design.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/X3_tauri_architecture.md (§7 FS scopes, §8.1 single-writer rule)
> - file:///C:/Users/dbhav/Projects/aether-planning/planning/monorepo_plan_draft.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L2_interface_pack.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L5_interface_pack.md
> - file:///C:/Users/dbhav/Projects/aether-planning/plans/implementation_prep/L6_interface_pack.md

---

## 1. Scope

**Lives in SQLite:**
- Policy grants (L5 §7)
- Policy audit log + chain-head checkpoints (L5 §8)
- Cost counters (L5 §9)
- Memory items + provenance + tags + retention + tombstones (L2 §7)
- Memory artifact links (blob pointers) and embedding references (external vector-store IDs)
- Persona profiles (installed pack registry)
- Compiled persona artifacts cache (per-kind blobs)
- Interaction session metadata (L1 — sessions, turn counts, tier transitions)
- Routing decision log (L4)
- BYOK credential *metadata* (provider, key-ref handle, rotation schedule) — **NOT** key material
- Approval request tickets (user-facing interactive approvals)
- Degraded-mode events log
- Schema version registry (per-component migration state)

**Does NOT live in SQLite:**
- **Memory blobs** — filesystem, content-addressed under `%APPDATA%/Aether/Pro/data/blobs/<hash-prefix>/<hash>`
- **Embeddings (vectors)** — external vector store (vendor TBD — see §11)
- **Secrets / key material** — OS keyring (Windows Credential Manager via `tauri-plugin-stronghold` or equivalent)
- **Persona pack YAML files** — filesystem under `%APPDATA%/Aether/Pro/personas/<persona_id>/<version>/`
- **Large binary artifacts** (images, audio) — filesystem blob store
- **Live model weights / caches** — outside scope

---

## 2. Database Layout

Per X3 §7 filesystem scopes, Aether Pro data root is `%APPDATA%/Aether/Pro/data/`.

**Proposed layout:**

| DB file | Purpose | Rationale |
|---|---|---|
| file:///C:/Users/dbhav/AppData/Roaming/Aether/Pro/data/aether.db | Primary user data (memory, persona, sessions, routing, grants, BYOK meta, approvals, degraded events) | One DB for related tables keeps referential integrity + atomic multi-table writes |
| file:///C:/Users/dbhav/AppData/Roaming/Aether/Pro/data/aether_audit.db | Append-only audit log + checkpoints | Isolation: audit cannot be corrupted by a bad migration on primary DB; different backup/retention policy; read-mostly after write |
| file:///C:/Users/dbhav/AppData/Roaming/Aether/Pro/data/aether_cost.db | Cost counters (optional, see below) | **OPEN:** could collapse into aether.db. Justification for separation: high write churn (per-request updates), bounded size, easily rebuildable from audit log. Justification for merge: fewer handles, simpler transactions. **Recommendation:** collapse into aether.db for v1 (single ATTACH) and split only if contention measured. |

**Single-writer rule (X3 §8.1):** `tauri-plugin-single-instance` ensures one Aether process per user session. Multiple backend threads use a single connection pool with a single writer (SQLite WAL mode permits concurrent readers).

**Pragmas applied at open:**

```sql
-- DRAFT — SQLite pragmas set on every connection open
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;
PRAGMA busy_timeout = 5000;
-- SQLCipher only:
-- PRAGMA key = '<derived-from-OS-keyring-master-key>';
-- PRAGMA cipher_page_size = 4096;
```

---

## 3. Draft Tables

All DDL below is **DRAFT**.

### 3a. policy_grants (L5 §7)

```sql
-- DRAFT
CREATE TABLE policy_grants (
    grant_id          TEXT PRIMARY KEY,
    capability        TEXT NOT NULL,
    resource_scope    TEXT NOT NULL,          -- JSON: {"kind":"...", "pattern":"..."}
    approval_mode     TEXT NOT NULL,          -- 'always_ask' | 'once' | 'session' | 'duration' | 'standing'
    duration_kind     TEXT NOT NULL,          -- 'none' | 'session' | 'until_ts' | 'count' | 'rolling'
    duration_param    TEXT,                   -- JSON: e.g. {"seconds":3600} | {"count":5}
    issued_at         TEXT NOT NULL,          -- ISO-8601
    expires_at        TEXT,                   -- ISO-8601 nullable
    issued_by         TEXT NOT NULL,          -- 'user' | 'persona' | 'system'
    issued_by_ref     TEXT NOT NULL,          -- persona_id or 'user:<local-account>'
    audit_ref         TEXT NOT NULL,          -- change_id linking to policy_audit_log
    revoked_at        TEXT,                   -- ISO-8601 nullable
    revoked_reason    TEXT,
    actor_persona     TEXT NOT NULL
);

CREATE INDEX idx_policy_grants_capability     ON policy_grants(capability);
CREATE INDEX idx_policy_grants_actor_persona  ON policy_grants(actor_persona);
CREATE INDEX idx_policy_grants_expires_at     ON policy_grants(expires_at);
CREATE INDEX idx_policy_grants_active         ON policy_grants(actor_persona, capability)
    WHERE revoked_at IS NULL;
```

### 3b. policy_audit_log (L5 §8) — APPEND-ONLY

```sql
-- DRAFT
CREATE TABLE policy_audit_log (
    audit_id         TEXT PRIMARY KEY,        -- ULID or UUIDv7 preferred (time-sortable)
    timestamp        TEXT NOT NULL,           -- ISO-8601
    actor_persona    TEXT NOT NULL,
    capability       TEXT NOT NULL,
    resource         TEXT NOT NULL,           -- JSON
    decision         TEXT NOT NULL,           -- 'allow' | 'deny' | 'ask' | 'revoke' | 'issue'
    deny_reason      TEXT,
    change_id        TEXT NOT NULL,           -- correlation id, unique per logical decision
    prev_hash        BLOB,                    -- hash of previous record (nullable on genesis)
    record_hmac      BLOB NOT NULL,           -- HMAC over this record's canonical serialization
    grant_ref        TEXT,                    -- FK-ish to policy_grants.grant_id (soft)
    payload          TEXT NOT NULL            -- JSON: full structured detail
);

CREATE INDEX idx_policy_audit_timestamp     ON policy_audit_log(timestamp);
CREATE INDEX idx_policy_audit_change_id     ON policy_audit_log(change_id);
CREATE INDEX idx_policy_audit_capability    ON policy_audit_log(capability);
CREATE INDEX idx_policy_audit_actor_persona ON policy_audit_log(actor_persona);

-- Append-only triggers (see §4)
```

### 3c. policy_audit_checkpoints

```sql
-- DRAFT
CREATE TABLE policy_audit_checkpoints (
    checkpoint_id   TEXT PRIMARY KEY,
    up_to_audit_id  TEXT NOT NULL,            -- last audit_id included in this chain head
    head_hash       BLOB NOT NULL,            -- rolling hash at that point
    head_hmac       BLOB NOT NULL,            -- HMAC over (up_to_audit_id || head_hash)
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_policy_audit_checkpoints_created ON policy_audit_checkpoints(created_at);
```

### 3d. cost_counters (L5 §9)

```sql
-- DRAFT
CREATE TABLE cost_counters (
    provider_id         TEXT NOT NULL,
    window_kind         TEXT NOT NULL,        -- 'daily' | 'weekly' | 'monthly' | 'rolling_24h'
    window_start        TEXT NOT NULL,        -- ISO-8601 (start of window)
    tokens_used         INTEGER NOT NULL DEFAULT 0,
    dollars_used_cents  INTEGER NOT NULL DEFAULT 0,
    cap_tokens          INTEGER,
    cap_dollars_cents   INTEGER,
    last_updated        TEXT NOT NULL,
    PRIMARY KEY (provider_id, window_kind, window_start)
);

CREATE INDEX idx_cost_counters_provider ON cost_counters(provider_id);
CREATE INDEX idx_cost_counters_window   ON cost_counters(window_kind, window_start);
```

### 3e. memory_items (L2 §7)

```sql
-- DRAFT
CREATE TABLE memory_items (
    memory_id           TEXT PRIMARY KEY,
    domain              TEXT NOT NULL,        -- 'personal' | 'work' | 'health' | ...
    content_summary     TEXT NOT NULL,
    content_ref         TEXT,                 -- filesystem blob path (content-addressed), nullable if inline
    content_inline      TEXT,                 -- short-content fast path; NULL if content_ref set
    source_kind         TEXT NOT NULL,        -- 'conversation' | 'file' | 'observation' | 'import' | 'persona'
    source_ref          TEXT NOT NULL,        -- source-kind-specific reference
    confidence          REAL NOT NULL,        -- 0.0 — 1.0
    recency_ts          TEXT NOT NULL,        -- ISO-8601 of the underlying event (not write time)
    salience            REAL NOT NULL DEFAULT 0.0,
    privacy_class       TEXT NOT NULL,        -- 'public' | 'private' | 'sensitive' | 'secret'
    revocable           INTEGER NOT NULL DEFAULT 1,   -- 0/1
    retention_kind      TEXT NOT NULL,        -- 'ephemeral' | 'session' | 'days' | 'permanent'
    retention_expires   TEXT,                 -- ISO-8601 nullable
    created_by          TEXT NOT NULL,        -- persona_id or 'user' or 'system'
    last_accessed_ts    TEXT,
    access_count        INTEGER NOT NULL DEFAULT 0,
    editable            INTEGER NOT NULL DEFAULT 1,
    tombstoned          INTEGER NOT NULL DEFAULT 0,
    tombstoned_at       TEXT,
    schema_version      INTEGER NOT NULL,
    CHECK (content_ref IS NOT NULL OR content_inline IS NOT NULL),
    CHECK (tombstoned IN (0,1)),
    CHECK (revocable IN (0,1))
);

CREATE INDEX idx_memory_domain            ON memory_items(domain);
CREATE INDEX idx_memory_privacy_class     ON memory_items(privacy_class);
CREATE INDEX idx_memory_retention_expires ON memory_items(retention_expires);
CREATE INDEX idx_memory_recency           ON memory_items(recency_ts);
CREATE INDEX idx_memory_salience          ON memory_items(salience DESC);
CREATE INDEX idx_memory_live              ON memory_items(domain, salience DESC)
    WHERE tombstoned = 0;
```

### 3f. memory_provenance

```sql
-- DRAFT
CREATE TABLE memory_provenance (
    memory_id              TEXT NOT NULL,
    provenance_idx         INTEGER NOT NULL,
    source_kind            TEXT NOT NULL,
    source_ref             TEXT NOT NULL,
    confidence_contribution REAL NOT NULL,
    PRIMARY KEY (memory_id, provenance_idx),
    FOREIGN KEY (memory_id) REFERENCES memory_items(memory_id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_provenance_source_ref ON memory_provenance(source_ref);
```

### 3g. memory_tags

```sql
-- DRAFT
CREATE TABLE memory_tags (
    memory_id  TEXT NOT NULL,
    tag_kind   TEXT NOT NULL,                 -- 'domain' | 'topic' | 'entity' | 'sentiment' | ...
    tag_value  TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag_kind, tag_value),
    FOREIGN KEY (memory_id) REFERENCES memory_items(memory_id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_tags_kv ON memory_tags(tag_kind, tag_value);
```

### 3h. memory_artifact_links

```sql
-- DRAFT
CREATE TABLE memory_artifact_links (
    memory_id    TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,               -- filesystem blob path (content-addressed)
    link_kind    TEXT NOT NULL,               -- 'source' | 'attachment' | 'derived' | 'screenshot'
    PRIMARY KEY (memory_id, artifact_ref),
    FOREIGN KEY (memory_id) REFERENCES memory_items(memory_id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_artifact_kind ON memory_artifact_links(link_kind);
```

### 3i. memory_embeddings_ref

```sql
-- DRAFT
CREATE TABLE memory_embeddings_ref (
    memory_id        TEXT NOT NULL,
    vector_store_id  TEXT NOT NULL,           -- external index row id
    model_id         TEXT NOT NULL,           -- embedding model identifier
    model_version    TEXT NOT NULL,
    dimensions       INTEGER NOT NULL,
    PRIMARY KEY (memory_id, model_id, model_version),
    FOREIGN KEY (memory_id) REFERENCES memory_items(memory_id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_embeddings_model ON memory_embeddings_ref(model_id, model_version);
```

### 3j. memory_tombstones — APPEND-ONLY (with windowed hard-delete)

```sql
-- DRAFT
CREATE TABLE memory_tombstones (
    memory_id           TEXT PRIMARY KEY,
    tombstoned_at       TEXT NOT NULL,
    reason              TEXT NOT NULL,        -- 'user_request' | 'retention_expired' | 'revocation' | 'policy'
    committed           INTEGER NOT NULL DEFAULT 0,     -- 0/1
    hard_delete_after   TEXT NOT NULL        -- ISO-8601; grace window before blob + row removal
);

CREATE INDEX idx_memory_tombstones_hard_delete ON memory_tombstones(hard_delete_after);
```

### 3k. persona_profiles (L6)

```sql
-- DRAFT
CREATE TABLE persona_profiles (
    persona_id            TEXT PRIMARY KEY,
    version               TEXT NOT NULL,
    display_name          TEXT NOT NULL,
    pack_ref              TEXT NOT NULL,      -- filesystem path to YAML pack root
    signature_verified    INTEGER NOT NULL DEFAULT 0,    -- 0/1
    is_privileged_overlay INTEGER NOT NULL DEFAULT 0,    -- 0/1
    installed_at          TEXT NOT NULL
);

CREATE INDEX idx_persona_profiles_version ON persona_profiles(persona_id, version);
```

### 3l. compiled_persona_artifacts (L6) — APPEND-ONLY after commit

```sql
-- DRAFT
CREATE TABLE compiled_persona_artifacts (
    persona_id     TEXT NOT NULL,
    version        TEXT NOT NULL,
    compiled_at    TEXT NOT NULL,
    change_id      TEXT NOT NULL,            -- correlation with policy_audit_log
    artifact_kind  TEXT NOT NULL,            -- 'language' | 'salience' | 'visual' | 'routing' | 'policy_defaults' | 'summary'
    artifact_blob  BLOB NOT NULL,            -- JSON (optionally compressed)
    PRIMARY KEY (persona_id, version, artifact_kind),
    FOREIGN KEY (persona_id) REFERENCES persona_profiles(persona_id) ON DELETE RESTRICT
);

CREATE INDEX idx_compiled_persona_artifacts_compiled_at ON compiled_persona_artifacts(compiled_at);
```

### 3m. interaction_sessions (L1)

```sql
-- DRAFT
CREATE TABLE interaction_sessions (
    session_id         TEXT PRIMARY KEY,
    started_at         TEXT NOT NULL,
    ended_at           TEXT,
    active_persona_id  TEXT NOT NULL,
    tier_at_start      TEXT NOT NULL,        -- tier enum per L1
    tier_last          TEXT NOT NULL,
    turn_count         INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (active_persona_id) REFERENCES persona_profiles(persona_id) ON DELETE RESTRICT
);

CREATE INDEX idx_interaction_sessions_started ON interaction_sessions(started_at);
CREATE INDEX idx_interaction_sessions_persona ON interaction_sessions(active_persona_id);
```

### 3n. routing_decisions (L4) — APPEND-ONLY

```sql
-- DRAFT
CREATE TABLE routing_decisions (
    decision_id          TEXT PRIMARY KEY,
    turn_id              TEXT NOT NULL,
    chosen_tier          TEXT NOT NULL,
    chosen_provider      TEXT NOT NULL,
    rationale            TEXT NOT NULL,       -- JSON
    cost_estimate_cents  INTEGER,
    decided_at           TEXT NOT NULL,
    policy_decision_ref  TEXT,                -- change_id of related L5 decision
    fallback_chain       TEXT                 -- JSON array of providers
);

CREATE INDEX idx_routing_decisions_turn_id    ON routing_decisions(turn_id);
CREATE INDEX idx_routing_decisions_decided_at ON routing_decisions(decided_at);
CREATE INDEX idx_routing_decisions_provider   ON routing_decisions(chosen_provider);
```

### 3o. byok_credentials_meta (L4)

```sql
-- DRAFT
-- NOTE: no key material is ever stored here. Only a handle to the OS keyring entry.
CREATE TABLE byok_credentials_meta (
    provider_id       TEXT PRIMARY KEY,
    key_ref           TEXT NOT NULL,          -- OS-keyring handle (opaque string)
    created_at        TEXT NOT NULL,
    last_rotated_at   TEXT,
    rotation_due      TEXT,
    scope_limits      TEXT,                   -- JSON: rate/usage/region restrictions declared by user
    last_used_at      TEXT
);

CREATE INDEX idx_byok_rotation_due ON byok_credentials_meta(rotation_due);
```

### 3p. approval_requests

```sql
-- DRAFT
CREATE TABLE approval_requests (
    ticket_id                TEXT PRIMARY KEY,
    action_request_payload   TEXT NOT NULL,   -- JSON: capability + resource + rationale
    created_at               TEXT NOT NULL,
    deadline_at              TEXT,
    responded_at             TEXT,
    response_choice          TEXT,            -- 'allow' | 'allow_once' | 'allow_session' | 'deny'
    response_scope           TEXT,            -- JSON: scope narrowing/widening chosen by user
    change_id                TEXT NOT NULL
);

CREATE INDEX idx_approval_requests_open     ON approval_requests(created_at) WHERE responded_at IS NULL;
CREATE INDEX idx_approval_requests_deadline ON approval_requests(deadline_at);
```

### 3q. degraded_mode_events

```sql
-- DRAFT
CREATE TABLE degraded_mode_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    entered_at    TEXT NOT NULL,
    cleared_at    TEXT,
    mode          TEXT NOT NULL,              -- e.g. 'offline_only' | 'read_only_memory' | 'policy_fail_closed'
    trigger_layer TEXT NOT NULL,              -- which L# raised the condition
    details       TEXT                        -- JSON
);

CREATE INDEX idx_degraded_entered ON degraded_mode_events(entered_at);
CREATE INDEX idx_degraded_mode    ON degraded_mode_events(mode);
```

### 3r. schema_versions (migration registry)

```sql
-- DRAFT
CREATE TABLE schema_versions (
    component  TEXT PRIMARY KEY,              -- 'policy' | 'memory' | 'persona' | 'router' | 'interaction' | 'core'
    version    INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
```

---

## 4. Append-Only Triggers

Append-only tables enforce their invariant with `BEFORE UPDATE` / `BEFORE DELETE` triggers that `RAISE(ABORT, ...)`. Any legitimate mutation (e.g. tombstone hard-delete after grace window) is performed via a controlled maintenance path that temporarily drops the relevant trigger inside a transaction, or — preferred — uses a sentinel column rather than a physical delete.

### 4a. policy_audit_log (canonical example)

```sql
-- DRAFT
CREATE TRIGGER policy_audit_log_no_update
BEFORE UPDATE ON policy_audit_log
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_log is append-only');
END;

CREATE TRIGGER policy_audit_log_no_delete
BEFORE DELETE ON policy_audit_log
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_log is append-only');
END;
```

### 4b. policy_audit_checkpoints

```sql
-- DRAFT
CREATE TRIGGER policy_audit_checkpoints_no_update
BEFORE UPDATE ON policy_audit_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_checkpoints is append-only');
END;

CREATE TRIGGER policy_audit_checkpoints_no_delete
BEFORE DELETE ON policy_audit_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'policy_audit_checkpoints is append-only');
END;
```

### 4c. memory_tombstones — no delete before `hard_delete_after`

```sql
-- DRAFT
CREATE TRIGGER memory_tombstones_no_update
BEFORE UPDATE ON memory_tombstones
WHEN OLD.committed = 1 AND (NEW.memory_id <> OLD.memory_id
                            OR NEW.tombstoned_at <> OLD.tombstoned_at
                            OR NEW.reason <> OLD.reason)
BEGIN
    SELECT RAISE(ABORT, 'memory_tombstones rows are immutable once committed');
END;

CREATE TRIGGER memory_tombstones_no_early_delete
BEFORE DELETE ON memory_tombstones
WHEN OLD.hard_delete_after > strftime('%Y-%m-%dT%H:%M:%fZ','now')
BEGIN
    SELECT RAISE(ABORT, 'memory_tombstones cannot be deleted before hard_delete_after window elapses');
END;
```

### 4d. compiled_persona_artifacts — no update after commit

```sql
-- DRAFT
CREATE TRIGGER compiled_persona_artifacts_no_update
BEFORE UPDATE ON compiled_persona_artifacts
BEGIN
    SELECT RAISE(ABORT, 'compiled_persona_artifacts is immutable after commit; write a new (version, artifact_kind) row');
END;

CREATE TRIGGER compiled_persona_artifacts_no_delete
BEFORE DELETE ON compiled_persona_artifacts
BEGIN
    SELECT RAISE(ABORT, 'compiled_persona_artifacts is append-only (use GC maintenance path for obsolete versions)');
END;
```

### 4e. routing_decisions — no update/delete

```sql
-- DRAFT
CREATE TRIGGER routing_decisions_no_update
BEFORE UPDATE ON routing_decisions
BEGIN
    SELECT RAISE(ABORT, 'routing_decisions is append-only');
END;

CREATE TRIGGER routing_decisions_no_delete
BEFORE DELETE ON routing_decisions
BEGIN
    SELECT RAISE(ABORT, 'routing_decisions is append-only');
END;
```

**Summary of append-only tables:**
- `policy_audit_log`
- `policy_audit_checkpoints`
- `memory_tombstones` (with windowed hard-delete exception)
- `compiled_persona_artifacts` (post-commit)
- `routing_decisions`

---

## 5. Retention and Tombstones

Memory deletion follows a **two-phase** protocol to guarantee auditability and recoverability.

**Phase 1 — Tombstone (soft delete):**

1. Retention engine scans `memory_items` where `retention_expires <= now()` AND `tombstoned = 0`.
2. Emits a `memory_retention_expired` event through the policy audit channel (written to `policy_audit_log`).
3. Sets `memory_items.tombstoned = 1`, `tombstoned_at = now()`.
4. Inserts row into `memory_tombstones` with `reason='retention_expired'`, `committed=1`, `hard_delete_after = now() + RETENTION_GRACE`.
5. Memory is now excluded from reads (by an index predicate / query filter).

**Phase 2 — Hard delete (after grace):**

1. Maintenance task selects `memory_tombstones WHERE hard_delete_after <= now()`.
2. For each: remove referenced blob from filesystem (ref-counted if shared across memories).
3. Remove vector-store entry via `memory_embeddings_ref`.
4. Delete the `memory_items` row (cascades to `memory_provenance`, `memory_tags`, `memory_artifact_links`, `memory_embeddings_ref`).
5. The `memory_tombstones` row itself is **retained** as the permanent record ("a memory with this id used to exist, tombstoned for reason X at time Y, hard-deleted at time Z"). A separate GC policy may purge very old tombstones, but only after confirming no references remain in audit queries.
6. All steps produce `policy_audit_log` entries.

**Other tombstone reasons:**
- `user_request` — explicit "forget this" from UI.
- `revocation` — policy revocation cascades to memories derived from a revoked grant (L5 revocation path).
- `policy` — privacy class tightening caused re-classification that excluded the memory.

---

## 6. Hash-Chain and HMAC (Audit)

**Rule:** every insert into `policy_audit_log` is computed in-process before commit.

- `prev_hash` = hash (SHA-256) of the canonical serialization of the immediately prior audit row. Genesis row has `prev_hash = NULL`.
- `record_hmac` = HMAC-SHA-256 keyed with `HMAC_KEY` over the canonical serialization of the current row (including `prev_hash`).
- `HMAC_KEY` is derived from the OS-keyring master key (never read from disk in plaintext).

**Checkpoints** (`policy_audit_checkpoints`) allow O(1) verification of chain integrity up to a known good point without replaying the entire log. A background task writes a checkpoint every N records or T minutes (tunable, DRAFT: N=1000 or T=15min).

**Verification:**
1. Load latest checkpoint.
2. For each row after `up_to_audit_id`: recompute `prev_hash` and `record_hmac`, compare.
3. A mismatch = tamper event → raise degraded-mode flag (`policy_fail_closed`) and surface to user.

**Key rotation:**
- A new HMAC epoch begins when key rotates. A rotation record is written into `policy_audit_log` (payload: old-key-fingerprint, new-key-fingerprint, rotated_at).
- Old records remain verifiable with retained old-key fingerprint; verifier selects key by row timestamp or by walking rotation records.
- Rotation cadence is **OPEN** (see §11).

---

## 7. Migration Considerations

**Migration pipeline:**
- Per-component migrations live under file:///C:/Users/dbhav/Projects/aether/migrations/ with subdirs `policy/`, `memory/`, `persona/`, `router/`, `interaction/`, `core/`.
- Files named `NNN_short_description.sql` where NNN is zero-padded monotonic integer per component.
- Applied atomically at startup inside a single transaction per migration.
- On success: insert/update `schema_versions (component, version, applied_at)`.
- Each migration emits a `schema_migrated` entry into `policy_audit_log` (preserves forensic trail of schema changes).
- Forward-only; rollback = new migration, not an undo file. Manual backup taken via `VACUUM INTO` before any migration.

**Churn profile:**

| Table | Write rate | Size profile |
|---|---|---|
| `memory_items` | High (ongoing ingestion) | Large (millions over years) |
| `policy_audit_log` | High (every decision) | Very large; partition via periodic archive out of primary DB if needed |
| `cost_counters` | Very high (per-request UPSERT) | Small (bounded by providers × windows) |
| `routing_decisions` | High (per turn) | Medium |
| `interaction_sessions` | Medium | Small |
| `persona_profiles` | Low | Tiny |
| `compiled_persona_artifacts` | Low (on persona change) | Medium (blobs) |
| `byok_credentials_meta` | Low | Tiny |
| `approval_requests` | Low–medium | Small (TTL-capped) |
| `degraded_mode_events` | Low (event-driven) | Small |

Stable tables (`persona_profiles`, `byok_credentials_meta`, `schema_versions`) rarely need migrations. High-churn append-only tables (`policy_audit_log`) should get a long-term archive strategy (monthly export to signed archive files) — deferred to post-MVP.

---

## 8. Index Strategy

| Table | Index | Rationale |
|---|---|---|
| `policy_grants` | `(capability)`, `(actor_persona)`, `(expires_at)`, partial `(actor_persona, capability) WHERE revoked_at IS NULL` | Fast grant lookup on every policy check; expiry scan for GC |
| `policy_audit_log` | `(timestamp)`, `(change_id)`, `(capability)`, `(actor_persona)` | Audit UI browse by time; correlation by change_id; per-capability forensics |
| `policy_audit_checkpoints` | `(created_at)` | Find most recent checkpoint fast |
| `cost_counters` | `(provider_id)`, `(window_kind, window_start)` | Cap checks at request time; rollup queries |
| `memory_items` | `(domain)`, `(privacy_class)`, `(retention_expires)`, `(recency_ts)`, `(salience DESC)`, partial `(domain, salience DESC) WHERE tombstoned=0` | Domain-scoped retrieval; privacy filter; retention sweep; recency + salience ranking hot path |
| `memory_provenance` | `(source_ref)` | Reverse lookup: which memories derived from source X |
| `memory_tags` | `(tag_kind, tag_value)` | Tag-based retrieval |
| `memory_artifact_links` | `(link_kind)` | Find all derived / source artifacts |
| `memory_embeddings_ref` | `(model_id, model_version)` | Re-embedding campaigns, model deprecation sweeps |
| `memory_tombstones` | `(hard_delete_after)` | GC scan |
| `persona_profiles` | `(persona_id, version)` | Version browse |
| `compiled_persona_artifacts` | `(compiled_at)` | Recency / cache-freshness queries |
| `interaction_sessions` | `(started_at)`, `(active_persona_id)` | History UI; per-persona analytics |
| `routing_decisions` | `(turn_id)`, `(decided_at)`, `(chosen_provider)` | Per-turn correlation; provider analytics |
| `byok_credentials_meta` | `(rotation_due)` | Rotation reminder sweep |
| `approval_requests` | partial `(created_at) WHERE responded_at IS NULL`, `(deadline_at)` | Open-ticket UI; expiry sweep |
| `degraded_mode_events` | `(entered_at)`, `(mode)` | Incident forensics |

---

## 9. Encryption

**Recommendation:** SQLCipher whole-DB for `aether.db` and `aether_audit.db`. Key derivation:
- Master key held in OS keyring (Windows Credential Manager).
- At app launch, Aether fetches master key, derives per-DB key via HKDF(master_key, info="aether-db:<db-name>:v1").
- `PRAGMA key = '<derived>'` applied on each connection.

**Alternative (OPEN, §11):** per-column encryption only on sensitive fields (`memory_items.content_inline`, `memory_items.content_summary`, `memory_provenance.source_ref`, `policy_audit_log.payload`). Benefit: indexes remain usable on non-encrypted columns without SQLCipher overhead. Drawback: leaks metadata; more error-prone; index on encrypted columns impossible.

**Dev / CI builds:** unencrypted DB is permitted with a prominent warning banner and a refusal to open any file that looks like a production DB (magic-byte check). A dev-env flag `AETHER_DB_ALLOW_PLAINTEXT=1` must be set.

**Backup encryption:** `VACUUM INTO` snapshots use the same SQLCipher key, so backups are encrypted at rest by default.

---

## 10. Integrity and Audit Notes

- **Append-only enumeration:** `policy_audit_log`, `policy_audit_checkpoints`, `memory_tombstones` (conditional), `compiled_persona_artifacts` (post-commit), `routing_decisions`.
- `PRAGMA foreign_keys = ON` on every connection (SQLite requires this per-connection).
- `PRAGMA journal_mode = WAL` — crash safety + concurrent readers.
- Single-writer enforced at process level via `tauri-plugin-single-instance` plus a single writer pool inside the backend.
- Scheduled `PRAGMA integrity_check;` — nightly background task; mismatch raises degraded-mode.
- Backup: `VACUUM INTO 'file:///C:/Users/dbhav/AppData/Roaming/Aether/Pro/data/backups/aether-YYYYMMDD-HHMM.db'`. Rotation policy DRAFT: daily for 7d, weekly for 4w, monthly for 12m.
- Post-restore verification: re-run audit chain verification from genesis or latest checkpoint.

---

## 11. Open Questions

1. **Vector store vendor.** `sqlite-vss` (in-process, keeps everything in one file-scope ecosystem), `lancedb` (embedded, columnar, strong performance), or `qdrant-embedded` (richer filter DSL, heavier). Trade-off: in-process simplicity vs. scale headroom vs. licensing. **Blocking** for finalizing `memory_embeddings_ref` schema and for sync design.
2. **Encryption scheme.** SQLCipher whole-DB vs. per-column encryption. Whole-DB is simpler and strictly stronger at rest; per-column keeps indexing fully functional without SQLCipher dependency. **Blocking** for build toolchain + dependency decisions.
3. **CRDT vs. op-log for Phase-5 sync.** Affects whether tables need vector clocks / lamport columns / tombstone semantics beyond what's drafted. If CRDT: add `updated_at`, `replica_id`, `op_id` columns to mutable tables and design merge functions now rather than retrofitting. **Blocking** if multi-device sync is desired early; safe to defer if strictly single-device for v1.
4. **Separate audit DB vs. merged.** Recommendation is separate for isolation; final call depends on migration tooling + backup ergonomics.
5. **HMAC key rotation cadence.** Draft: 90 days. Needs security review.
6. **Retention grace period length** (`hard_delete_after` window). Draft: 7 days for user-requested deletes, 30 days for retention-expired, 0 days for policy revocations. Needs product decision.
7. **Cost DB collapse.** Draft recommends merging `aether_cost.db` into `aether.db`. Confirm after load testing.

---

### Three open items most blocking for implementation

1. **Vector store vendor** — blocks `memory_embeddings_ref` finalization and the embedding-write path (L2 pipeline).
2. **Encryption scheme (SQLCipher whole-DB vs per-column)** — blocks dependency pinning, build pipeline, and keying code paths.
3. **CRDT vs op-log sync model** — blocks whether sync-metadata columns get added to mutable tables now (cheaper) or retrofitted later (expensive migration).
