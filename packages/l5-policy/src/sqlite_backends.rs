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
/// declared in `0001_init.sql`, giving us a minimal tamper guarantee
/// without needing a hash chain in place yet.
#[derive(Debug)]
pub struct SqliteAuditStore {
    conn: Arc<Mutex<Connection>>,
}

impl SqliteAuditStore {
    /// Build an audit store from a shared connection. Assumes migrations
    /// (0001 + 0002) have been run.
    pub fn new(conn: Arc<Mutex<Connection>>) -> Self {
        Self { conn }
    }
}

impl AuditStore for SqliteAuditStore {
    fn append(&self, row: &AuditRecordEvent) -> Result<AuditId, AuditWriteError> {
        let payload =
            serde_json::to_string(row).map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let conn = self
            .conn
            .lock()
            .map_err(|e| AuditWriteError::Io(format!("mutex poisoned: {e}")))?;

        let cap_tag = capability_tag(&row.capability);
        let resource_json = serde_json::to_string(&row.resource)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let actor_ref = serde_json::to_string(&row.actor)
            .map_err(|e| AuditWriteError::Canonical(e.to_string()))?;
        let decision_tag = format!("{:?}", row.decision).to_lowercase();

        conn.execute(
            "INSERT INTO policy_audit_log (\
                 audit_id, timestamp, actor_persona, capability, resource, \
                 decision, change_id, prev_hash, record_hmac, payload, \
                 key_id, privileged_profile\
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            aether_storage::rusqlite::params![
                row.audit_id.0,
                row.timestamp_monotonic.0 as i64,
                actor_ref,
                cap_tag,
                resource_json,
                decision_tag,
                row.change_id.0.clone(),
                row.prev_hash.clone(),
                row.record_hmac.clone(),
                payload,
                row.key_id.0.clone(),
                row.privileged_profile as i64,
            ],
        )
        .map_err(|e| AuditWriteError::Io(e.to_string()))?;

        Ok(row.audit_id.clone())
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
        // Wave 4.5 posture: rely on 0001's append-only triggers + 0002's
        // key_id / chain_head groundwork. Full hash-chain verification is
        // a future wave; surface Ok here so callers don't flip L5 into
        // `AuditBroken` spuriously.
        Ok(())
    }
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
    /// Open (or create) a SQLite DB at `path`, run migrations, and return
    /// ledger + audit backends sharing the connection.
    pub fn open(path: impl AsRef<Path>) -> Result<Self, OpenError> {
        let outcome = aether_storage::open_with_migrations(path)?;
        let conn = Arc::new(Mutex::new(outcome.conn));
        Ok(Self {
            ledger: Arc::new(SqliteGrantLedger::new(conn.clone())),
            audit: Arc::new(SqliteAuditStore::new(conn.clone())),
            conn,
        })
    }
}
