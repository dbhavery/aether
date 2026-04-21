//! Provider adapters.
//!
//! Each submodule implements a concrete backend for
//! [`crate::ProviderAdapter`] / [`crate::ModelRouter`]. Everything under
//! this namespace is feature-gated so the default OSS build pulls no
//! network dependencies and calls no external services.

#[cfg(feature = "vision-llamacpp")]
pub mod llamacpp_vision;
#[cfg(feature = "ollama-provider")]
pub mod ollama;
#[cfg(feature = "ollama-provider")]
pub mod ollama_vision;

#[cfg(feature = "vision-llamacpp")]
pub use llamacpp_vision::{LlamaCppVisionConfig, LlamaCppVisionProvider};
#[cfg(feature = "ollama-provider")]
pub use ollama::{
    ChatCompletion, ChatMessage, MessageRole, OllamaConfig, OllamaConfigError, OllamaProvider,
};
#[cfg(feature = "ollama-provider")]
pub use ollama_vision::{OllamaVisionConfig, OllamaVisionProvider};
