//! L4 error vocabulary.

use thiserror::Error;

/// Errors returnable by L4 routing surfaces.
#[derive(Debug, Error)]
pub enum L4Error {
    /// Provider not registered.
    #[error("unknown provider: {0}")]
    UnknownProvider(String),
    /// Generic provider error. Kept for back-compat with older call-sites
    /// and for errors that don't fit any of the typed variants below. New
    /// provider code should prefer the typed variants so the UI can offer
    /// useful language.
    #[error("provider: {0}")]
    Provider(String),
    /// Provider did not respond within its configured timeout.
    #[error("provider timeout: {detail}")]
    ProviderTimeout {
        /// Best-effort transport-level detail.
        detail: String,
    },
    /// Provider daemon is not reachable — connection refused, no route,
    /// etc. Actionable: the user likely needs to start the daemon.
    #[error("provider not running: {detail}")]
    ProviderNotRunning {
        /// Best-effort transport-level detail.
        detail: String,
    },
    /// Provider reports the requested model id is unknown.
    #[error("provider model not found: {model} ({detail})")]
    ProviderModelNotFound {
        /// Model id the caller asked for.
        model: String,
        /// Raw provider message where available.
        detail: String,
    },
    /// Provider returned a response we couldn't parse or trust.
    #[error("provider bad response: {detail}")]
    ProviderBadResponse {
        /// Parse-level detail.
        detail: String,
    },
    /// Transport- or status-level failure we couldn't classify.
    #[error("provider unknown error: {detail}")]
    ProviderUnknown {
        /// Best-effort transport-level detail.
        detail: String,
    },
    /// Policy gate denied.
    #[error("policy denied")]
    PolicyDenied,
    /// Decision-4 re-eval trigger fired; caller must re-issue ActionRequest.
    #[error("re-eval required: {0}")]
    ReEvalRequired(&'static str),
    /// Cost cap hit — providerid denied until re-arm.
    #[error("cost cap hit for {0}")]
    CostCapHit(String),
    /// Internal.
    #[error("internal: {0}")]
    Internal(String),
}
