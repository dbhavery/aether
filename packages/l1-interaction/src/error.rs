//! L1 error vocabulary.

use thiserror::Error;

/// Errors returnable by the L1 interaction engine and its adapters.
#[derive(Debug, Error)]
pub enum L1Error {
    /// Turn id not found.
    #[error("turn not found")]
    UnknownTurn,
    /// STT adapter failure.
    #[error("stt: {0}")]
    Stt(String),
    /// TTS adapter failure.
    #[error("tts: {0}")]
    Tts(String),
    /// Reflex classifier exceeded its budget.
    #[error("reflex budget exceeded after {ms}ms")]
    ReflexBudget {
        /// Elapsed ms.
        ms: u64,
    },
    /// Router client rejected dispatch.
    #[error("router client: {0}")]
    Router(String),
    /// Policy gate surfaced an error from L5.
    #[error("policy: {0}")]
    Policy(String),
    /// Catch-all.
    #[error("internal: {0}")]
    Internal(String),
}
