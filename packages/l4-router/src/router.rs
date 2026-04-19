//! `ModelRouter` + `ProviderAdapter` traits, 7-tier abstraction, tool-call
//! vocabulary.

use serde::{Deserialize, Serialize};

use aether_l5_policy::{Capability, Decision, ResourceScope};

use crate::error::L4Error;

/// Opaque provider id (`"anthropic"`, `"openai"`, `"gemma-local"`, …).
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ProviderId(pub String);

/// 7-tier routing abstraction (see L4 §4). Ordered by cost and deliberation
/// depth.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RouterTier {
    /// Reflex — instant template reply, no LLM.
    Reflex,
    /// Local tiny — smallest Gemma variant.
    LocalTiny,
    /// Local small — balanced Gemma variant.
    LocalSmall,
    /// Local full — full-tier Gemma variant.
    LocalFull,
    /// Remote standard — frontier provider, default tier.
    RemoteStandard,
    /// Remote premium — frontier provider, highest-capability tier.
    RemotePremium,
    /// Remote deep-research — long-horizon / tool-heavy frontier.
    RemoteDeepResearch,
}

/// A single tool-call descriptor produced by the router.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Tool id (e.g. `"fs.read"`).
    pub tool: String,
    /// Capability this call needs L5 to allow.
    pub capability: Capability,
    /// Resource scope (e.g. the target path).
    pub resource: ResourceScope,
    /// JSON-encoded arguments.
    pub args: serde_json::Value,
}

/// Successful tool-call result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    /// Tool id that produced the result.
    pub tool: String,
    /// JSON-encoded output.
    pub output: serde_json::Value,
}

/// Tool-call failure.
#[derive(Debug, thiserror::Error)]
pub enum ToolError {
    /// Policy denied the call.
    #[error("policy denied: {0:?}")]
    PolicyDenied(Decision),
    /// Provider reported a failure.
    #[error("provider: {0}")]
    Provider(String),
    /// Time budget exceeded.
    #[error("timeout after {ms}ms")]
    Timeout {
        /// Elapsed ms.
        ms: u64,
    },
    /// Catch-all.
    #[error("internal: {0}")]
    Internal(String),
}

/// Provider adapter. Concrete impls wrap Anthropic SDK, OpenAI SDK,
/// llama.cpp / Ollama, etc.
pub trait ProviderAdapter: Send + Sync {
    /// Provider id.
    fn id(&self) -> ProviderId;
    /// Is this provider currently reachable?
    fn healthcheck(&self) -> Result<(), L4Error>;
    /// Dispatch a completion request; blocking for Wave 4 contract clarity.
    fn complete(
        &self,
        prompt: &str,
        tier: RouterTier,
    ) -> Result<String, L4Error>;
}

/// Router surface consumed by L1. Every tool-call and remote-model request
/// routes through `PolicyEngine::evaluate` before the provider adapter fires.
pub trait ModelRouter: Send + Sync {
    /// Dispatch a prompt at a tier; policy is enforced internally.
    fn route(&self, tier: RouterTier, prompt: &str) -> Result<String, L4Error>;
    /// Execute a tool call after L5 has returned Allow.
    fn execute_tool(&self, call: &ToolCall) -> Result<ToolResult, ToolError>;
    /// Called by L1 when a policy decision lands asynchronously (approval
    /// flow completed, emergency revoke).
    fn on_policy_decision(&self, decision: &Decision) -> Result<(), L4Error>;
}
