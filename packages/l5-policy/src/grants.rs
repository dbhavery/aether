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
/// in-memory + SQLite implementations. See `planning/plans/implementation_prep/sqlite_schema_pack.md` §3 (grant_ledger table).
pub trait GrantLedger: Send + Sync {
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
    /// Isabelle privileged-profile flag (source §14.10 — still pending ratification).
    pub privileged_profile: bool,
    /// Persona's recommended preset, if any.
    pub recommended_preset: Option<PresetId>,
    // TODO(wave-3): `strict_provenance_tags: BitSet<ProvenanceTagKind>`.
}
