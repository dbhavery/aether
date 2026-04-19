//! `PersonaCompiler` trait + 6 compiled artifacts + hot-reload state machine.

use serde::{Deserialize, Serialize};

use aether_l5_policy::PersonaCompiledPolicyDefaults;

use crate::error::L6Error;

/// Persona id (mirrors `aether_l5_policy::PersonaId`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PersonaId(pub String);

/// Raw persona pack input (YAML-shaped at rest; typed here).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PersonaPack {
    /// Persona id.
    pub persona_id: PersonaId,
    /// Pack version.
    pub version: u32,
    /// Signature over the pack content (privileged overlays only).
    pub signature: Option<String>,
    /// Free-form YAML content serialized to JSON for the Wave 4 stub; real
    /// shape is per `17_persona_pack_schema.md`.
    pub body: serde_json::Value,
}

/// Artifact 1 — compiled prompts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledPrompts {
    /// System prompt.
    pub system: String,
    /// Reflex template prompts keyed by reflex class.
    pub reflex_templates: Vec<(String, String)>,
}

/// Artifact 2 — compiled routing rules.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledRoutingRules {
    /// Preferred tier for this persona.
    pub preferred_tier: String,
    /// Max escalation tier allowed.
    pub max_tier: String,
}

/// Artifact 3 — compiled behavior map (for L3).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledBehaviorMap {
    /// Behavior-class → intensity multipliers.
    pub intensities: Vec<(String, f32)>,
}

/// Artifact 4 — compiled memory hints (for L2 salience).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledMemoryHints {
    /// Domain-specific salience boosts.
    pub domain_salience: Vec<(String, f32)>,
}

/// Artifact 5 — compiled tool allow-list (cross-check against L5 capabilities).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledToolAllowList {
    /// Tool ids this persona may request.
    pub tools: Vec<String>,
}

/// Artifact 6 — compiled voice config (for media-engine).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledVoiceConfig {
    /// Voice preset id.
    pub voice_id: String,
    /// Speaking rate multiplier.
    pub rate: f32,
}

/// All six artifacts bundled — atomic unit delivered to downstream layers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledPersona {
    /// Persona metadata.
    pub persona_id: PersonaId,
    /// Persona version.
    pub version: u32,
    /// Prompts.
    pub prompts: CompiledPrompts,
    /// Routing rules.
    pub routing: CompiledRoutingRules,
    /// Behavior map.
    pub behavior: CompiledBehaviorMap,
    /// Memory hints.
    pub memory: CompiledMemoryHints,
    /// Tool allow-list.
    pub tools: CompiledToolAllowList,
    /// Voice config.
    pub voice: CompiledVoiceConfig,
    /// L5 policy defaults delivered on swap commit.
    pub policy_defaults: PersonaCompiledPolicyDefaults,
}

/// Hot-reload state machine.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SwapState {
    /// No swap in flight.
    Idle,
    /// Compiling the new pack.
    Compiling,
    /// Validation pending.
    Validating,
    /// Ready to commit atomically.
    ReadyToCommit,
    /// Committed; downstream consumers applying.
    Committing,
    /// Rolled back due to validation failure.
    RolledBack,
}

/// Persona compiler surface.
pub trait PersonaCompiler: Send + Sync {
    /// Compile a `PersonaPack` → `CompiledPersona`. Deterministic: same input
    /// yields byte-identical output (L6-T01).
    fn compile(&self, pack: PersonaPack) -> Result<CompiledPersona, L6Error>;

    /// Begin a hot-reload swap to a new pack.
    fn begin_swap(&self, pack: PersonaPack) -> Result<(), L6Error>;

    /// Current hot-reload state.
    fn swap_state(&self) -> SwapState;

    /// Commit or roll back a staged swap.
    fn commit_swap(&self) -> Result<CompiledPersona, L6Error>;
}
