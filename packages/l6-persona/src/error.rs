//! L6 error vocabulary.

use thiserror::Error;

/// Errors returnable by the persona compiler.
#[derive(Debug, Error)]
pub enum L6Error {
    /// Signature verification failed on a privileged overlay.
    #[error("signature verification failed")]
    InvalidSignature,
    /// Schema / shape error in the raw pack.
    #[error("schema: {0}")]
    Schema(String),
    /// Compile-time invariant violated (e.g. auto-approve on High/Critical).
    #[error("invariant: {0}")]
    InvariantViolation(&'static str),
    /// Swap commit attempted while in an incompatible state.
    #[error("swap state: {0}")]
    SwapState(&'static str),
    /// Internal.
    #[error("internal: {0}")]
    Internal(String),
}
