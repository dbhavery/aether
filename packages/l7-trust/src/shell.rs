//! `ShellAdapter` trait + onboarding state + UI-facing data shapes.
//!
//! The renderer / component implementation lives in `apps/desktop/` (a later
//! wave). This crate only defines the Rust-side contract.

use serde::{Deserialize, Serialize};

use aether_l5_policy::{
    ApprovalTicket, Capability, Decision, DegradedMode, PersonaId, PolicyPostureSummary,
    ResourceScope, StaticReasonId,
};

use crate::error::L7Error;

/// Data needed to render an approval prompt in the trust UX.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalPrompt {
    /// Originating ticket from L5.
    pub ticket: ApprovalTicket,
    /// Capability requested.
    pub capability: Capability,
    /// Scope the grant would cover.
    pub resource: ResourceScope,
    /// Short reason id (for the copy table / translations).
    pub reason: StaticReasonId,
}

/// Data needed to render the posture banner (e.g. degraded mode).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PostureBanner {
    /// Current posture snapshot.
    pub posture: PolicyPostureSummary,
    /// If Some, degraded-mode banner should render.
    pub degraded: Option<DegradedMode>,
}

/// 8-screen onboarding wizard order (L7 interface pack §onboarding).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OnboardingScreen {
    /// Welcome.
    Welcome,
    /// Persona picker.
    PersonaPicker,
    /// Preset picker.
    PresetPicker,
    /// Capability matrix preview.
    CapabilityPreview,
    /// Privacy posture + local-first pledge.
    PrivacyPledge,
    /// BYOK / cost caps setup.
    ByokSetup,
    /// First-turn smoke test.
    FirstTurn,
    /// Completion.
    Done,
}

/// Onboarding progress state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OnboardingState {
    /// Currently rendered screen.
    pub current: OnboardingScreen,
    /// Chosen persona (set after PersonaPicker).
    pub chosen_persona: Option<PersonaId>,
}

/// Shell adapter — implemented by `apps/desktop/` (Tauri primary) and a
/// pywebview fallback (tactical, OSS-preview only per doctrine).
pub trait ShellAdapter: Send + Sync {
    /// Ask the user to resolve an approval ticket. Returns once a choice
    /// has been made. Implementations marshal the response through
    /// `policy.respond_approval`.
    fn present_approval(&self, prompt: &ApprovalPrompt) -> Result<(), L7Error>;

    /// Render (or update) the posture banner.
    fn render_posture_banner(&self, banner: &PostureBanner) -> Result<(), L7Error>;

    /// Forward a typed event from Rust → webview. Implementations are free to
    /// coalesce high-frequency events per X3 §3.2.
    fn emit_to_webview(&self, name: &str, payload: serde_json::Value) -> Result<(), L7Error>;

    /// Optional post-decision hook — used for optimistic-UI rollback when
    /// late `Deny` arrives (L7-T02).
    fn on_late_decision(&self, _decision: &Decision) -> Result<(), L7Error> {
        Ok(())
    }
}
