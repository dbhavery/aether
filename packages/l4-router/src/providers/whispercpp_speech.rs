//! whisper.cpp speech adapter — Voice V1 step 2 scaffold.
//!
//! **Scope for this step:** provider abstraction + construction +
//! env-config parsing + healthcheck only. Transcription is NOT wired
//! yet — `transcribe` returns a clear, loud error so the shell cannot
//! accidentally ship a half-finished voice surface. The real
//! inference call lands in Voice V1 step 4, alongside the
//! `transcribe_utterance` Tauri command.
//!
//! Talks (or will talk) to the whisper.cpp HTTP server wrapper
//! (`whisper-server` / `whisper.cpp/examples/server`) whose default
//! bind is `http://127.0.0.1:8081`. We deliberately DO NOT pin the
//! transport shape (HTTP vs FFI) here — that decision belongs to
//! step 4 when real audio starts flowing. The scaffold just stands up
//! the provider identity, configuration surface, healthcheck probe,
//! and object-safe trait implementation so later steps can plug
//! transcription in without reshaping the interface.
//!
//! ## Defaults and config
//!
//! Constructed via [`WhisperCppSpeechConfig::from_env`] which reads:
//! - `AETHER_WHISPERCPP_SPEECH_BASE_URL` (default
//!   `http://127.0.0.1:8081`),
//! - `AETHER_WHISPERCPP_SPEECH_MODEL` — **required** opt-in. If unset,
//!   `from_env` returns `None` so the shell falls back cleanly,
//! - `AETHER_WHISPERCPP_SPEECH_LANGUAGE` — optional ISO-639-1 hint
//!   (e.g. `"en"`), defaults to `None` so the adapter auto-detects,
//! - `AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS` (default `60_000`).
//!
//! The provider's config error type ([`WhisperCppConfigError`]) is
//! intentionally **not** unified with `OllamaConfigError` /
//! `LlamaCppConfigError`. Each adapter owns its own taxonomy so a
//! future remote adapter can have its own without surgery on the
//! others — the same constraint Vision V1 locked for its providers.

use std::env;
use std::sync::RwLock;
use std::time::Duration;

use crate::error::L4Error;
use crate::speech::{SpeechProvider, SpeechRequest, SpeechResponse};

/// Errors that can arise when reading [`WhisperCppSpeechConfig`] from
/// env. Kept deliberately distinct from the vision provider config
/// errors — see module docs for rationale.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum WhisperCppConfigError {
    /// `AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS` did not parse as `u64`.
    #[error("invalid AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS: {0}")]
    InvalidTimeout(String),
    /// Base URL set to empty string explicitly.
    #[error("AETHER_WHISPERCPP_SPEECH_BASE_URL must not be empty")]
    EmptyBaseUrl,
    /// Language hint set to an empty (or whitespace-only) string.
    /// Distinct from "no language env var set at all", which cleanly
    /// resolves to `None`.
    #[error("AETHER_WHISPERCPP_SPEECH_LANGUAGE must not be empty if set")]
    EmptyLanguage,
}

const DEFAULT_BASE_URL: &str = "http://127.0.0.1:8081";
const DEFAULT_TIMEOUT_MS: u64 = 60_000;

/// Configuration for [`WhisperCppSpeechProvider`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WhisperCppSpeechConfig {
    /// Base URL of the whisper.cpp server, e.g. `http://127.0.0.1:8081`.
    pub base_url: String,
    /// Model id the server was launched with (e.g. `ggml-base.en.bin`).
    pub model: String,
    /// Optional ISO-639-1 language hint (e.g. `"en"`), `None` → auto.
    pub language: Option<String>,
    /// Per-request timeout in milliseconds.
    pub timeout_ms: u64,
}

impl WhisperCppSpeechConfig {
    /// Build from env. Returns `None` when the user has not opted in
    /// via `AETHER_WHISPERCPP_SPEECH_MODEL`. Returns `Some(Err(_))`
    /// only when env opt-in is present but malformed.
    ///
    /// Mirrors the shape of [`crate::providers::LlamaCppVisionConfig`]'s
    /// `from_env` — the absence of the required model var is a "not
    /// configured, not a bug" signal, not an error.
    pub fn from_env() -> Option<Result<Self, WhisperCppConfigError>> {
        let model = env::var("AETHER_WHISPERCPP_SPEECH_MODEL").ok()?;
        if model.trim().is_empty() {
            return None;
        }
        let base_url = env::var("AETHER_WHISPERCPP_SPEECH_BASE_URL")
            .ok()
            .unwrap_or_else(|| DEFAULT_BASE_URL.to_string());
        if base_url.is_empty() {
            return Some(Err(WhisperCppConfigError::EmptyBaseUrl));
        }
        let language = match env::var("AETHER_WHISPERCPP_SPEECH_LANGUAGE") {
            Ok(s) if s.trim().is_empty() => {
                return Some(Err(WhisperCppConfigError::EmptyLanguage));
            }
            Ok(s) => Some(s),
            Err(_) => None,
        };
        let timeout_ms = match env::var("AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS") {
            Ok(s) => match s.parse::<u64>() {
                Ok(n) => n,
                Err(_) => return Some(Err(WhisperCppConfigError::InvalidTimeout(s))),
            },
            Err(_) => DEFAULT_TIMEOUT_MS,
        };
        Some(Ok(Self {
            base_url,
            model,
            language,
            timeout_ms,
        }))
    }
}

