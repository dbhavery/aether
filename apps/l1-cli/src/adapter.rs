//! L4 → L1 adapter.
//!
//! L1 defines `TurnRouter` (its local routing surface). L4 defines
//! `ModelRouter` (its own 7-tier routing surface). Neither depends on the
//! other — sibling-engine rule. This adapter crate depends on both and
//! stitches them together.
//!
//! The adapter picks a tier, asks L4's router to produce a completion, and
//! maps the returned `String` back into L1's `RouteOutcome`. A minimal
//! `ReflexModelRouter` is included so the demo runs with zero external
//! dependencies (no network, no local model). Plugging a real
//! `ModelRouter` impl here is the next step after this demo.

use aether_l1_interaction::{L1Error, RouteOutcome, TurnId, TurnRouter};
use aether_l4_router::{L4Error, ModelRouter, RouterTier, ToolCall, ToolError, ToolResult};
use aether_l5_policy::Decision;

/// Stub `ModelRouter` that never leaves the process — it echoes the prompt
/// under a fixed reflex tier. Keeps the demo runnable without configuring
/// any provider; a real adapter swaps this out for Anthropic / llama.cpp /
/// Ollama / etc.
#[derive(Default)]
pub struct ReflexModelRouter;

impl ReflexModelRouter {
    /// Build a reflex-tier router. Provider label is attached by the
    /// `ModelRouterAdapter` wrapper, not stored here.
    pub fn new() -> Self {
        Self
    }
}

impl ModelRouter for ReflexModelRouter {
    fn route(&self, tier: RouterTier, prompt: &str) -> Result<String, L4Error> {
        // Reflex-tier: no model call, just a templated reply. Higher tiers
        // would plug a provider adapter in; this demo stays honest about
        // doing no real inference.
        let tier_label = tier_label(tier);
        Ok(format!("[{tier_label}] heard you: {prompt}"))
    }

    fn execute_tool(&self, _call: &ToolCall) -> Result<ToolResult, ToolError> {
        // Demo never dispatches tool calls through L4 — the stub path is
        // prompt-only. Surfacing a typed error is cheaper than panicking.
        Err(ToolError::Internal(String::from(
            "ReflexModelRouter does not execute tool calls in the community demo",
        )))
    }

    fn on_policy_decision(&self, _decision: &Decision) -> Result<(), L4Error> {
        Ok(())
    }
}

fn tier_label(t: RouterTier) -> &'static str {
    match t {
        RouterTier::Reflex => "reflex",
        RouterTier::LocalTiny => "local-tiny",
        RouterTier::LocalSmall => "local-small",
        RouterTier::LocalFull => "local-full",
        RouterTier::RemoteStandard => "remote-standard",
        RouterTier::RemotePremium => "remote-premium",
        RouterTier::RemoteDeepResearch => "remote-deep-research",
    }
}

/// Adapter that makes any `aether_l4_router::ModelRouter` satisfy L1's
/// `TurnRouter` contract. Tier selection lives here; a richer adapter could
/// pick based on decision metadata, persona, or utterance length.
pub struct ModelRouterAdapter<R: ModelRouter> {
    router: R,
    provider_label: String,
    tier: RouterTier,
}

impl<R: ModelRouter> ModelRouterAdapter<R> {
    /// Wrap a concrete `ModelRouter` at a fixed tier.
    pub fn new(router: R, provider_label: impl Into<String>, tier: RouterTier) -> Self {
        Self {
            router,
            provider_label: provider_label.into(),
            tier,
        }
    }
}

impl<R: ModelRouter> TurnRouter for ModelRouterAdapter<R> {
    fn dispatch(
        &self,
        _turn_id: &TurnId,
        prompt: &str,
        _decision: &Decision,
    ) -> Result<RouteOutcome, L1Error> {
        let response = self
            .router
            .route(self.tier, prompt)
            .map_err(|e| L1Error::Router(format!("{e}")))?;
        Ok(RouteOutcome {
            tier: tier_label(self.tier).to_string(),
            provider: self.provider_label.clone(),
            response_text: response,
        })
    }
}
