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

use serde::Deserialize;

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

/// Shape of the JSON response whisper.cpp returns from `/inference`.
///
/// The OpenAI-compatible minimal surface exposes `text`; richer
/// shapes (segments, language, duration) may come along with newer
/// builds — we deserialize only what we consume. `serde` drops the
/// rest silently.
#[derive(Debug, Deserialize)]
struct WhisperResponse {
    /// Full transcript. `None` / missing means "server returned
    /// JSON but no text field" which we render as an empty
    /// transcript (the caller decides how to surface that).
    text: Option<String>,
}

/// Derive a reasonable filename for the multipart `file` part from
/// the MIME type. whisper-server treats the extension as a hint for
/// format sniffing. WAV is the Voice V1 native format.
fn derive_filename(mime: &str) -> String {
    let ext = match mime.to_ascii_lowercase().as_str() {
        "audio/wav" | "audio/wave" | "audio/x-wav" => "wav",
        "audio/mpeg" | "audio/mp3" => "mp3",
        "audio/ogg" | "audio/opus" => "ogg",
        _ => "wav",
    };
    format!("utterance.{ext}")
}

/// Stable-ish multipart boundary. Uses a time + pid mix so
/// concurrent calls from the same process don't collide; the
/// boundary does not need to be cryptographically random.
fn multipart_boundary() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0);
    format!("----aether-whispercpp-{pid}-{nanos:x}-{n:x}")
}

/// Build a multipart/form-data body for whisper-server's
/// `/inference` endpoint. Emits two parts when language is set:
///   - `file`      — binary audio bytes
///   - `language`  — ISO-639-1 hint string
///
/// Pure helper so the contract can be unit-tested without touching
/// the network. Uses CRLF line endings per RFC 2046.
fn build_multipart_body(
    boundary: &str,
    filename: &str,
    mime: &str,
    audio: &[u8],
    language: Option<&str>,
) -> Vec<u8> {
    let mut body: Vec<u8> = Vec::with_capacity(audio.len() + 256);
    // File part
    body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
    body.extend_from_slice(
        format!("Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n")
            .as_bytes(),
    );
    body.extend_from_slice(format!("Content-Type: {mime}\r\n\r\n").as_bytes());
    body.extend_from_slice(audio);
    body.extend_from_slice(b"\r\n");

    // Optional language hint
    if let Some(lang) = language {
        body.extend_from_slice(format!("--{boundary}\r\n").as_bytes());
        body.extend_from_slice(b"Content-Disposition: form-data; name=\"language\"\r\n\r\n");
        body.extend_from_slice(lang.as_bytes());
        body.extend_from_slice(b"\r\n");
    }

    // Closing boundary
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}

/// Minimal pure-Rust base64 decoder. Accepts the standard alphabet
/// (RFC 4648) with optional `=` padding; tolerant of a trailing
/// newline and of whitespace (stripped). Returns the decoded bytes
/// or a human-readable error string. Inline — saves a new
/// dependency on `base64` for a single call site.
fn decode_base64(input: &str) -> Result<Vec<u8>, String> {
    // Strip whitespace (newlines, spaces, tabs). Case-sensitive
    // alphabet: A-Z, a-z, 0-9, +, /. Padding is `=`.
    let cleaned: Vec<u8> = input.bytes().filter(|b| !b.is_ascii_whitespace()).collect();
    if cleaned.len() % 4 != 0 {
        return Err(format!(
            "base64 input length {} is not a multiple of 4",
            cleaned.len()
        ));
    }
    let mut out = Vec::with_capacity(cleaned.len() / 4 * 3);
    let mut i = 0;
    while i < cleaned.len() {
        let chunk = &cleaned[i..i + 4];
        let v0 = decode_base64_char(chunk[0])
            .ok_or_else(|| format!("invalid base64 char at offset {i}: {:?}", chunk[0] as char))?;
        let v1 = decode_base64_char(chunk[1]).ok_or_else(|| {
            format!(
                "invalid base64 char at offset {}: {:?}",
                i + 1,
                chunk[1] as char
            )
        })?;
        let pad2 = chunk[2] == b'=';
        let pad3 = chunk[3] == b'=';
        let v2 = if pad2 {
            0u8
        } else {
            decode_base64_char(chunk[2]).ok_or_else(|| {
                format!(
                    "invalid base64 char at offset {}: {:?}",
                    i + 2,
                    chunk[2] as char
                )
            })?
        };
        let v3 = if pad3 {
            0u8
        } else {
            decode_base64_char(chunk[3]).ok_or_else(|| {
                format!(
                    "invalid base64 char at offset {}: {:?}",
                    i + 3,
                    chunk[3] as char
                )
            })?
        };

        out.push((v0 << 2) | (v1 >> 4));
        if !pad2 {
            out.push(((v1 & 0x0F) << 4) | (v2 >> 2));
        }
        if !pad3 {
            out.push(((v2 & 0x03) << 6) | v3);
        }
        i += 4;
    }
    Ok(out)
}

