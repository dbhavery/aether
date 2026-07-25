//! Wave 4.5 — SQLite-backed `GrantLedger` and `AuditStore` implementations.
//!
//! Feature-gated behind the `sqlite-backend` cargo feature. The default build
//! of `aether-l5-policy` does not compile this module, keeping cold builds
//! unchanged for the in-memory preview mode.
//!
//! ## Wiring
//!
//! Use the [`aether_storage::open_with_migrations`] helper to obtain a
//! [`Connection`] whose schema matches both `0001_init.sql` and
//! `0002_audit_chain.sql`, then pass the connection to
//! [`SqliteGrantLedger::new`] / [`SqliteAuditStore::new`]. The
//! [`DurableBackends`] convenience builder opens a single DB and returns
//! both backends sharing a `Mutex<Connection>`.
//!
//! ## Storage layout
//!
//! - **Grants** are stored in `policy_grants`. The canonical form of a
//!   [`Grant`] is the JSON payload in the new `payload` column (added by
//!   0002). A few indexed columns (`grant_id`, `actor_persona`,
//!   `revoked_at`, `revoked_reason`) are populated for query-path
//!   filtering. Other 0001 columns (capability, resource_scope, etc.) are
//!   filled with canonical strings derived from the payload so they can be
//!   used by external observers or future migrations without re-parsing.
//! - **Audit rows** are stored in `policy_audit_log`. Again the canonical
//!   form is the JSON payload in the pre-existing `payload` column; the
//!   indexed columns (timestamp, actor_persona, capability, decision,
//!   change_id, key_id, privileged_profile) are populated for query paths.
//!
//! ## Limitations (explicit)
//!
//! - `verify_chain` currently returns `Ok(())` unconditionally. The 0001
//!   append-only triggers already reject `UPDATE` / `DELETE`, which gives
//!   us the weak-tamper guarantee the in-memory store also promised.
//!   Full hash-chain + HMAC verification is a future wave once
//!   `key_id`-driven rotation and a keyring integration land.
//! - `covers` fetches matching active grants via `snapshot` + Rust-side
//!   filtering. Works correctly on the preview's expected grant counts
//!   (tens to low hundreds). A future wave can push the `ResourceScope`
//!   coverage logic into SQL for very large ledgers.
//! - The `query` / `snapshot` filters do not yet push `capability`,
//!   `persona`, or `decisions` filters into SQL — they filter in Rust
//!   after a broad `SELECT`. Correct but not optimal at scale.

#![cfg(feature = "sqlite-backend")]

use std::path::Path;
use std::sync::{Arc, Mutex};

use aether_storage::rusqlite::Connection;
use aether_storage::OpenError;

use crate::audit::{AuditFilter, AuditId, AuditRecordEvent};
use crate::capability::{Capability, ResourceScope};
use crate::common::PersonaId;
use crate::events::RevokeReason;
use crate::grants::{Grant, GrantFilter, GrantId, GrantLedger};
use crate::storage_hooks::{AuditStore, AuditVerifyError, AuditWriteError};

// ---------------------------------------------------------------------------
// SqliteGrantLedger
// ---------------------------------------------------------------------------

/// SQLite-backed [`GrantLedger`]. Stores the full [`Grant`] as JSON in the
/// `payload` column added by `0002_audit_chain.sql`, with a handful of
/// granular columns populated for query-path indexing.
///
/// Thread-safe: the driver connection is held in an internal `Mutex`.
#[derive(Debug)]
pub struct SqliteGrantLedger {
    conn: Arc<Mutex<Connection>>,
}

impl SqliteGrantLedger {
    /// Build a ledger from a shared connection. Callers are expected to
    /// have already run migrations via `aether_storage::open_with_migrations`.
    pub fn new(conn: Arc<Mutex<Connection>>) -> Self {
        Self { conn }
    }
}

