//! Posture and degraded-mode types.

use serde::{Deserialize, Serialize};

/// Privacy posture baseline set by the active persona.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PrivacyPosture {
    /// Strict — private-tagged context never crosses a remote route.
    Strict,
    /// Balanced — remote allowed unless private-tagged or elevated risk.
    Balanced,
    /// Open — remote allowed with standard consent flow.
    Open,
}

/// Summary of the active posture. Subscribers compare hashes to detect drift.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyPostureSummary {
    /// Preset id.
    pub preset: crate::common::PresetId,
    /// Preset version.
    pub preset_version: u32,
    /// Persona id.
    pub persona_id: crate::common::PersonaId,
    /// Persona version.
    pub persona_version: u32,
    /// Posture.
    pub privacy_posture: PrivacyPosture,
    /// Active degraded mode, if any.
    pub degraded: Option<DegradedMode>,
    /// Stable hash for drift detection (Wave 3 computes it; Wave 2 placeholder).
    pub hash: u64,
}

/// What caused the posture change.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PostureTrigger {
    /// Preset switched via `policy.set_preset`.
    PresetSwitch,
    /// Persona swapped.
    PersonaSwap,
    /// Degraded mode entered.
    DegradedEntry,
    /// Degraded mode exited.
    DegradedExit,
    /// Capability block-list updated.
    CapBlocklistUpdate,
}

/// Degraded operating modes. All prefer deny-all over silent-allow.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DegradedMode {
    /// Big-red-button / security trip — deny-all for a configured window.
    SafeMode,
    /// Audit chain verification failed — deny-all until user ack.
    AuditBroken,
    /// Grant ledger inconsistent — deny-all until recovery run.
    LedgerCorrupt,
    /// No persona loaded → fallback persona with minimal trust defaults.
    MinimumTrust,
}

/// Warn-level attached to early `cost_threshold_hit` emissions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WarnLevel {
    /// 50% of cap.
    Half,
    /// 80% of cap.
    Eighty,
    /// 95% of cap.
    NinetyFive,
}