fn decode_base64_char(b: u8) -> Option<u8> {
    match b {
        b'A'..=b'Z' => Some(b - b'A'),
        b'a'..=b'z' => Some(b - b'a' + 26),
        b'0'..=b'9' => Some(b - b'0' + 52),
        b'+' => Some(62),
        b'/' => Some(63),
        _ => None,
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

    fn transcribe(&self, req: SpeechRequest) -> Result<SpeechResponse, L4Error> {
        // Decode the base64 audio payload. Inline implementation —
        // one new dependency (base64 crate) avoided; the payload is
        // ~< a few hundred KB for a single utterance so the allocator
        // cost is trivial.
        let audio =
            decode_base64(&req.audio_b64).map_err(|detail| L4Error::ProviderBadResponse {
                detail: format!("whispercpp-speech: audio base64 decode failed: {detail}"),
            })?;
        if audio.is_empty() {
            return Err(L4Error::ProviderBadResponse {
                detail: "whispercpp-speech: decoded audio payload was empty".to_string(),
            });
        }

        // Language resolution precedence:
        //   1. per-request `language` hint from the shell,
        //   2. adapter config language (env override),
        //   3. whisper.cpp's own auto-detect (absent `language` field).
        let language = req
            .language
            .as_deref()
            .or(self.language.as_deref())
            .map(str::to_string);

        let filename = derive_filename(&req.mime);
        let boundary = multipart_boundary();
        let body =
            build_multipart_body(&boundary, &filename, &req.mime, &audio, language.as_deref());

        let url = format!("{}/inference", self.base_url.trim_end_matches('/'));
        let content_type = format!("multipart/form-data; boundary={boundary}");

        let resp = self
            .agent
            .post(&url)
            .set("Content-Type", &content_type)
            .send_bytes(&body)
            .map_err(|e| L4Error::ProviderUnknown {
                detail: format!("whispercpp-speech POST {url} failed: {e}"),
            })?;

        // Whisper's HTTP server defaults to a JSON body with at
        // least a `text` field. Builds that support `response_format`
        // may widen it; we only depend on `text`. `into_json` returns
        // `Err` if the server returned non-JSON (e.g. HTML error
        // page) — surface as a provider error.
        let parsed: WhisperResponse =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("whispercpp-speech JSON decode failed: {e}"),
            })?;
        let text = parsed.text.unwrap_or_default();

        Ok(SpeechResponse {
            text,
            // Whisper's OpenAI-compatible surface does not report an
            // average logprob — leave confidence unset. Builds that
            // expose segment-level logprobs could wire a min/avg
            // here in a later slice; the trait contract says
            // confidence is informational anyway.
            confidence: None,
            prompt_tokens: None,
            completion_tokens: None,
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
    fn transcribe_rejects_empty_audio() {
        // Decoded empty payload must short-circuit with a clear
        // bad-response error rather than sending an empty multipart
        // part to the server. Same contract `transcribe_utterance`
        // enforces at the shell gate.
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let req = SpeechRequest {
            audio_b64: String::new(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: None,
        };
        let err = p.transcribe(req).unwrap_err();
        match err {
            L4Error::ProviderBadResponse { detail } => {
                assert!(
                    detail.contains("empty"),
                    "expected empty-payload detail, got: {detail}"
                );
            }
            other => panic!("expected ProviderBadResponse, got {other:?}"),
        }
    }

    #[test]
    fn transcribe_rejects_malformed_base64() {
        let cfg = WhisperCppSpeechConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1_000,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let req = SpeechRequest {
            // Illegal chars in the alphabet.
            audio_b64: "!!!!".to_string(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: None,
        };
        let err = p.transcribe(req).unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn transcribe_surfaces_transport_error_for_unreachable_server() {
        // Tiny timeout against a port that's almost certainly closed
        // (65535) — proves the error bubbles up as ProviderUnknown,
        // not a silent empty transcript.
        let cfg = WhisperCppSpeechConfig {
            base_url: "http://127.0.0.1:65535".to_string(),
            model: "ggml-base.en".to_string(),
            language: None,
            timeout_ms: 1,
        };
        let p = WhisperCppSpeechProvider::new(cfg);
        let req = SpeechRequest {
            // "AAAA" decodes to 3 zero bytes — non-empty so we reach
            // the HTTP layer.
            audio_b64: "AAAA".to_string(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: None,
        };
        let err = p.transcribe(req).unwrap_err();
        assert!(matches!(err, L4Error::ProviderUnknown { .. }));
    }

    #[test]
    fn decode_base64_round_trips_simple_payloads() {
        assert_eq!(decode_base64("").unwrap(), Vec::<u8>::new());
        // "Man" = TWFu
        assert_eq!(decode_base64("TWFu").unwrap(), b"Man".to_vec());
        // "Ma" = TWE=
        assert_eq!(decode_base64("TWE=").unwrap(), b"Ma".to_vec());
        // "M" = TQ==
        assert_eq!(decode_base64("TQ==").unwrap(), b"M".to_vec());
        // Binary bytes 0x00 0x80 0xff 0x7f = AID/fw==
        assert_eq!(
            decode_base64("AID/fw==").unwrap(),
            vec![0x00, 0x80, 0xff, 0x7f]
        );
    }

    #[test]
    fn decode_base64_tolerates_whitespace() {
        assert_eq!(decode_base64("TW\nFu").unwrap(), b"Man".to_vec());
        assert_eq!(decode_base64("TW Fu").unwrap(), b"Man".to_vec());
    }

    #[test]
    fn decode_base64_rejects_bad_chars() {
        assert!(decode_base64("!!!!").is_err());
        assert!(decode_base64("AB@D").is_err());
    }

    #[test]
    fn decode_base64_rejects_bad_length() {
        // 3 chars after whitespace strip → not a multiple of 4.
        assert!(decode_base64("ABC").is_err());
    }

    #[test]
    fn build_multipart_body_includes_file_part_and_boundary() {
        let body = build_multipart_body(
            "bnd",
            "utterance.wav",
            "audio/wav",
            &[0x01, 0x02, 0x03],
            None,
        );
        let as_str = String::from_utf8_lossy(&body).to_string();
        assert!(as_str.contains("--bnd\r\n"));
        assert!(as_str
            .contains("Content-Disposition: form-data; name=\"file\"; filename=\"utterance.wav\""));
        assert!(as_str.contains("Content-Type: audio/wav\r\n\r\n"));
        assert!(as_str.ends_with("--bnd--\r\n"));
        // Raw bytes survived verbatim in the middle.
        assert!(body.windows(3).any(|w| w == [0x01, 0x02, 0x03]));
    }

    #[test]
    fn build_multipart_body_emits_language_part_when_provided() {
        let body = build_multipart_body("bnd", "u.wav", "audio/wav", &[0u8; 4], Some("ja"));
        let as_str = String::from_utf8_lossy(&body).to_string();
        assert!(
            as_str.contains("Content-Disposition: form-data; name=\"language\""),
            "language part missing: {as_str}"
        );
        assert!(as_str.contains("\r\n\r\nja\r\n"));
    }

    #[test]
    fn derive_filename_defaults_to_wav() {
        assert_eq!(derive_filename("audio/wav"), "utterance.wav");
        assert_eq!(derive_filename("audio/wave"), "utterance.wav");
        assert_eq!(derive_filename("audio/mpeg"), "utterance.mp3");
        assert_eq!(derive_filename("audio/ogg"), "utterance.ogg");
        // Unknown MIME → fall back to wav so whisper-server's
        // default sniffer still has a hint.
        assert_eq!(derive_filename("audio/something-weird"), "utterance.wav");
    }

    #[test]
    fn multipart_boundary_is_unique_across_calls() {
        let a = multipart_boundary();
        let b = multipart_boundary();
        assert_ne!(a, b);
        assert!(a.starts_with("----aether-whispercpp-"));
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
