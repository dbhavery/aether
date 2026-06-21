//! Grant ledger types + `PersonaCompiledPolicyDefaults` (L6 → L5 inbound).

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::capability::{Capability, ResourceScope};
use crate::common::{Duration, MonotonicTimestamp, PersonaId, PresetId, TaskId};
use crate::posture::PrivacyPosture;

/// Stable id for a `Grant`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct GrantId(pub String);

/// How a capability is approved per the evaluator / persona / preset.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ApprovalMode {
    /// Auto — no prompt.
    Auto,
    /// Task-scoped — ask once, apply for remaining steps in the task.
    TaskScoped,
    /// Ask every time.
    Ask,
    /// Draft-only; side effects inhibited.
    DraftOnly,
    /// Never allow.
    Deny,
}

/// TTL / scope of a grant.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GrantDuration {
    /// One-shot grant; consumed on use.
    Once,
    /// Valid for one task.
    TaskScoped(TaskId),
    /// Valid for the rest of the session.
    Session,
    /// Persistent; optional monotonic TTL.
    Persistent {
        /// Optional TTL from issuance.
        ttl: Option<Duration>,
    },
}

/// A live (or historical) grant row.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Grant {
    /// Id.
    pub grant_id: GrantId,
    /// Capability granted.
    pub capability: Capability,
    /// Scope pattern — grants cover this pattern for the 8-trigger re-eval rule.
    pub resource_pattern: ResourceScope,
    /// Persona that holds the grant.
    pub persona_id: PersonaId,
    /// Approval mode at issuance.
    pub approval_mode: ApprovalMode,
    /// Duration at issuance.
    pub duration: GrantDuration,
    /// Issuance timestamp (monotonic).
    pub issued_at: MonotonicTimestamp,
    /// Computed expiry (if time-bounded).
    pub expires_at: Option<MonotonicTimestamp>,
    /// Preset version under which this grant was issued.
    pub preset_version_issued_under: u32,
}

/// Query filter for `snapshot_grants` / `list_grants`.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GrantFilter {
    /// Only active (not expired / revoked).
    pub active_only: bool,
    /// Narrow to a single persona.
    pub persona_id: Option<PersonaId>,
    /// Narrow to a capability family prefix.
    pub capability: Option<Capability>,
}

/// In-memory ledger surface. Persistence lives in `aether-storage`.
///
/// Wave 2 declares this trait but implements nothing. Wave 3 lands the
/// in-memory implementation. Wave 4.5 extends the trait with bulk
/// mutation helpers — given as default impls so any ledger implementing
/// the core four methods automatically inherits them, and specialized
/// backends may override for efficiency.
///
/// See `planning/plans/implementation_prep/sqlite_schema_pack.md` §3
/// (grant_ledger table).
pub trait GrantLedger: Send + Sync {
    // --- core four (required) ---------------------------------------------

    /// Snapshot matching grants.
    fn snapshot(&self, filter: &GrantFilter) -> Vec<Grant>;
    /// Attempt to issue a grant — returns `None` if the ledger is in a
    /// degraded mode that forbids new grants.
    fn issue(&self, grant: Grant) -> Option<GrantId>;
    /// Revoke by id. Idempotent no-op if already revoked / expired.
    fn revoke(&self, grant_id: &GrantId, reason: crate::events::RevokeReason);
    /// Check whether `(capability, resource, persona)` falls inside any
    /// active grant for the 8-trigger re-eval rule. Semantics finalized in Wave 3.
    fn covers(
        &self,
        capability: &Capability,
        resource: &ResourceScope,
        persona: &PersonaId,
    ) -> Option<GrantId>;

    // --- bulk mutation helpers (default impls via core four) --------------

    /// Count of currently-active (non-revoked, non-expired) grants.
    fn active_count(&self) -> u64 {
        self.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        })
        .len() as u64
    }

    /// Expire every TTL-bearing active grant whose `expires_at <= now`.
    /// Returns the ids that flipped to revoked this call.
    ///
    /// The default implementation snapshots all active grants, compares each
    /// one's `expires_at` to `now`, and revokes those that have elapsed with
    /// `RevokeReason::TtlExpired`. Specialized backends may override to push
    /// the comparison into the storage layer.
    fn expire_ttl(&self, now: crate::common::MonotonicTimestamp) -> Vec<GrantId> {
        let active = self.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        });
        let mut expired = Vec::new();
        for g in active {
            if let Some(exp) = g.expires_at {
                if exp.0 <= now.0 {
                    self.revoke(&g.grant_id, crate::events::RevokeReason::TtlExpired);
                    expired.push(g.grant_id);
                }
            }
        }
        expired
    }

    /// Revoke every currently-active grant with `reason`. Returns count revoked.
    fn revoke_all(&self, reason: crate::events::RevokeReason) -> u32 {
        let active = self.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        });
        let n = active.len() as u32;
        for g in active {
            self.revoke(&g.grant_id, reason.clone());
        }
        n
    }

    /// Revoke every active grant matching `persona` with `reason`. Returns count revoked.
    fn revoke_persona(&self, persona: &PersonaId, reason: crate::events::RevokeReason) -> u32 {
        let active = self.snapshot(&GrantFilter {
            active_only: true,
            persona_id: Some(persona.clone()),
            ..Default::default()
        });
        let n = active.len() as u32;
        for g in active {
            self.revoke(&g.grant_id, reason.clone());
        }
        n
    }
}

/// L6 → L5 overlay delivered on `persona_swap_commit`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonaCompiledPolicyDefaults {
    /// Persona bound to this overlay.
    pub persona_id: PersonaId,
    /// Persona version.
    pub persona_version: u32,
    /// Privacy posture baseline.
    pub privacy_posture: PrivacyPosture,
    /// Per-capability default approval mode (layer 3 of precedence).
    pub per_capability_defaults: HashMap<Capability, ApprovalMode>,
    /// Privileged-profile flag (source §14.10 — still pending ratification).
    pub privileged_profile: bool,
    /// Persona's recommended preset, if any.
    pub recommended_preset: Option<PresetId>,
    // TODO(wave-3): `strict_provenance_tags: BitSet<ProvenanceTagKind>`.
}
