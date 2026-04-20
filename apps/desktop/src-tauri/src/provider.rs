//! Provider mode enum + tier translation. Kept here so state.rs can
//! stay focused on wiring.

use aether_l4_router::RouterTier;
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
#[allow(dead_code)] // `Ollama` is constructed only under #[cfg(feature = "ollama-provider")]
pub enum ProviderMode {
    ReflexStub,
    Ollama,
}

impl ProviderMode {
    pub fn as_str(self) -> &'static str {
        match self {
            ProviderMode::ReflexStub => "reflex_stub",
            ProviderMode::Ollama => "ollama",
        }
    }
}

pub fn tier_from_rules(preferred: &str) -> RouterTier {
    match preferred {
        "reflex" => RouterTier::Reflex,
        "local-tiny" => RouterTier::LocalTiny,
        "local-small" => RouterTier::LocalSmall,
        "local-full" => RouterTier::LocalFull,
        "remote-standard" => RouterTier::RemoteStandard,
        "remote-premium" => RouterTier::RemotePremium,
        "remote-deep-research" => RouterTier::RemoteDeepResearch,
        _ => RouterTier::Reflex,
    }
}
