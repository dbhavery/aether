//! llama.cpp vision adapter — sibling to the Ollama vision adapter.
//!
//! Talks to a `llama-server` (or any OpenAI-compatible server) at
//! `/v1/chat/completions` with the standard OpenAI `image_url`
//! content-block shape. The wire format is meaningfully different
//! from Ollama's `images` array, which is exactly why this exists —
//! it proves the [`VisionProvider`] trait surface is correct and gives
//! users a second local-first choice (llama.cpp + LLaVA / MiniCPM-V /
//! similar models served over HTTP).
//!
//! ## Defaults and config
//!
//! Constructed via [`LlamaCppVisionConfig::from_env`] which reads:
//! - `AETHER_LLAMACPP_VISION_BASE_URL` (default
//!   `http://127.0.0.1:8080`),
//! - `AETHER_LLAMACPP_VISION_MODEL` — **required** opt-in. If unset,
//!   `from_env` returns `None` so the shell falls back cleanly,
//! - `AETHER_LLAMACPP_VISION_TIMEOUT_MS` (default `120_000`).
//!
//! ## Wire shape
//!
//! ```json
//! {
//!   "model": "llava-v1.6",
//!   "messages": [
//!     {
//!       "role": "user",
//!       "content": [
//!         { "type": "text", "text": "describe what you see" },
//!         {
//!           "type": "image_url",
//!           "image_url": { "url": "data:image/jpeg;base64,<...>" }
//!         }
//!       ]
//!     }
//!   ],
//!   "stream": false
//! }
//! ```

use std::env;
use std::sync::RwLock;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::error::L4Error;
use crate::vision::{VisionProvider, VisionRequest, VisionResponse};

/// Errors that can arise when reading [`LlamaCppVisionConfig`] from
/// env. Mirrors the shape of `LlamaCppConfigError` so the two adapters
/// stay symmetric without forcing a cross-feature dependency.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum LlamaCppConfigError {
    /// `AETHER_LLAMACPP_VISION_TIMEOUT_MS` did not parse as `u64`.
    #[error("invalid AETHER_LLAMACPP_VISION_TIMEOUT_MS: {0}")]
    InvalidTimeout(String),
    /// Base URL set to empty string explicitly.
    #[error("AETHER_LLAMACPP_VISION_BASE_URL must not be empty")]
    EmptyBaseUrl,
}

const DEFAULT_BASE_URL: &str = "http://127.0.0.1:8080";
const DEFAULT_TIMEOUT_MS: u64 = 120_000;
const DEFAULT_VISION_CUE: &str =
    "Describe what you see in this image in a short, helpful sentence.";

/// Configuration for [`LlamaCppVisionProvider`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LlamaCppVisionConfig {
    /// Base URL of the llama-server, e.g. `http://127.0.0.1:8080`.
    pub base_url: String,
    /// Vision-capable model id (matches the `model` the server was
    /// launched with; some llama-server builds tolerate any string).
    pub model: String,
    /// Per-request timeout in milliseconds.
    pub timeout_ms: u64,
}

impl LlamaCppVisionConfig {
    /// Build from env. Returns `None` when the user has not opted in
    /// via `AETHER_LLAMACPP_VISION_MODEL`. Returns `Some(Err(_))` only
    /// when env opt-in is present but malformed.
    pub fn from_env() -> Option<Result<Self, LlamaCppConfigError>> {
        let model = env::var("AETHER_LLAMACPP_VISION_MODEL").ok()?;
        if model.trim().is_empty() {
            return None;
        }
        let base_url = env::var("AETHER_LLAMACPP_VISION_BASE_URL")
            .ok()
            .unwrap_or_else(|| DEFAULT_BASE_URL.to_string());
        if base_url.is_empty() {
            return Some(Err(LlamaCppConfigError::EmptyBaseUrl));
        }
        let timeout_ms = match env::var("AETHER_LLAMACPP_VISION_TIMEOUT_MS") {
            Ok(s) => match s.parse::<u64>() {
                Ok(n) => n,
                Err(_) => return Some(Err(LlamaCppConfigError::InvalidTimeout(s))),
            },
            Err(_) => DEFAULT_TIMEOUT_MS,
        };
        Some(Ok(Self {
            base_url,
            model,
            timeout_ms,
        }))
    }
}

/// Vision-capable llama.cpp HTTP adapter.
///
/// Model id is held behind an `RwLock` so the shell's
/// `set_active_vision_model` command can hot-swap the model without
/// rebuilding the provider. Base URL and timeout are immutable after
/// construction — swapping those requires a restart anyway.
pub struct LlamaCppVisionProvider {
    base_url: String,
    model: RwLock<String>,
    timeout_ms: u64,
    agent: ureq::Agent,
}