/// whisper.cpp HTTP speech adapter (scaffold).
///
/// Model id is held behind an `RwLock` so a future hot-swap surface
/// can update it without rebuilding the provider. Base URL, language,
/// and timeout are immutable after construction — swapping those
/// requires a restart anyway.
pub struct WhisperCppSpeechProvider {
    base_url: String,
    model: RwLock<String>,
    language: Option<String>,
    timeout_ms: u64,
    agent: ureq::Agent,
}

impl WhisperCppSpeechProvider {
    /// Construct from config. Does not probe the server.
    pub fn new(config: WhisperCppSpeechConfig) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_millis(config.timeout_ms))
            .build();
        Self {
            base_url: config.base_url,
            model: RwLock::new(config.model),
            language: config.language,
            timeout_ms: config.timeout_ms,
            agent,
        }
    }

    /// Current model id this provider is pointed at.
    pub fn model(&self) -> String {
        self.model
            .read()
            .expect("whispercpp-speech model read lock")
            .clone()
    }

    /// Base URL this provider is pointed at.
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// Configured language hint, if any.
    pub fn language(&self) -> Option<&str> {
        self.language.as_deref()
    }

    /// Per-request timeout in milliseconds. Immutable after construction.
    #[allow(dead_code)]
    pub fn timeout_ms(&self) -> u64 {
        self.timeout_ms
    }
}

impl SpeechProvider for WhisperCppSpeechProvider {
    fn id(&self) -> &str {
        "whispercpp-speech"
    }

    fn label(&self) -> String {
        format!("whisper.cpp · {} · {}", self.model(), self.base_url)
    }

    fn healthcheck(&self) -> Result<(), L4Error> {
        // whisper.cpp's HTTP server wrapper does not have a single
        // canonical health endpoint across builds. We probe the root
        // `/` which every build serves (either the static HTML demo
        // page or a JSON index). Any response that did not fail at
        // the transport layer is treated as "daemon is up" — the
        // real transcription call in step 4 is the authoritative
        // "provider can do work" signal.
        let url = format!("{}/", self.base_url.trim_end_matches('/'));
        match self.agent.get(&url).call() {
            Ok(_) => Ok(()),
            Err(e) => Err(L4Error::ProviderUnknown {
                detail: format!("whispercpp-speech healthcheck at {url}: {e}"),
            }),
        }
    }

    fn transcribe(&self, _req: SpeechRequest) -> Result<SpeechResponse, L4Error> {
        // Scaffold-only — the real wire call lands in Voice V1 step 4
        // alongside the `transcribe_utterance` Tauri command. Return
        // a loud error so an accidental early caller gets a clear
        // signal instead of a silent empty transcript.
        Err(L4Error::ProviderUnknown {
            detail: "whispercpp-speech: transcription wiring deferred \
                to Voice V1 step 4 (transcribe_utterance)"
                .to_string(),
        })
    }

    fn set_model(&self, id: &str) -> Result<(), L4Error> {
        let trimmed = id.trim();
        if trimmed.is_empty() {
            return Err(L4Error::ProviderBadResponse {
                detail: "whispercpp-speech set_model: id must not be empty".to_string(),
            });
        }
        *self
            .model
            .write()
            .expect("whispercpp-speech model write lock") = trimmed.to_string();
        Ok(())
    }

    fn current_model(&self) -> Option<String> {
        Some(self.model())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unset_env() {
        env::remove_var("AETHER_WHISPERCPP_SPEECH_MODEL");
        env::remove_var("AETHER_WHISPERCPP_SPEECH_BASE_URL");
        env::remove_var("AETHER_WHISPERCPP_SPEECH_LANGUAGE");
        env::remove_var("AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS");
    }

    // Env-reading tests share process-global env vars. Serialize so
    // they don't stomp each other when cargo runs tests in parallel.
    static ENV_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn from_env_returns_none_without_model_var() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        assert!(WhisperCppSpeechConfig::from_env().is_none());
    }

