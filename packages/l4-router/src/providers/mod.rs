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
#[cfg(feature = "speech-whispercpp")]
pub mod whispercpp_speech;

#[cfg(feature = "vision-llamacpp")]
pub use llamacpp_vision::{LlamaCppVisionConfig, LlamaCppVisionProvider};
#[cfg(feature = "ollama-provider")]
pub use ollama::{
    ChatCompletion, ChatMessage, MessageRole, OllamaConfig, OllamaConfigError, OllamaProvider,
};
#[cfg(feature = "ollama-provider")]
pub use ollama_vision::{OllamaVisionConfig, OllamaVisionProvider};
#[cfg(feature = "speech-whispercpp")]
pub use whispercpp_speech::{
    WhisperCppConfigError, WhisperCppSpeechConfig, WhisperCppSpeechProvider,
};

/// Shared env-lock for provider tests that mutate `AETHER_OLLAMA_*`
/// env vars. Any test in `providers/*` that calls `env::set_var` or
/// `env::remove_var` on one of those keys MUST take this lock so the
/// text + vision test modules don't race each other. Before this
/// shared static, each module had its own `static` lock, which
/// serialised intra-module tests but not cross-module tests; under
/// parallel execution the text-provider's
/// `from_env_uses_defaults_when_vars_unset` flaked when the
/// vision-provider tests set `AETHER_OLLAMA_BASE_URL` mid-run. See
/// `HANDOFF_2026-05-17_SESSION_END_ULTRA_LONG_SETUP.md` Risk E.
///
/// The returned `MutexGuard` handles poisoning internally — a panic
/// inside a guarded test only poisons the lock, which this helper
/// recovers from so the next test can still run.
#[cfg(all(test, feature = "ollama-provider"))]
pub(crate) fn env_lock() -> std::sync::MutexGuard<'static, ()> {
    use std::sync::{Mutex, OnceLock};
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}
