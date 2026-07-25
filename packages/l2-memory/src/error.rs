//! L2 error vocabulary.

use thiserror::Error;

/// Errors returnable by L2.
#[derive(Debug, Error)]
pub enum L2Error {
    /// Memory id not found.
    #[error("memory not found")]
    NotFound,
    /// Storage backend failure.
    #[error("storage: {0}")]
    Storage(String),
    /// Embedding store failure.
    #[error("embedding: {0}")]
    Embedding(String),
    /// Privacy-class violation (e.g. Sensitive data requested without waiver).
    #[error("privacy violation: {0}")]
    PrivacyViolation(String),
    /// Catch-all.
    #[error("internal: {0}")]
    Internal(String),
}
