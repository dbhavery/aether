//! L7 error vocabulary.

use thiserror::Error;

/// Errors returnable by the L7 backend surfaces.
#[derive(Debug, Error)]
pub enum L7Error {
    /// Webview channel unavailable.
    #[error("webview channel closed")]
    ChannelClosed,
    /// Approval prompt deadline exceeded without response.
    #[error("approval timeout after {ms}ms")]
    ApprovalTimeout {
        /// Elapsed ms.
        ms: u64,
    },
    /// Onboarding invariant violated (wrong screen for event).
    #[error("onboarding invariant: {0}")]
    OnboardingInvariant(&'static str),
    /// Secret leaked into a logged payload — hard fail.
    #[error("secret leak detected in payload")]
    SecretLeak,
    /// Internal.
    #[error("internal: {0}")]
    Internal(String),
}