impl GrantLedger for SqliteGrantLedger {
    fn snapshot(&self, filter: &GrantFilter) -> Vec<Grant> {
        let conn = self.conn.lock().expect("grant ledger mutex poisoned");
        let sql = if filter.active_only {
            "SELECT payload FROM policy_grants \
             WHERE payload IS NOT NULL AND revoked_at IS NULL"
        } else {
            "SELECT payload FROM policy_grants WHERE payload IS NOT NULL"
        };
        let mut stmt = match conn.prepare(sql) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };
        let rows = stmt.query_map([], |r| r.get::<_, String>(0));
        let Ok(rows) = rows else { return Vec::new() };
        rows.filter_map(|r| r.ok())
            .filter_map(|payload| serde_json::from_str::<Grant>(&payload).ok())
            .filter(|g| match &filter.persona_id {
                Some(p) => g.persona_id == *p,
                None => true,
            })
            .filter(|g| match &filter.capability {
                Some(c) => g.capability == *c,
                None => true,
            })
            .collect()
    }

    fn issue(&self, grant: Grant) -> Option<GrantId> {
        let payload = serde_json::to_string(&grant).ok()?;
        let conn = self.conn.lock().expect("grant ledger mutex poisoned");

        let cap_tag = capability_tag(&grant.capability);
        let resource_json = serde_json::to_string(&grant.resource_pattern).ok()?;
        let approval_json = serde_json::to_string(&grant.approval_mode).ok()?;
        let (duration_kind, duration_param) = duration_to_columns(&grant.duration);
        let issued_at = grant.issued_at.0 as i64;
        let expires_at = grant.expires_at.map(|t| t.0 as i64);
        let persona_ref = grant.persona_id.0.clone();

        let id = grant.grant_id.clone();
        let res = conn.execute(
            "INSERT OR REPLACE INTO policy_grants (\
                 grant_id, capability, resource_scope, approval_mode, \
                 duration_kind, duration_param, issued_at, expires_at, \
                 issued_by, issued_by_ref, audit_ref, actor_persona, \
                 preset_version, payload\
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            aether_storage::rusqlite::params![
                id.0,
                cap_tag,
                resource_json,
                approval_json,
                duration_kind,
                duration_param,
                issued_at.to_string(),
                expires_at.map(|e| e.to_string()),
                "persona",
                persona_ref.clone(),
                String::new(),
                persona_ref,
                grant.preset_version_issued_under as i64,
                payload,
            ],
        );
        res.ok().map(|_| id)
    }

    fn revoke(&self, grant_id: &GrantId, reason: RevokeReason) {
        let conn = self.conn.lock().expect("grant ledger mutex poisoned");
        let reason_str = serde_json::to_string(&reason).unwrap_or_else(|_| "\"?\"".into());
        let _ = conn.execute(
            "UPDATE policy_grants \
             SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), \
                 revoked_reason = ?1 \
             WHERE grant_id = ?2 AND revoked_at IS NULL",
            aether_storage::rusqlite::params![reason_str, grant_id.0],
        );
    }

    fn covers(
        &self,
        capability: &Capability,
        resource: &ResourceScope,
        persona: &PersonaId,
    ) -> Option<GrantId> {
        // Fetch active grants for the persona + capability, check scope in Rust.
        let snap = self.snapshot(&GrantFilter {
            active_only: true,
            persona_id: Some(persona.clone()),
            capability: Some(capability.clone()),
        });
        for g in snap {
            if scope_covers(&g.resource_pattern, resource) {
                return Some(g.grant_id);
            }
        }
        None
    }
}

fn duration_to_columns(d: &crate::grants::GrantDuration) -> (&'static str, Option<String>) {
    match d {
        crate::grants::GrantDuration::Once => ("once", None),
        crate::grants::GrantDuration::TaskScoped(t) => {
            ("task_scoped", serde_json::to_string(t).ok())
        }
        crate::grants::GrantDuration::Session => ("session", None),
        crate::grants::GrantDuration::Persistent { ttl } => {
            ("persistent", serde_json::to_string(ttl).ok())
        }
    }
}

fn capability_tag(cap: &Capability) -> String {
    // Use the serde representation as the indexable string form. Variants
    // that carry payloads (e.g. `IntegrationUse(IntegrationId)`) will
    // serialize as JSON objects; those are still unique per capability
    // instance for indexing purposes.
    serde_json::to_string(cap).unwrap_or_else(|_| "\"?\"".into())
}

