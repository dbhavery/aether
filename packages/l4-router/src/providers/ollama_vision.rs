//! Ollama vision adapter — sibling to the text Ollama provider.
//!
//! Talks to the same `/api/chat` endpoint with the **`images` field**
//! Ollama exposes for vision-capable models (LLaVA, BakLLaVA,
//! gemma3:vision, qwen2.5-vl, etc.). Single-shot only.
//!
//! ## Defaults and config
//!
//! Constructed via [`OllamaVisionConfig::from_env`] which reads:
//! - `AETHER_OLLAMA_VISION_BASE_URL` (defaults to `AETHER_OLLAMA_BASE_URL`,
//!   then to `http://127.0.0.1:11434`),
//! - `AETHER_OLLAMA_VISION_MODEL` — **required** opt-in. If unset,
//!   `from_env` returns `None` so the shell falls back cleanly.
//! - `AETHER_OLLAMA_VISION_TIMEOUT_MS` (default `120_000` — vision
//!   models are slower than text-only models on commodity hardware).
//!
//! ## Wire shape
//!
//! ```json
//! {
//!   "model": "llava:latest",
//!   "messages": [
//!     {
//!       "role": "user",
//!       "content": "describe what you see",
//!       "images": ["<base64-jpeg-without-data-url-prefix>"]
//!     }
//!   ],
//!   "stream": false
//! }
//! ```
//!
//! The `images` field is an array of base64-encoded image bytes
//! (no `data:` URL prefix) per Ollama's documentation.

use std::env;
use std::sync::RwLock;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::error::L4Error;
use crate::providers::ollama::{parse_chat_response_detailed, OllamaConfigError};
use crate::vision::{VisionProvider, VisionRequest, VisionResponse};

const DEFAULT_BASE_URL: &str = "http://127.0.0.1:11434";
const DEFAULT_TIMEOUT_MS: u64 = 120_000;
const DEFAULT_VISION_CUE: &str =
    "Describe what you see in this image in a short, helpful sentence.";

/// Configuration for [`OllamaVisionProvider`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OllamaVisionConfig {
    /// Base URL, e.g. `http://127.0.0.1:11434`.
    pub base_url: String,
    /// Vision-capable model id, e.g. `llava:latest`.
    pub model: String,
    /// Per-request timeout in milliseconds.
    pub timeout_ms: u64,
}

