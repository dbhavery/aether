//! Wave L6.1 — minimal `PersonaProfile` input for the first deterministic
//! compilation slice.
//!
//! The Wave 4 stub declared a `PersonaPack` holding free-form YAML/JSON.
//! That's still the long-term shape. But for the first real compilation
//! pass, we want a typed, small surface: a handful of identity dials we
//! can round-trip through a compiler without inventing a schema. This
//! module adds that surface without touching the existing stub types.
//!
//! No LLM calls, no external files, no policy decisions — just simple,
//! inspectable rules. Policy choices still belong to L5.

use serde::{Deserialize, Serialize};

use crate::compiler::PersonaId;

/// Formality / warmth dial. Ordered from reserved → warm.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Tone {
    /// Reserved, precise, minimal small talk.
    Formal,
    /// Balanced default — professional but not stiff.
    Neutral,
    /// Warm, conversational, tolerant of small talk.
    Warm,
}

/// How much the persona tends to say. Ordered from short → long.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Verbosity {
    /// Tight one-line answers.
    Terse,
    /// Normal paragraph answers.
    Balanced,
    /// Richer, more explanatory answers.
    Verbose,
}

/// Risk stance. Affects routing preference and behavior intensities —
/// **not** policy decisions (those remain L5's monopoly).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Stance {
    /// Cautious — prefers local / cheaper tiers, leans on drafts.
    Cautious,
    /// Balanced default.
    Balanced,
    /// Bolder — willing to escalate to remote tiers for ambitious tasks.
    Bold,
}

/// Humor dial. Intentionally narrow; a real pack surface will want more.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Humor {
    /// Dry — rare witticisms, never jokey.
    Dry,
    /// Occasional — light humor when it fits.
    Occasional,
    /// Playful — enjoys banter, uses metaphors.
    Playful,
}

/// Minimal typed persona input for L6.1. Expands into the 7-layer
/// compiled artifacts via [`DefaultPersonaCompiler`].
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PersonaProfile {
    /// Persona id (stable across versions).
    pub persona_id: PersonaId,
    /// Monotonic version number.
    pub version: u32,
    /// Display name (e.g. `"Aurora"`).
    pub name: String,
    /// Short self-description, interpolated into the system prompt.
    pub description: String,
    /// Formality / warmth dial.
    pub tone: Tone,
    /// How verbose the persona is.
    pub verbosity: Verbosity,
    /// Cautious / balanced / bold risk stance.
    pub stance: Stance,
    /// Humor dial.
    pub humor: Humor,
}

impl PersonaProfile {
    /// Minimal valid profile — handy as a test / demo baseline.
    pub fn simple(id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            persona_id: PersonaId(id.into()),
            version: 1,
            name: name.into(),
            description: String::from(
                "An attentive local assistant that prefers clarity over flourish.",
            ),
            tone: Tone::Neutral,
            verbosity: Verbosity::Balanced,
            stance: Stance::Balanced,
            humor: Humor::Occasional,
        }
    }
}