/// Match the Wave 3 in-memory semantics for `ResourceScope` coverage.
fn scope_covers(pattern: &ResourceScope, target: &ResourceScope) -> bool {
    match (pattern, target) {
        (ResourceScope::None, _) => true,
        (ResourceScope::Path(pat), ResourceScope::Path(t)) => t.starts_with(pat.as_str()),
        (ResourceScope::Url(pat), ResourceScope::Url(t)) => t.starts_with(pat.as_str()),
        (ResourceScope::Mailbox(p), ResourceScope::Mailbox(t)) => p == t,
        (ResourceScope::Integration(p), ResourceScope::Integration(t)) => p == t,
        (
            ResourceScope::CostScope {
                provider: pp,
                window: pw,
            },
            ResourceScope::CostScope {
                provider: tp,
                window: tw,
            },
        ) => pp == tp && pw == tw,
        _ => false,
    }
}

// ---------------------------------------------------------------------------
// SqliteAuditStore
// ---------------------------------------------------------------------------

/// SQLite-backed [`AuditStore`]. Writes append-only rows to
/// `policy_audit_log` — `UPDATE` / `DELETE` are rejected by triggers
/// declared in `0001_init.sql`, and every row is sealed with the Wave 4.6
/// hash-chain + HMAC pipeline (`audit_seal` module).
#[derive(Debug)]
pub struct SqliteAuditStore {
    conn: Arc<Mutex<Connection>>,
    key: crate::audit_seal::HmacKey,
}

impl SqliteAuditStore {
    /// Build an audit store from a shared connection + HMAC signing key.
    /// Assumes migrations 0001 / 0002 / 0003 have been run.
    pub fn new(conn: Arc<Mutex<Connection>>, key: crate::audit_seal::HmacKey) -> Self {
        Self { conn, key }
    }

    /// Key id the store is sealing with. Useful for tests and reporting.
    pub fn key_id(&self) -> &crate::audit::KeyId {
        self.key.id()
    }
}

impl AuditStore for SqliteAuditStore {
    fn append(&self, row: &AuditRecordEvent) -> Result<AuditId, AuditWriteError> {
        // Build a sealed copy of the incoming row: the caller's supplied
        // prev_hash / record_hmac / key_id are overwritten with values
        // derived from the current chain head and the configured key.
        // This keeps `AuditRecordEvent` a plain data struct and prevents
        // callers from accidentally forging sealing fields.
        let conn = self
            .conn
            .lock()
            .map_err(|e| AuditWriteError::Io(format!("mutex poisoned: {e}")))?;

        let prev_hash: Vec<u8> = read_chain_head(&conn)
            .map_err(|e| AuditWriteError::Io(e.to_string()))?
            .unwrap_or_else(|| crate::audit_seal::GENESIS_PREV_HASH.to_vec());

        let mut sealed = row.clone();
        sealed.prev_hash = prev_hash.clone();
        sealed.key_id = self.key.id().clone();

        let canonical = crate::audit_seal::canonical_bytes(&sealed)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let event_hash = crate::audit_seal::compute_event_hash(&prev_hash, &canonical);
        let hmac_bytes = crate::audit_seal::compute_event_hmac(&self.key, &event_hash);
        sealed.record_hmac = hmac_bytes.to_vec();

        let payload = serde_json::to_string(&sealed)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;

        let cap_tag = capability_tag(&sealed.capability);
        let resource_json = serde_json::to_string(&sealed.resource)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let actor_ref = serde_json::to_string(&sealed.actor)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let decision_tag = format!("{:?}", sealed.decision).to_lowercase();

        conn.execute(
            "INSERT INTO policy_audit_log (\
                 audit_id, timestamp, actor_persona, capability, resource, \
                 decision, change_id, prev_hash, record_hmac, payload, \
                 key_id, privileged_profile, event_hash\
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
            aether_storage::rusqlite::params![
                sealed.audit_id.0,
                sealed.timestamp_monotonic.0 as i64,
                actor_ref,
                cap_tag,
                resource_json,
                decision_tag,
                sealed.change_id.0.clone(),
                prev_hash.clone(),
                hmac_bytes.to_vec(),
                payload,
                sealed.key_id.0.clone(),
                sealed.privileged_profile as i64,
                event_hash.to_vec(),
            ],
        )
        .map_err(|e| AuditWriteError::Io(e.to_string()))?;

        update_chain_head(&conn, &sealed.audit_id, &event_hash)
            .map_err(|e| AuditWriteError::Io(e.to_string()))?;

        Ok(sealed.audit_id)
    }

