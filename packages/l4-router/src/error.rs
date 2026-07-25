//! L4 error vocabulary.

use thiserror::Error;

/// Errors returnable by L4 routing surfaces.
#[derive(Debug, Error)]
pub enum L4Error {
    /// Provider not registered.
    #[error("unknown provider: {0}")]
    UnknownProvider(String),
    /// Provider returned an error.
    #[error("provider: {0}")]
    Provider(String),
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
