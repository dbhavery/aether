//! Decision, deny-reason, and draft-source types.
//!
//! Locked shapes:
//! - **Decision 1 (2026-04-18):** `NeedsUpgrade(CapabilityPath)` is a
//!   **top-level** variant — not a `DenyReason`.
//! - **Decision 2 (2026-04-18):** `Decision::DraftOnly { source: DraftSource }`
//!   where `DraftSource ∈ {System, UserChoice}`. There is no `AllowDraft`.
//!
//! Source: the locked architectural decisions in `ARCHITECTURE.md`.

use serde::{Deserialize, Serialize};

use crate::approval::ApprovalTicket;
use crate::audit::AuditId;
use crate::capability::{Capability, CapabilityPath};
use crate::common::PresetId;
use crate::grants::GrantId;

/// Top-level decision returned by `PolicyEngine::evaluate`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Decision {
    /// Permit the action. An audit row is always written before this variant
    /// is returned. A `grant_ref` is attached when a persistent grant was
    /// issued (as opposed to a once-only allow from an existing persistent
    /// grant).
    Allow {
        /// Grant id if this Allow was issued against a new or extended grant.
        grant_ref: Option<GrantId>,
        /// Matching audit row.
        audit_id: AuditId,
    },
    /// Prompt the user. The ticket must be resolved via `respond_approval`.
    Ask {
        /// Pending approval ticket.
        ticket: ApprovalTicket,
        /// Matching audit row.
        audit_id: AuditId,
    },
    /// Allow the action to produce a draft without committing side effects.
    /// `source` discriminates system-initiated from user-choice.
    DraftOnly {
        /// Audit row.
        audit_id: AuditId,
        /// Why this ended up as DraftOnly.
        source: DraftSource,
        /// Optional static reason copy-id (for L7 rendering).
        reason: Option<StaticReasonId>,
    },
    /// Refuse. `reason` discriminates policy vs audit vs revoked vs so on.
    Deny {
        /// Reason code.
        reason: DenyReason,
        /// Audit row.
        audit_id: AuditId,
    },
    /// Denied but upgradable — the caller's current preset cannot accommodate
    /// the request, but a higher preset would. L7 renders an upgrade card.
    NeedsUpgrade {
        /// Canonical dot-path of the capability that would be unlocked.
        capability_path: CapabilityPath,
        /// Audit row.
        audit_id: AuditId,
        /// Suggested preset that would accommodate this capability.
        suggested_preset: Option<PresetId>,
    },
}

/// Why a `Decision::DraftOnly` was issued.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DraftSource {
    /// Policy decided DraftOnly without user input (posture / capability default).
    System,
    /// User explicitly picked "Draft only" in the approval dialog
    /// (`UserChoice::DeferToDraft`).
    UserChoice,
}

/// Flat decision-kind discriminator used in audit rows and pattern matches
/// where the payload is not needed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DecisionKind {
    /// `Decision::Allow`.
    Allow,
    /// `Decision::Ask`.
    Ask,
    /// `Decision::DraftOnly { source: System }`.
    DraftOnlySystem,
    /// `Decision::DraftOnly { source: UserChoice }`.
    DraftOnlyUserChoice,
    /// `Decision::Deny`.
    Deny,
    /// `Decision::NeedsUpgrade`.
    NeedsUpgrade,
}

impl Decision {
    /// Extract the audit id associated with any decision.
    pub fn audit_id(&self) -> &AuditId {
        match self {
            Decision::Allow { audit_id, .. }
            | Decision::Ask { audit_id, .. }
            | Decision::DraftOnly { audit_id, .. }
            | Decision::Deny { audit_id, .. }
            | Decision::NeedsUpgrade { audit_id, .. } => audit_id,
        }
    }

    /// Flat discriminator form.
    pub fn kind(&self) -> DecisionKind {
        match self {
            Decision::Allow { .. } => DecisionKind::Allow,
            Decision::Ask { .. } => DecisionKind::Ask,
            Decision::DraftOnly {
                source: DraftSource::System,
                ..
            } => DecisionKind::DraftOnlySystem,
            Decision::DraftOnly {
                source: DraftSource::UserChoice,
                ..
            } => DecisionKind::DraftOnlyUserChoice,
            Decision::Deny { .. } => DecisionKind::Deny,
            Decision::NeedsUpgrade { .. } => DecisionKind::NeedsUpgrade,
        }
    }
}

