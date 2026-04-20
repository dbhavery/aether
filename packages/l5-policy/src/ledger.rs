//! In-memory `GrantLedger` implementation.
//!
//! Wave 3 slice. Thread-safe (`Mutex`), process-local, not persisted. Maps the
//! 8-trigger re-evaluation rule (Decision 4, 2026-04-18) onto concrete mutating
//! helpers (`expire_ttl`, `revoke_all`) consumed by `engine::DefaultPolicyEngine`.

use std::collections::HashMap;
use std::sync::Mutex;

use crate::capability::{Capability, ResourceScope};
use crate::common::{MonotonicTimestamp, PersonaId};
use crate::events::RevokeReason;
use crate::grants::{Grant, GrantFilter, GrantId, GrantLedger};

/// Thread-safe in-memory grant ledger.
#[derive(Debug, Default)]
pub struct InMemoryGrantLedger {
    inner: Mutex<LedgerInner>,
}

#[derive(Debug, Default)]
struct LedgerInner {
    grants: HashMap<GrantId, GrantRow>,
}

#[derive(Debug, Clone)]
struct GrantRow {
    grant: Grant,
    revoked: Option<RevokeReason>,
}

impl InMemoryGrantLedger {
    /// Create an empty ledger.
    pub fn new() -> Self {
        Self::default()
    }

    /// Count of currently-active (non-revoked, non-expired) grants.
    pub fn active_len(&self) -> usize {
        let s = self.inner.lock().unwrap();
        s.grants.values().filter(|r| r.revoked.is_none()).count()
    }

    /// Expire every TTL-bearing grant whose `expires_at <= now`. Returns the
    /// ids that flipped to revoked this call.
    pub fn expire_ttl(&self, now: MonotonicTimestamp) -> Vec<GrantId> {
        let mut s = self.inner.lock().unwrap();
        let mut expired = Vec::new();
        for (id, row) in s.grants.iter_mut() {
            if row.revoked.is_some() {
                continue;
            }
            if let Some(exp) = row.grant.expires_at {
                if exp.0 <= now.0 {
                    row.revoked = Some(RevokeReason::TtlExpired);
                    expired.push(id.clone());
                }
            }
        }
        expired
    }

    /// Revoke every active grant. Returns count revoked this call.
    pub fn revoke_all(&self, reason: RevokeReason) -> u32 {
        let mut s = self.inner.lock().unwrap();
        let mut n = 0u32;
        for row in s.grants.values_mut() {
            if row.revoked.is_none() {
                row.revoked = Some(reason.clone());
                n += 1;
            }
        }
        n
    }

    /// Revoke every active grant matching `persona`. Returns count revoked.
    pub fn revoke_persona(&self, persona: &PersonaId, reason: RevokeReason) -> u32 {
        let mut s = self.inner.lock().unwrap();
        let mut n = 0u32;
        for row in s.grants.values_mut() {
            if row.revoked.is_none() && row.grant.persona_id == *persona {
                row.revoked = Some(reason.clone());
                n += 1;
            }
        }
        n
    }
}

impl GrantLedger for InMemoryGrantLedger {
    fn snapshot(&self, filter: &GrantFilter) -> Vec<Grant> {
        let s = self.inner.lock().unwrap();
        s.grants
            .values()
            .filter(|r| !filter.active_only || r.revoked.is_none())
            .filter(|r| match &filter.persona_id {
                Some(p) => r.grant.persona_id == *p,
                None => true,
            })
            .filter(|r| match &filter.capability {
                Some(c) => r.grant.capability == *c,
                None => true,
            })
            .map(|r| r.grant.clone())
            .collect()
    }

    fn issue(&self, grant: Grant) -> Option<GrantId> {
        let mut s = self.inner.lock().unwrap();
        let id = grant.grant_id.clone();
        s.grants.insert(
            id.clone(),
            GrantRow {
                grant,
                revoked: None,
            },
        );
        Some(id)
    }

    fn revoke(&self, grant_id: &GrantId, reason: RevokeReason) {
        let mut s = self.inner.lock().unwrap();
        if let Some(row) = s.grants.get_mut(grant_id) {
            if row.revoked.is_none() {
                row.revoked = Some(reason);
            }
        }
    }

    fn covers(
        &self,
        capability: &Capability,
        resource: &ResourceScope,
        persona: &PersonaId,
    ) -> Option<GrantId> {
        let s = self.inner.lock().unwrap();
        for row in s.grants.values() {
            if row.revoked.is_some() {
                continue;
            }
            if row.grant.persona_id != *persona {
                continue;
            }
            if row.grant.capability != *capability {
                continue;
            }
            if !scope_covers(&row.grant.resource_pattern, resource) {
                continue;
            }
            return Some(row.grant.grant_id.clone());
        }
        None
    }
}

/// Pattern-coverage semantics. Wave 3 intentionally narrow:
/// - `ResourceScope::None` pattern covers any target (blanket grant).
/// - `Path` / `Url` patterns use prefix match.
/// - `Mailbox` / `Integration` / `CostScope` require exact equality.
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
