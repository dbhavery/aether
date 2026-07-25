//! L3 error vocabulary.

use thiserror::Error;

/// Errors returnable by L3.
#[derive(Debug, Error)]
pub enum L3Error {
    /// Rendering surface returned an error.
    #[error("rendering surface: {0}")]
    Rendering(String),
    /// Tier misconfigured (e.g. Pro tier requested but GPU unavailable).
    #[error("tier unavailable: {0:?}")]
    TierUnavailable(crate::engine::PresenceTier),
    /// Internal scheduler error.
    #[error("internal: {0}")]
    Internal(String),
}