    #[test]
    fn from_env_returns_none_for_whitespace_model() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "   ");
        assert!(WhisperCppSpeechConfig::from_env().is_none());
        unset_env();
    }

    #[test]
    fn from_env_picks_up_explicit_model_with_defaults() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-base.en");
        let cfg = WhisperCppSpeechConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.model, "ggml-base.en");
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        assert_eq!(cfg.timeout_ms, DEFAULT_TIMEOUT_MS);
        assert!(cfg.language.is_none());
        unset_env();
    }

    #[test]
    fn from_env_picks_up_explicit_language() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-small");
        env::set_var("AETHER_WHISPERCPP_SPEECH_LANGUAGE", "ja");
        let cfg = WhisperCppSpeechConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.language.as_deref(), Some("ja"));
        unset_env();
    }

    #[test]
    fn from_env_rejects_empty_base_url() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-base.en");
        env::set_var("AETHER_WHISPERCPP_SPEECH_BASE_URL", "");
        let r = WhisperCppSpeechConfig::from_env().unwrap();
        assert!(matches!(r, Err(WhisperCppConfigError::EmptyBaseUrl)));
        unset_env();
    }

    #[test]
    fn from_env_rejects_empty_language() {
        // Distinct from "no language set" which resolves cleanly.
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-base.en");
        env::set_var("AETHER_WHISPERCPP_SPEECH_LANGUAGE", "   ");
        let r = WhisperCppSpeechConfig::from_env().unwrap();
        assert!(matches!(r, Err(WhisperCppConfigError::EmptyLanguage)));
        unset_env();
    }

    #[test]
    fn from_env_rejects_malformed_timeout() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-base.en");
        env::set_var("AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS", "not-a-number");
        let r = WhisperCppSpeechConfig::from_env().unwrap();
        assert!(matches!(r, Err(WhisperCppConfigError::InvalidTimeout(_))));
        unset_env();
    }

    #[test]
    fn from_env_accepts_valid_timeout() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_WHISPERCPP_SPEECH_MODEL", "ggml-base.en");
        env::set_var("AETHER_WHISPERCPP_SPEECH_TIMEOUT_MS", "45000");
        let cfg = WhisperCppSpeechConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.timeout_ms, 45_000);
        unset_env();
    }

    #[test]
    fn provider_id_is_stable() {
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        assert_eq!(p.id(), "whispercpp-speech");
    }

    #[test]
    fn label_reflects_model_and_base_url() {
        let cfg = WhisperCppSpeechConfig {
            base_url: "http://127.0.0.1:8081".to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let label = p.label();
        assert!(label.contains("whisper.cpp"));
        assert!(label.contains("ggml-base.en"));
        assert!(label.contains("127.0.0.1:8081"));
    }

    #[test]
    fn set_model_round_trips_and_label_reflects_new_model() {
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        assert_eq!(p.model(), "ggml-base.en");
        assert_eq!(p.current_model().as_deref(), Some("ggml-base.en"));
        assert!(p.label().contains("ggml-base.en"));

        p.set_model("ggml-small").expect("set_model");
        assert_eq!(p.model(), "ggml-small");
        assert_eq!(p.current_model().as_deref(), Some("ggml-small"));
        assert!(p.label().contains("ggml-small"));
        assert!(!p.label().contains("ggml-base.en"));
    }

    #[test]
    fn set_model_rejects_empty_id() {
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        assert!(p.set_model("").is_err());
        assert!(p.set_model("   ").is_err());
        assert_eq!(p.model(), "ggml-base.en");
    }

    #[test]
    fn transcribe_returns_scaffold_error() {
        // Scaffold must NOT silently succeed — any caller that reaches
        // this before step 4 lands needs a loud signal.
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let req = SpeechRequest {
            audio_b64: "DATA".to_string(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: None,
        };
        let err = p.transcribe(req).unwrap_err();
        match err {
            L4Error::ProviderUnknown { detail } => {
                assert!(
                    detail.contains("deferred to Voice V1 step 4"),
                    "unexpected scaffold error detail: {detail}"
                );
            }
            other => panic!("expected ProviderUnknown, got {other:?}"),
        }
    }

    #[test]
    fn language_accessor_reflects_config() {
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: Some("en".to_string()),
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        assert_eq!(p.language(), Some("en"));
        assert_eq!(p.base_url(), DEFAULT_BASE_URL);
        assert_eq!(p.timeout_ms(), 1_000);
    }

    #[test]
    fn healthcheck_fails_cleanly_against_unreachable_daemon() {
        // Point at a port nothing is listening on. Must not hang the
        // test (timeout config keeps the probe short) and must return
        // a structured error that identifies whispercpp-speech in
        // the detail so operators can diagnose without guessing.
        let cfg = WhisperCppSpeechConfig {
            base_url: "http://127.0.0.1:1".to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 500,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let err = p.healthcheck().unwrap_err();
        match err {
            L4Error::ProviderUnknown { detail } => {
                assert!(
                    detail.contains("whispercpp-speech"),
                    "healthcheck error should name the provider: {detail}"
                );
            }
            other => panic!("expected ProviderUnknown, got {other:?}"),
        }
    }

    #[test]
    fn default_list_models_is_empty_for_scaffold() {
        // Scaffold stage — default impl on the trait is inherited.
        // When step 3 wires registry persistence and model selection,
        // list_models may be overridden with a real probe. Until then,
        // the empty default is the contract.
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        assert!(p.list_models().unwrap().is_empty());
    }
}