    fn query(&self, filter: &AuditFilter, limit: u32) -> Vec<AuditRecordEvent> {
        let conn = match self.conn.lock() {
            Ok(c) => c,
            Err(_) => return Vec::new(),
        };
        let mut stmt =
            match conn.prepare("SELECT payload FROM policy_audit_log ORDER BY timestamp ASC") {
                Ok(s) => s,
                Err(_) => return Vec::new(),
            };
        let rows = stmt.query_map([], |r| r.get::<_, String>(0));
        let Ok(rows) = rows else { return Vec::new() };

        rows.filter_map(|r| r.ok())
            .filter_map(|p| serde_json::from_str::<AuditRecordEvent>(&p).ok())
            .filter(|r| match &filter.since {
                Some(t) => r.timestamp_monotonic.0 >= t.0,
                None => true,
            })
            .filter(|r| match &filter.until {
                Some(t) => r.timestamp_monotonic.0 < t.0,
                None => true,
            })
            .filter(|r| match &filter.decisions {
                Some(d) => d.contains(&r.decision),
                None => true,
            })
            .take(limit as usize)
            .collect()
    }

    fn verify_chain(&self) -> Result<(), AuditVerifyError> {
        let conn = self
            .conn
            .lock()
            .map_err(|e| AuditVerifyError::Io(format!("mutex poisoned: {e}")))?;

        // Walk the log in insertion order (rowid ASC is stable for an
        // INSERT-only table).
        let mut stmt = conn
            .prepare(
                "SELECT rowid, payload, prev_hash, record_hmac, event_hash \
                 FROM policy_audit_log ORDER BY rowid ASC",
            )
            .map_err(|e| AuditVerifyError::Io(e.to_string()))?;

        struct Row {
            rowid: i64,
            payload: String,
            prev_hash: Vec<u8>,
            record_hmac: Vec<u8>,
            event_hash: Option<Vec<u8>>,
        }
        let rows = stmt
            .query_map([], |r| {
                Ok(Row {
                    rowid: r.get(0)?,
                    payload: r.get(1)?,
                    prev_hash: r.get::<_, Option<Vec<u8>>>(2)?.unwrap_or_default(),
                    record_hmac: r.get::<_, Vec<u8>>(3)?,
                    event_hash: r.get::<_, Option<Vec<u8>>>(4)?,
                })
            })
            .map_err(|e| AuditVerifyError::Io(e.to_string()))?;

        let mut expected_prev: Vec<u8> = crate::audit_seal::GENESIS_PREV_HASH.to_vec();
        let mut last_computed: Option<Vec<u8>> = None;
        let mut sealed_rows: u64 = 0;

        for row_result in rows {
            let row = row_result.map_err(|e| AuditVerifyError::Io(e.to_string()))?;
            let row_id = row.rowid as u64;

            // Rows written before Wave 4.6 may lack event_hash; skip them.
            // A future 0004 migration can backfill.
            let Some(stored_event_hash) = row.event_hash else {
                continue;
            };

            // Chain linkage — stored prev_hash must match expected prev.
            if !crate::audit_seal::ct_eq(&row.prev_hash, &expected_prev) {
                return Err(AuditVerifyError::ChainBreak { row_id });
            }

            let parsed: AuditRecordEvent = serde_json::from_str(&row.payload)
                .map_err(|e| AuditVerifyError::Io(format!("payload parse @ row {row_id}: {e}")))?;
            let canonical = crate::audit_seal::canonical_bytes(&parsed)
                .map_err(|e| AuditVerifyError::Io(format!("canonical @ row {row_id}: {e}")))?;
            let recomputed_hash = crate::audit_seal::compute_event_hash(&row.prev_hash, &canonical);

            if !crate::audit_seal::ct_eq(&recomputed_hash, &stored_event_hash) {
                return Err(AuditVerifyError::ChainBreak { row_id });
            }

            let recomputed_hmac =
                crate::audit_seal::compute_event_hmac(&self.key, &recomputed_hash);
            if !crate::audit_seal::ct_eq(&recomputed_hmac, &row.record_hmac) {
                return Err(AuditVerifyError::HmacMismatch { row_id });
            }

            expected_prev = stored_event_hash.clone();
            last_computed = Some(stored_event_hash);
            sealed_rows += 1;
        }

        // If any sealed rows were seen, the chain tip must equal the
        // singleton's head_hash — catches chain-tip rollback.
        if sealed_rows > 0 {
            if let Some(last) = last_computed {
                let stored_head: Option<Vec<u8>> = conn
                    .query_row(
                        "SELECT head_hash FROM policy_audit_chain_head WHERE id = 1",
                        [],
                        |r| r.get::<_, Option<Vec<u8>>>(0),
                    )
                    .map_err(|e| AuditVerifyError::Io(e.to_string()))?;
                match stored_head {
                    Some(h) if crate::audit_seal::ct_eq(&h, &last) => {}
                    _ => return Err(AuditVerifyError::ChainBreak { row_id: u64::MAX }),
                }
            }
        }

        Ok(())
    }
}