impl OllamaVisionConfig {
    /// Build from env. Returns `None` when the user has not opted in
    /// (the vision-model env var is absent or empty). Returns
    /// `Some(Err(_))` when env opt-in is present but malformed.
    pub fn from_env() -> Option<Result<Self, OllamaConfigError>> {
        let model = env::var("AETHER_OLLAMA_VISION_MODEL").ok()?;
        if model.trim().is_empty() {
            return None;
        }
        let base_url = env::var("AETHER_OLLAMA_VISION_BASE_URL")
            .ok()
            .or_else(|| env::var("AETHER_OLLAMA_BASE_URL").ok())
            .unwrap_or_else(|| DEFAULT_BASE_URL.to_string());
        if base_url.is_empty() {
            return Some(Err(OllamaConfigError::EmptyBaseUrl));
        }
        let timeout_ms = match env::var("AETHER_OLLAMA_VISION_TIMEOUT_MS") {
            Ok(s) => match s.parse::<u64>() {
                Ok(n) => n,
                Err(_) => return Some(Err(OllamaConfigError::InvalidTimeout(s))),
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

/// Vision-aware Ollama adapter.
///
/// Model id is held behind an `RwLock` so the shell's
/// `set_active_vision_model` command can hot-swap the model without
/// rebuilding the provider. Base URL and timeout are immutable after
/// construction — swapping those requires a restart anyway.
pub struct OllamaVisionProvider {
    base_url: String,
    model: RwLock<String>,
    timeout_ms: u64,
    agent: ureq::Agent,
}

#[derive(Debug, Clone, Serialize)]
struct VisionRequestWire<'a> {
    model: &'a str,
    messages: Vec<VisionMessageWire<'a>>,
    stream: bool,
}

#[derive(Debug, Clone, Serialize)]
struct VisionMessageWire<'a> {
    role: &'a str,
    content: &'a str,
    /// Skipped when empty so the same wire shape works for messages
    /// without images on multi-turn vision chats (future work).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    images: Vec<&'a str>,
}

/// Build the JSON payload sent to `/api/chat` for a single-image
/// analysis turn. Pure; exposed for unit tests so the wire shape can
/// be locked without a live daemon.
pub fn build_vision_payload(model: &str, cue: &str, image_b64: &str) -> serde_json::Value {
    let body = VisionRequestWire {
        model,
        messages: vec![VisionMessageWire {
            role: "user",
            content: cue,
            images: vec![image_b64],
        }],
        stream: false,
    };
    serde_json::to_value(&body).expect("VisionRequestWire always serializes")
}

/// Parse the JSON body returned by `/api/tags` into a list of model
/// ids (Ollama's `models[].name`). Pure; exposed for unit tests so
/// the wire shape can be locked without a live daemon. Tolerant of
/// missing fields — we never want a malformed `tags` response to
/// blow up the UI.
pub fn parse_tags_response(json: &serde_json::Value) -> Vec<String> {
    let Some(arr) = json.get("models").and_then(|v| v.as_array()) else {
        return Vec::new();
    };
    arr.iter()
        .filter_map(|m| m.get("name").and_then(|n| n.as_str()))
        .map(|s| s.to_string())
        .collect()
}

/// Pull `(text, prompt_tokens, completion_tokens)` out of the JSON
/// `/api/chat` non-streaming response. Defers to the same parser the
/// text adapter uses so the token-count semantics stay aligned.
pub fn parse_vision_response(json: &serde_json::Value) -> Result<VisionResponse, L4Error> {
    let chat = parse_chat_response_detailed(json)?;
    Ok(VisionResponse {
        text: chat.text,
        prompt_tokens: chat.prompt_tokens,
        completion_tokens: chat.completion_tokens,
    })
}

impl OllamaVisionProvider {
    /// Construct from config. Does not probe the daemon.
    pub fn new(config: OllamaVisionConfig) -> Self {
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
            .expect("ollama-vision model read lock")
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

impl VisionProvider for OllamaVisionProvider {
    fn id(&self) -> &str {
        "ollama-vision"
    }

    fn label(&self) -> String {
        format!("Ollama vision · {} · {}", self.model(), self.base_url)
    }

    fn healthcheck(&self) -> Result<(), L4Error> {
        let url = format!("{}/api/tags", self.base_url.trim_end_matches('/'));
        // We deliberately do not classify the error here — vision boot
        // is best-effort, and the shell already maps an Err here to
        // "fall back to text-only".
        match self.agent.get(&url).call() {
            Ok(_) => Ok(()),
            Err(e) => Err(L4Error::ProviderUnknown {
                detail: format!("ollama-vision healthcheck: {e}"),
            }),
        }
    }

    fn list_models(&self) -> Result<Vec<String>, L4Error> {
        let url = format!("{}/api/tags", self.base_url.trim_end_matches('/'));
        let resp = self
            .agent
            .get(&url)
            .call()
            .map_err(|e| L4Error::ProviderUnknown {
                detail: format!("ollama-vision list_models: {e}"),
            })?;
        let json: serde_json::Value =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("ollama-vision list_models body: {e}"),
            })?;
        Ok(parse_tags_response(&json))
    }

    fn set_model(&self, id: &str) -> Result<(), L4Error> {
        let trimmed = id.trim();
        if trimmed.is_empty() {
            return Err(L4Error::ProviderBadResponse {
                detail: "ollama-vision set_model: id must not be empty".to_string(),
            });
        }
        *self.model.write().expect("ollama-vision model write lock") = trimmed.to_string();
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
        let url = format!("{}/api/chat", self.base_url.trim_end_matches('/'));
        let model = self.model();
        let payload = build_vision_payload(&model, &cue, &req.image_b64);
        let resp = self
            .agent
            .post(&url)
            .set("content-type", "application/json")
            .send_json(payload)
            .map_err(|e| L4Error::ProviderUnknown {
                detail: format!("ollama-vision request: {e}"),
            })?;
        let json: serde_json::Value =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("ollama-vision body: {e}"),
            })?;
        parse_vision_response(&json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn unset_vision_env() {
        env::remove_var("AETHER_OLLAMA_VISION_MODEL");
        env::remove_var("AETHER_OLLAMA_VISION_BASE_URL");
        env::remove_var("AETHER_OLLAMA_VISION_TIMEOUT_MS");
    }

    #[test]
    fn from_env_returns_none_without_vision_model_var() {
        let _g = crate::providers::env_lock();
        unset_vision_env();
        assert!(OllamaVisionConfig::from_env().is_none());
    }

    #[test]
    fn from_env_picks_up_explicit_vision_model_and_defaults() {
        let _g = crate::providers::env_lock();
        unset_vision_env();
        env::set_var("AETHER_OLLAMA_VISION_MODEL", "llava:latest");
        let cfg = OllamaVisionConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.model, "llava:latest");
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        assert_eq!(cfg.timeout_ms, DEFAULT_TIMEOUT_MS);
        unset_vision_env();
    }

    #[test]
    fn from_env_inherits_text_provider_base_url_when_vision_url_unset() {
        let _g = crate::providers::env_lock();
        unset_vision_env();
        env::set_var("AETHER_OLLAMA_VISION_MODEL", "llava");
        env::set_var("AETHER_OLLAMA_BASE_URL", "http://10.0.0.5:11434");
        let cfg = OllamaVisionConfig::from_env().unwrap().unwrap();
        assert_eq!(cfg.base_url, "http://10.0.0.5:11434");
        unset_vision_env();
        env::remove_var("AETHER_OLLAMA_BASE_URL");
    }

    #[test]
    fn from_env_rejects_malformed_timeout() {
        let _g = crate::providers::env_lock();
        unset_vision_env();
        env::set_var("AETHER_OLLAMA_VISION_MODEL", "llava");
        env::set_var("AETHER_OLLAMA_VISION_TIMEOUT_MS", "not-a-number");
        let r = OllamaVisionConfig::from_env().unwrap();
        assert!(matches!(r, Err(OllamaConfigError::InvalidTimeout(_))));
        unset_vision_env();
    }

    #[test]
    fn build_vision_payload_includes_images_array() {
        let v = build_vision_payload("llava", "what is this?", "BASE64DATA");
        let msgs = v.get("messages").unwrap().as_array().unwrap();
        let first = &msgs[0];
        assert_eq!(first.get("role").unwrap(), "user");
        assert_eq!(first.get("content").unwrap(), "what is this?");
        let images = first.get("images").unwrap().as_array().unwrap();
        assert_eq!(images.len(), 1);
        assert_eq!(images[0].as_str().unwrap(), "BASE64DATA");
        assert_eq!(v.get("stream").unwrap(), false);
        assert_eq!(v.get("model").unwrap(), "llava");
    }

    #[test]
    fn parse_vision_response_extracts_text_and_token_counts() {
        let body = serde_json::json!({
            "message": { "role": "assistant", "content": "I see a kettle." },
            "done": true,
            "prompt_eval_count": 1234,
            "eval_count": 56
        });
        let r = parse_vision_response(&body).unwrap();
        assert_eq!(r.text, "I see a kettle.");
        assert_eq!(r.prompt_tokens, Some(1234));
        assert_eq!(r.completion_tokens, Some(56));
    }

    #[test]
    fn parse_vision_response_handles_missing_token_counts() {
        let body = serde_json::json!({
            "message": { "role": "assistant", "content": "ok" },
            "done": true
        });
        let r = parse_vision_response(&body).unwrap();
        assert_eq!(r.text, "ok");
        assert!(r.prompt_tokens.is_none());
        assert!(r.completion_tokens.is_none());
    }

    #[test]
    fn parse_vision_response_errors_on_bad_body() {
        let body = serde_json::json!({"oops": true});
        let err = parse_vision_response(&body).unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn parse_tags_extracts_names_in_order() {
        let body = serde_json::json!({
            "models": [
                {"name": "llava:latest", "modified_at": "x", "size": 1},
                {"name": "gemma3:vision", "modified_at": "y", "size": 2},
                {"name": "qwen2.5-vl", "modified_at": "z", "size": 3}
            ]
        });
        assert_eq!(
            parse_tags_response(&body),
            vec!["llava:latest", "gemma3:vision", "qwen2.5-vl"]
        );
    }

    #[test]
    fn parse_tags_returns_empty_for_missing_models_key() {
        let body = serde_json::json!({"oops": true});
        assert!(parse_tags_response(&body).is_empty());
    }

    #[test]
    fn parse_tags_skips_entries_without_name() {
        let body = serde_json::json!({
            "models": [
                {"name": "good"},
                {"size": 5},
                {"name": "alsogood"}
            ]
        });
        assert_eq!(parse_tags_response(&body), vec!["good", "alsogood"]);
    }

    #[test]
    fn set_model_round_trips_and_label_reflects_new_model() {
        let cfg = OllamaVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava:latest".to_string(),
            timeout_ms: 1_000,
        };
        let p = OllamaVisionProvider::new(cfg);
        assert_eq!(p.model(), "llava:latest");
        assert_eq!(p.current_model().as_deref(), Some("llava:latest"));
        assert!(p.label().contains("llava:latest"));

        p.set_model("gemma3:vision").expect("set_model");
        assert_eq!(p.model(), "gemma3:vision");
        assert_eq!(p.current_model().as_deref(), Some("gemma3:vision"));
        assert!(p.label().contains("gemma3:vision"));
        assert!(!p.label().contains("llava:latest"));
    }

    #[test]
    fn set_model_rejects_empty_id() {
        let cfg = OllamaVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava".to_string(),
            timeout_ms: 1_000,
        };
        let p = OllamaVisionProvider::new(cfg);
        assert!(p.set_model("").is_err());
        assert!(p.set_model("   ").is_err());
        // model unchanged after a rejected swap
        assert_eq!(p.model(), "llava");
    }

    #[test]
    fn build_vision_payload_uses_current_model_after_swap() {
        let cfg = OllamaVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "old".to_string(),
            timeout_ms: 1_000,
        };
        let p = OllamaVisionProvider::new(cfg);
        p.set_model("new").unwrap();
        let v = build_vision_payload(&p.model(), "hi", "DATA");
        assert_eq!(v.get("model").unwrap(), "new");
    }

    #[test]
    fn analyze_rejects_empty_image() {
        let cfg = OllamaVisionConfig {
            base_url: DEFAULT_BASE_URL.to_string(),
            model: "llava".to_string(),
            timeout_ms: 1_000,
        };
        let p = OllamaVisionProvider::new(cfg);
        let err = p
            .analyze(VisionRequest {
                cue: "x".to_string(),
                image_b64: String::new(),
                mime: "image/jpeg".to_string(),
            })
            .unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }
}