#[derive(Debug, Clone, Serialize)]
struct ChatRequest<'a> {
    model: &'a str,
    messages: Vec<ChatMessage<'a>>,
    stream: bool,
}

#[derive(Debug, Clone, Serialize)]
struct ChatMessage<'a> {
    role: &'a str,
    content: Vec<ContentBlock<'a>>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum ContentBlock<'a> {
    Text { text: &'a str },
    ImageUrl { image_url: ImageUrl<'a> },
}

#[derive(Debug, Clone, Serialize)]
struct ImageUrl<'a> {
    url: &'a str,
}

#[derive(Debug, Clone, Deserialize)]
struct ChatResponse {
    choices: Vec<ChoiceWire>,
    #[serde(default)]
    usage: Option<UsageWire>,
}

#[derive(Debug, Clone, Deserialize)]
struct ChoiceWire {
    message: ChoiceMessageWire,
}

#[derive(Debug, Clone, Deserialize)]
struct ChoiceMessageWire {
    /// llama-server returns the assistant text as a plain string in
    /// non-streaming mode (`"content": "..."`).
    content: String,
}

#[derive(Debug, Clone, Deserialize)]
struct UsageWire {
    #[serde(default)]
    prompt_tokens: Option<u32>,
    #[serde(default)]
    completion_tokens: Option<u32>,
}

/// Build the JSON payload sent to `/v1/chat/completions`. Pure;
/// exposed for unit tests so the wire shape can be locked without a
/// live server. The data URL is reattached locally because OpenAI's
/// vision content block expects the full `data:image/...;base64,...`
/// prefix on the URL.
pub fn build_vision_payload(
    model: &str,
    cue: &str,
    image_b64: &str,
    mime: &str,
) -> serde_json::Value {
    let data_url = format!("data:{};base64,{}", mime, image_b64);
    let body = ChatRequest {
        model,
        messages: vec![ChatMessage {
            role: "user",
            content: vec![
                ContentBlock::Text { text: cue },
                ContentBlock::ImageUrl {
                    image_url: ImageUrl { url: &data_url },
                },
            ],
        }],
        stream: false,
    };
    serde_json::to_value(&body).expect("ChatRequest always serializes")
}

/// Parse the JSON body returned by `/v1/models` (OpenAI-compatible)
/// into a list of model ids (`data[].id`). Pure; exposed for unit
/// tests so the wire shape can be locked without a live server.
/// Tolerant of missing fields — never blows up the UI on a malformed
/// `models` response.
pub fn parse_models_response(json: &serde_json::Value) -> Vec<String> {
    let Some(arr) = json.get("data").and_then(|v| v.as_array()) else {
        return Vec::new();
    };
    arr.iter()
        .filter_map(|m| m.get("id").and_then(|n| n.as_str()))
        .map(|s| s.to_string())
        .collect()
}

/// Pull `(text, prompt_tokens, completion_tokens)` out of the JSON
/// `/v1/chat/completions` non-streaming response.
pub fn parse_vision_response(json: &serde_json::Value) -> Result<VisionResponse, L4Error> {
    let resp: ChatResponse =
        serde_json::from_value(json.clone()).map_err(|e| L4Error::ProviderBadResponse {
            detail: format!("llamacpp-vision: invalid response: {e}"),
        })?;
    let first = resp
        .choices
        .into_iter()
        .next()
        .ok_or_else(|| L4Error::ProviderBadResponse {
            detail: "llamacpp-vision: response had no choices".to_string(),
        })?;
    Ok(VisionResponse {
        text: first.message.content,
        prompt_tokens: resp.usage.as_ref().and_then(|u| u.prompt_tokens),
        completion_tokens: resp.usage.as_ref().and_then(|u| u.completion_tokens),
    })
}

impl LlamaCppVisionProvider {
    /// Construct from config. Does not probe the server.
    pub fn new(config: LlamaCppVisionConfig) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_millis(config.timeout_ms))
            .build();
        Self {
            base_url: config.base_url,
            model: RwLock::new(config.model),
            timeout_ms: config.timeout_ms,
            agent,
        }
    }

    /// Current model id this provider is pointed at.
    pub fn model(&self) -> String {
        self.model
            .read()
            .expect("llamacpp-vision model read lock")
            .clone()
    }

    /// Base URL this provider is pointed at.
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// Per-request timeout in milliseconds. Immutable after construction.
    #[allow(dead_code)]
    pub fn timeout_ms(&self) -> u64 {
        self.timeout_ms
    }
}

impl VisionProvider for LlamaCppVisionProvider {
    fn id(&self) -> &str {
        "llamacpp-vision"
    }

