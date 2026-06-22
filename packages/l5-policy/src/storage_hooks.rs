//! Storage-integration hooks.
//!
//! L5 owns three SQLite tables in the shared `aether.db` (see
//! see `ARCHITECTURE.md` §3):
//!
//! - `policy_grants` — active + historical grant rows.
//! - `audit_log` — append-only, hash-chained, HMAC-integrity rows.
//! - `cost_counters` — BYOK rolling counters.
//!
//! Persistence implementations live in `aether-storage` (Wave 3). This module
//! defines the Rust-facing traits the evaluator composes, which lets the
//! engine be tested against in-memory impls without pulling a SQLite driver.

use crate::audit::{AuditFilter, AuditId, AuditRecordEvent};
use crate::byok::{CostCap, CostEvent, CostThreshold, CostWindow, ProviderId};
use crate::common::{Cents, MonotonicTimestamp};
use crate::grants::{Grant, GrantFilter, GrantId};

/// Grant persistence surface.
pub trait GrantStore: Send + Sync {
    /// Insert a new grant row.
    fn insert(&self, grant: &Grant);
    /// Mark a grant revoked. Idempotent.
    fn mark_revoked(&self, id: &GrantId, reason: crate::events::RevokeReason);
    /// Query grants.
    fn query(&self, filter: &GrantFilter) -> Vec<Grant>;
    /// Count active grants. Used by emergency-revoke acceptance test.
    fn active_count(&self) -> u64;
}

/// Audit log persistence surface.
///
/// Implementations must:
///   - Reject `UPDATE`/`DELETE` via SQLite triggers.
///   - Chain every row by `prev_hash = SHA256(prev_row_canonical)`.
///   - Seal every row with HMAC using a per-install key from the OS keyring.
pub trait AuditStore: Send + Sync {
    /// Append a row. Returns its id on success.
    /// Failure MUST cause L5 to deny-all until `verify_chain` succeeds again.
    fn append(&self, row: &AuditRecordEvent) -> Result<AuditId, AuditWriteError>;
    /// Page through rows under a filter.
    fn query(&self, filter: &AuditFilter, limit: u32) -> Vec<AuditRecordEvent>;
    /// Verify the entire chain — used at boot and on demand.
    fn verify_chain(&self) -> Result<(), AuditVerifyError>;
}

/// Audit-log write failure.
#[derive(Debug, thiserror::Error)]
pub enum AuditWriteError {
    /// Storage I/O error.
    #[error("storage io: {0}")]
    Io(String),
    /// HMAC key missing (OS keyring unavailable).
    #[error("missing signing key")]
    MissingKey,
    /// Canonical serialization failed.
    #[error("canonical serialization: {0}")]
    Canonical(String),
}

/// Chain-verification failure.
#[derive(Debug, thiserror::Error)]
pub enum AuditVerifyError {
    /// Hash of row N did not match `prev_hash` of row N+1.
    #[error("chain break at row {row_id}")]
    ChainBreak {
        /// Offending row id.
        row_id: u64,
    },
    /// HMAC mismatch for a row.
    #[error("hmac mismatch at row {row_id}")]
    HmacMismatch {
        /// Offending row id.
        row_id: u64,
    },
    /// Storage error during verification.
    #[error("storage io: {0}")]
    Io(String),
}

/// Cost-counter surface. Increments are fire-and-forget from L4's `CostEvent`.
pub trait CostCounterStore: Send + Sync {
    /// Increment the counter for `(provider, window)` by `event.dollars`.
    fn apply(&self, event: &CostEvent);
    /// Read the current value.
    fn read(&self, provider: &ProviderId, window: &CostWindow) -> Cents;
    /// Install or update a cap for `(provider, window)`.
    fn set_cap(&self, provider: &ProviderId, window: &CostWindow, cap: CostCap);
    /// Reset the counter for `(provider, window)` to zero.
    fn reset(&self, provider: &ProviderId, window: &CostWindow);
    /// Check whether a threshold has been crossed since the last notify.
    fn peek_threshold(
        &self,
        provider: &ProviderId,
        window: &CostWindow,
    ) -> Option<(CostThreshold, MonotonicTimestamp)>;
}
