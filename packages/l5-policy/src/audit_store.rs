//! In-memory `AuditStore` implementation.
//!
//! Wave 3 slice. Append-only (`Vec::push`), not hash-chained, not HMAC-sealed.
//! Chain + HMAC integrity arrive in Wave 4 once `aether-storage` wires the
//! SQLite driver. Semantics preserved: `verify_chain` returns `Ok(())` because
//! append-only is trivially preserved by a `Vec::push`-only surface.

use std::sync::Mutex;

use crate::audit::{AuditFilter, AuditId, AuditRecordEvent};
use crate::decision::DecisionKind;
use crate::storage_hooks::{AuditStore, AuditVerifyError, AuditWriteError};

/// Thread-safe in-memory audit log.
#[derive(Debug, Default)]
pub struct InMemoryAuditStore {
    rows: Mutex<Vec<AuditRecordEvent>>,
}

impl InMemoryAuditStore {
    /// Empty log.
    pub fn new() -> Self {
        Self::default()
    }

    /// How many rows are currently stored.
    pub fn len(&self) -> usize {
        self.rows.lock().unwrap().len()
    }

    /// Is the log empty?
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Snapshot of every row written so far (clones internally).
    pub fn all(&self) -> Vec<AuditRecordEvent> {
        self.rows.lock().unwrap().clone()
    }

    /// Count rows of a specific decision kind.
    pub fn count_kind(&self, kind: DecisionKind) -> usize {
        self.rows
            .lock()
            .unwrap()
            .iter()
            .filter(|r| r.decision == kind)
            .count()
    }
}

impl AuditStore for InMemoryAuditStore {
    fn append(&self, row: &AuditRecordEvent) -> Result<AuditId, AuditWriteError> {
        let mut s = self.rows.lock().unwrap();
        s.push(row.clone());
        Ok(row.audit_id.clone())
    }

    fn query(&self, filter: &AuditFilter, limit: u32) -> Vec<AuditRecordEvent> {
        let s = self.rows.lock().unwrap();
        s.iter()
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
            .cloned()
            .collect()
    }

    fn verify_chain(&self) -> Result<(), AuditVerifyError> {
        // Wave 3: no hash chain yet. A Vec is trivially append-only at this
        // surface (no `UPDATE`/`DELETE` exposed). Wave 4 upgrades to real
        // chain verification once SQLite + triggers are wired.
        Ok(())
    }
}