/// Reasons a `Decision::Deny` was returned.
///
/// Note: `NeedsUpgrade` is **not** here — it is a top-level `Decision`
/// variant per Decision 1 (2026-04-18).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DenyReason {
    /// Pre-evaluator hardcoded block (e.g. `shell.rm -rf /`).
    HardcodedBlock(HardcodedBlockId),
    /// Capability not enabled in the active preset.
    FeatureDisabled,
    /// Action is out of scope for the capability.
    ActionOutOfScope,
    /// Resource is out of scope for the grant / capability.
    ResourceOutOfScope,
    /// Mode layer denied (`ApprovalMode::Deny`).
    ModeDeny,
    /// Grant expired (TTL or session end).
    GrantExpired,
    /// Grant revoked (user / persona swap / emergency).
    GrantRevoked,
    /// Provenance taint blocked the action.
    ProvenanceTaint(TaintKind),
    /// Privacy posture gate blocked the action
    /// (private context + remote route, no waiver).
    PrivacyPostureViolation,
    /// BYOK cost cap hit for the provider.
    CostCapHit(crate::byok::ProviderId),
    /// Tier downgrade stripped the grant.
    TierDowngradeStripped,
    /// Grant ledger detected corrupt state — deny-all.
    LedgerCorrupt,
    /// Audit write failed — deny-all invariant.
    AuditWriteFailed,
}

/// Static id of a hardcoded pre-evaluator block. Owned string for
/// serde compatibility; the evaluator interns these from a static table.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct HardcodedBlockId(pub String);

/// Source of provenance taint (for `DenyReason::ProvenanceTaint`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TaintKind {
    /// Untrusted input (default when tags missing).
    UntrustedInput,
    /// Private-tagged context crossing a remote route without waiver.
    PrivateRemote,
    /// Scraped content at High/Critical risk.
    ScrapedHighRisk,
    /// Extracted preference at low confidence used for a mutation.
    LowConfidencePreference,
}

/// Static copy-id for a human-readable reason rendered by L7. Owned for
/// serde compatibility (string table is an in-memory concern).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct StaticReasonId(pub String);

/// The 8 re-evaluation triggers locked by Decision 4 (2026-04-18).
///
/// A `GrantIssued` authorizes `(capability, resource_pattern, persona, duration)`.
/// L4 **skips** re-evaluation for subsequent steps whose `(capability, resource,
/// persona)` fall inside the grant and whose execution does not cross any of
/// these triggers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReEvalTrigger {
    /// Capability differs from the grant's capability (incl. sub-capability).
    CapabilityDiffers,
    /// Resource is outside the grant's declared `resource_pattern`.
    ResourceOutsidePattern,
    /// Persona has changed (`persona_swap_commit` since grant issued).
    PersonaSwapped,
    /// Step triggers a remote-tier escalation not covered at grant time.
    RemoteEscalationUncovered,
    /// Provenance class elevated (e.g. private-tagged context entered prompt).
    ProvenanceElevated,
    /// `cost_threshold_hit` fired between grant issuance and this step.
    CostThresholdHit,
    /// `GrantRevoked` or `EmergencyRevokeAll` landed since grant issued.
    GrantOrEmergencyRevoked,
    /// Grant's TTL has expired.
    TtlExpired,
}

impl ReEvalTrigger {
    /// Every trigger — handy for exhaustive test matrices.
    pub const ALL: [ReEvalTrigger; 8] = [
        Self::CapabilityDiffers,
        Self::ResourceOutsidePattern,
        Self::PersonaSwapped,
        Self::RemoteEscalationUncovered,
        Self::ProvenanceElevated,
        Self::CostThresholdHit,
        Self::GrantOrEmergencyRevoked,
        Self::TtlExpired,
    ];
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::audit::AuditId;

    #[test]
    fn decision_kind_distinguishes_draft_sources() {
        let a = Decision::DraftOnly {
            audit_id: AuditId(String::from("a")),
            source: DraftSource::System,
            reason: None,
        };
        let b = Decision::DraftOnly {
            audit_id: AuditId(String::from("b")),
            source: DraftSource::UserChoice,
            reason: None,
        };
        assert_eq!(a.kind(), DecisionKind::DraftOnlySystem);
        assert_eq!(b.kind(), DecisionKind::DraftOnlyUserChoice);
    }

    #[test]
    fn re_eval_triggers_cover_eight() {
        assert_eq!(ReEvalTrigger::ALL.len(), 8);
    }
}