    fn label(&self) -> String {
        format!("llama.cpp vision · {} · {}", self.model(), self.base_url)
    }

    fn healthcheck(&self) -> Result<(), L4Error> {
        // llama-server exposes `/health` on recent builds; older builds
        // serve a 200 on `/v1/models`. We try `/health` first and
        // accept anything that did not refuse the connection.
        let url = format!("{}/health", self.base_url.trim_end_matches('/'));
        match self.agent.get(&url).call() {
            Ok(_) => Ok(()),
            Err(e) => Err(L4Error::ProviderUnknown {
                detail: format!("llamacpp-vision healthcheck: {e}"),
            }),
        }
    }

    fn list_models(&self) -> Result<Vec<String>, L4Error> {
        let url = format!("{}/v1/models", self.base_url.trim_end_matches('/'));
        let resp = self
            .agent
            .get(&url)
            .call()
            .map_err(|e| L4Error::ProviderUnknown {
                detail: format!("llamacpp-vision list_models: {e}"),
            })?;
        let json: serde_json::Value =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("llamacpp-vision list_models body: {e}"),
            })?;
        Ok(parse_models_response(&json))
    }

    fn set_model(&self, id: &str) -> Result<(), L4Error> {
        let trimmed = id.trim();
        if trimmed.is_empty() {
            return Err(L4Error::ProviderBadResponse {
                detail: "llamacpp-vision set_model: id must not be empty".to_string(),
            });
        }
        *self
            .model
            .write()
            .expect("llamacpp-vision model write lock") = trimmed.to_string();
        Ok(())
    }

    fn current_model(&self) -> Option<String> {
        Some(self.model())
    }

    fn analyze(&self, req: VisionRequest) -> Result<VisionResponse, L4Error> {
        if req.image_b64.is_empty() {
            return Err(L4Error::ProviderBadResponse {
                detail: "vision request had empty image_b64".to_string(),
            });
        }
        let cue = if req.cue.trim().is_empty() {
            DEFAULT_VISION_CUE.to_string()
        } else {
            req.cue
        };
        let url = format!(
            "{}/v1/chat/completions",
            self.base_url.trim_end_matches('/')
        );
        let model = self.model();
        let payload = build_vision_payload(&model, &cue, &req.image_b64, &req.mime);
        let resp = self
            .agent
            .post(&url)
            .set("content-type", "application/json")
            .send_json(payload)
            .map_err(|e| L4Error::ProviderUnknown {
                detail: format!("llamacpp-vision request: {e}"),
            })?;
        let json: serde_json::Value =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("llamacpp-vision body: {e}"),
            })?;
        parse_vision_response(&json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unset_env() {
        env::remove_var("AETHER_LLAMACPP_VISION_MODEL");
        env::remove_var("AETHER_LLAMACPP_VISION_BASE_URL");
        env::remove_var("AETHER_LLAMACPP_VISION_TIMEOUT_MS");
    }

    static ENV_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn from_env_returns_none_without_model_var() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        assert!(LlamaCppVisionConfig::from_env().is_none());
    }

    #[test]
    fn from_env_picks_up_explicit_model_with_defaults() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_LLAMACPP_VISION_MODEL", "llava-v1.6");
        let cfg = LlamaCppVisionConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.model, "llava-v1.6");
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        assert_eq!(cfg.timeout_ms, DEFAULT_TIMEOUT_MS);
        unset_env();
    }

    #[test]
    fn from_env_rejects_malformed_timeout() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_env();
        env::set_var("AETHER_LLAMACPP_VISION_MODEL", "llava");
        env::set_var("AETHER_LLAMACPP_VISION_TIMEOUT_MS", "garbage");
        let r = LlamaCppVisionConfig::from_env().unwrap();
        assert!(matches!(r, Err(LlamaCppConfigError::InvalidTimeout(_))));
        unset_env();
    }

    #[test]
    fn build_vision_payload_uses_openai_content_blocks() {
        let v = build_vision_payload("llava", "what is this?", "BASE64", "image/jpeg");
        assert_eq!(v.get("model").unwrap(), "llava");
        assert_eq!(v.get("stream").unwrap(), false);
        let msgs = v.get("messages").unwrap().as_array().unwrap();
        let content = msgs[0].get("content").unwrap().as_array().unwrap();
        assert_eq!(content.len(), 2);
        assert_eq!(content[0].get("type").unwrap(), "text");
        assert_eq!(content[0].get("text").unwrap(), "what is this?");
        assert_eq!(content[1].get("type").unwrap(), "image_url");
        let url = content[1]
            .get("image_url")
            .unwrap()
            .get("url")
            .unwrap()
            .as_str()
            .unwrap();
        assert_eq!(url, "data:image/jpeg;base64,BASE64");
    }

    #[test]
    fn parse_vision_response_extracts_text_and_token_counts() {
        let body = serde_json::json!({
            "choices": [{ "message": { "role": "assistant", "content": "I see a cat." } }],
            "usage": { "prompt_tokens": 200, "completion_tokens": 7 }
        });
        let r = parse_vision_response(&body).unwrap();
        assert_eq!(r.text, "I see a cat.");
        assert_eq!(r.prompt_tokens, Some(200));
        assert_eq!(r.completion_tokens, Some(7));
    }

    #[test]
    fn parse_vision_response_handles_missing_usage() {
        let body = serde_json::json!({
            "choices": [{ "message": { "role": "assistant", "content": "ok" } }]
        });
        let r = parse_vision_response(&body).unwrap();
        assert_eq!(r.text, "ok");
        assert!(r.prompt_tokens.is_none());
        assert!(r.completion_tokens.is_none());
    }

    #[test]
    fn parse_vision_response_errors_on_empty_choices() {
        let body = serde_json::json!({ "choices": [] });
        let err = parse_vision_response(&body).unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn parse_vision_response_errors_on_missing_choices() {
        let body = serde_json::json!({ "nope": true });
        let err = parse_vision_response(&body).unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn parse_models_extracts_ids_in_order() {
        let body = serde_json::json!({
            "object": "list",
            "data": [
                {"id": "llava-v1.6", "object": "model"},
                {"id": "minicpm-v", "object": "model"}
            ]
        });
        assert_eq!(
            parse_models_response(&body),
            vec!["llava-v1.6", "minicpm-v"]
        );
    }

    #[test]
    fn parse_models_returns_empty_for_missing_data_key() {
        let body = serde_json::json!({"object": "list"});
        assert!(parse_models_response(&body).is_empty());
    }

    #[test]
    fn parse_models_skips_entries_without_id() {
        let body = serde_json::json!({
            "data": [
                {"id": "good"},
                {"object": "model"},
                {"id": "alsogood"}
            ]
        });
        assert_eq!(parse_models_response(&body), vec!["good", "alsogood"]);
    }

    #[test]
    fn analyze_rejects_empty_image() {
        let cfg = LlamaCppVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava".to_string(),
            timeout_ms: 1_000,
        };
        let p = LlamaCppVisionProvider::new(cfg);
        let err = p
            .analyze(VisionRequest {
                cue: "x".to_string(),
                image_b64: String::new(),
                mime: "image/jpeg".to_string(),
            })
            .unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn set_model_round_trips_and_label_reflects_new_model() {
        let cfg = LlamaCppVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava-v1.6".to_string(),
            timeout_ms: 1_000,
        };
        let p = LlamaCppVisionProvider::new(cfg);
        assert_eq!(p.model(), "llava-v1.6");
        assert_eq!(p.current_model().as_deref(), Some("llava-v1.6"));
        assert!(p.label().contains("llava-v1.6"));

        p.set_model("minicpm-v").expect("set_model");
        assert_eq!(p.model(), "minicpm-v");
        assert_eq!(p.current_model().as_deref(), Some("minicpm-v"));
        assert!(p.label().contains("minicpm-v"));
        assert!(!p.label().contains("llava-v1.6"));
    }

    #[test]
    fn set_model_rejects_empty_id() {
        let cfg = LlamaCppVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava".to_string(),
            timeout_ms: 1_000,
        };
        let p = LlamaCppVisionProvider::new(cfg);
        assert!(p.set_model("").is_err());
        assert!(p.set_model("   ").is_err());
        assert_eq!(p.model(), "llava");
    }

    #[test]
    fn build_vision_payload_uses_current_model_after_swap() {
        let cfg = LlamaCppVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "old".to_string(),
            timeout_ms: 1_000,
        };
        let p = LlamaCppVisionProvider::new(cfg);
        p.set_model("new").unwrap();
        let v = build_vision_payload(&p.model(), "hi", "DATA", "image/jpeg");
        assert_eq!(v.get("model").unwrap(), "new");
    }

    #[test]
    fn provider_id_and_label_are_distinct_from_ollama() {
        let cfg = LlamaCppVisionConfig {
            base_url: "http://127.0.0.1:8080".to_string(),
            model: "llava".to_string(),
            timeout_ms: 1_000,
        };
        let p = LlamaCppVisionProvider::new(cfg);
        assert_eq!(p.id(), "llamacpp-vision");
        assert!(p.label().contains("llama.cpp"));
        assert!(!p.label().contains("Ollama"));
    }
}
