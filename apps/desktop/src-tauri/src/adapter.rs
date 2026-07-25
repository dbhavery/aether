//! L4→L1 adapter and reflex stub — identical in shape to
//! `apps/l1-cli/src/adapter.rs`. Kept per-app so the shell stays
//! self-contained and the CLI adapter stays focused on its stdin loop.

use aether_l1_interaction::{L1Error, RouteOutcome, TurnId, TurnRouter};
use aether_l4_router::{L4Error, ModelRouter, RouterTier, ToolCall, ToolError, ToolResult};
use aether_l5_policy::Decision;

#[derive(Default)]
pub struct ReflexModelRouter;

impl ReflexModelRouter {
    pub fn new() -> Self {
        Self
    }
}

impl ModelRouter for ReflexModelRouter {
    fn route(&self, tier: RouterTier, prompt: &str) -> Result<String, L4Error> {
        let label = tier_label(tier);
        Ok(format!(
            "[{label} stub] I heard: \"{prompt}\" — I'm running with no model loaded, so this is a deterministic echo. Enable the Ollama provider to get real responses."
        ))
    }

    fn execute_tool(&self, _call: &ToolCall) -> Result<ToolResult, ToolError> {
        Err(ToolError::Internal(String::from(
            "ReflexModelRouter does not execute tool calls in the v0 shell",
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

pub struct ModelRouterAdapter<R: ModelRouter> {
    router: R,
    provider_label: String,
    tier: RouterTier,
}

impl<R: ModelRouter> ModelRouterAdapter<R> {
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
            latency_ms: None,
            tokens: None,
        })
    }
}