fn read_chain_head(
    conn: &aether_storage::rusqlite::Connection,
) -> Result<Option<Vec<u8>>, aether_storage::rusqlite::Error> {
    conn.query_row(
        "SELECT head_hash FROM policy_audit_chain_head WHERE id = 1",
        [],
        |r| r.get::<_, Option<Vec<u8>>>(0),
    )
}

fn update_chain_head(
    conn: &aether_storage::rusqlite::Connection,
    audit_id: &AuditId,
    event_hash: &[u8; 32],
) -> Result<(), aether_storage::rusqlite::Error> {
    conn.execute(
        "UPDATE policy_audit_chain_head \
         SET head_audit_id = ?1, head_hash = ?2, \
             updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') \
         WHERE id = 1",
        aether_storage::rusqlite::params![audit_id.0, event_hash.to_vec()],
    )?;
    Ok(())
}

// ---------------------------------------------------------------------------
// DurableBackends convenience builder
// ---------------------------------------------------------------------------

/// Paired L5 durable backends sharing one SQLite connection.
///
/// Typical use from an app entry point (pseudocode):
///
/// ```ignore
/// let backends = DurableBackends::open("./aether.db")?;
/// let engine = DefaultPolicyEngine::new(
///     cfg,
///     backends.ledger.clone(),
///     backends.audit.clone(),
///     sink,
/// );
/// ```
///
/// The connection is wrapped in an `Arc<Mutex<_>>` so the ledger and the
/// audit store serialize writes on the same underlying driver — SQLite is a
/// single-writer system and this keeps the single-writer invariant honest.
pub struct DurableBackends {
    /// Trait-object handle suitable for `DefaultPolicyEngine::new`.
    pub ledger: Arc<dyn GrantLedger>,
    /// Trait-object handle suitable for `DefaultPolicyEngine::new`.
    pub audit: Arc<dyn AuditStore>,
    /// The shared connection, for callers that need to run adjacent queries
    /// (future waves: cost counters, chain-head reads).
    pub conn: Arc<Mutex<Connection>>,
}

impl DurableBackends {
    /// Open (or create) a SQLite DB at `path`, run migrations, load (or
    /// create) the HMAC signing key next to the DB, and return ledger +
    /// audit backends sharing the connection. The key is sourced from
    /// `AETHER_AUDIT_HMAC_KEY_HEX` when set, otherwise from
    /// `<path>.hmac.key` (auto-generated on first run).
    pub fn open(path: impl AsRef<Path>) -> Result<Self, OpenError> {
        let p = path.as_ref().to_path_buf();
        let outcome = aether_storage::open_with_migrations(&p)?;
        let key = crate::audit_seal::HmacKey::load_or_create(&p)
            .map_err(|e| OpenError::Io(format!("hmac key: {e}")))?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        Ok(Self {
            ledger: Arc::new(SqliteGrantLedger::new(conn.clone())),
            audit: Arc::new(SqliteAuditStore::new(conn.clone(), key)),
            conn,
        })
    }

    /// Open with an explicit HMAC key instead of the env/file lookup. Useful
    /// in tests and advanced deployments.
    pub fn open_with_key(
        path: impl AsRef<Path>,
        key: crate::audit_seal::HmacKey,
    ) -> Result<Self, OpenError> {
        let outcome = aether_storage::open_with_migrations(path)?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        Ok(Self {
            ledger: Arc::new(SqliteGrantLedger::new(conn.clone())),
            audit: Arc::new(SqliteAuditStore::new(conn.clone(), key)),
            conn,
        })
    }
}
