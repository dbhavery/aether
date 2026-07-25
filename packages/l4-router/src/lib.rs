//! # aether-l4-router
//!
//! **Status:** Wave 4 stub.
//!
//! L4 owns the model + tool router: the 7-tier abstraction (reflex → frontier),
//! tool-call dispatch, per-request policy gating, cost-event emission,
//! Decision-4 per-step re-evaluation.
//! Source: `ARCHITECTURE.md` (the L4 model/tool routing layer) and `docs/LLM-PROVIDERS.md`.

#![deny(unsafe_code)]
#![warn(missing_docs)]
#![allow(dead_code)]

pub mod error;
pub mod providers;
pub mod router;
pub mod speech;
pub mod vision;

pub use error::L4Error;
pub use router::{
    ModelRouter, ProviderAdapter, ProviderId, RouterTier, ToolCall, ToolError, ToolResult,
};
pub use speech::{split_audio_data_url, SpeechProvider, SpeechRequest, SpeechResponse};
pub use vision::{split_data_url, VisionProvider, VisionRequest, VisionResponse};

#[cfg(feature = "ollama-provider")]
pub use providers::{
    ChatCompletion, ChatMessage, MessageRole, OllamaConfig, OllamaConfigError, OllamaProvider,
    OllamaVisionConfig, OllamaVisionProvider,
};
#[cfg(feature = "vision-llamacpp")]
pub use providers::{LlamaCppVisionConfig, LlamaCppVisionProvider};
#[cfg(feature = "speech-whispercpp")]
pub use providers::{WhisperCppConfigError, WhisperCppSpeechConfig, WhisperCppSpeechProvider};
