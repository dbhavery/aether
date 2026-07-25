//! Wave L4.1 — Ollama provider adapter (feature-gated).
//!
//! Connects Aether's routing path to a local Ollama daemon
//! (`ollama serve`, default `http://127.0.0.1:11434`) via its `/api/chat`
//! endpoint. First real-model provider in the router.
//!
//! ## Scope
//!
//! - one provider (Ollama),
//! - blocking single-shot request/response (no streaming yet),
//! - no tool-call dispatch (tools remain Wave-5+ work),
//! - no hard requirement that the daemon be running — callers that build
//!   the adapter with [`OllamaProvider::new`] and find that
//!   [`OllamaProvider::healthcheck`] fails can fall back to a safe stub.
//!
//! ## Defaults and config
//!
//! Constructed via [`OllamaConfig::from_env`] which reads:
//! - `AETHER_OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`),
//! - `AETHER_OLLAMA_MODEL` (default `gemma4:e4b` per ADR-0003 — pin the
//!   known-good variant; 31B Dense has an unresolved FlashAttention hang
//!   and `gemma4:latest` resolution can drift),
//! - `AETHER_OLLAMA_TIMEOUT_MS` (default `60_000`).
//!
//! Opt-in at build time via the `ollama-provider` Cargo feature; opt-in at
//! runtime by setting an env var (callers typically just check for
//! `AETHER_OLLAMA_MODEL`).

use std::env;
use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::error::L4Error;
use crate::router::{
    ModelRouter, ProviderAdapter, ProviderId, RouterTier, ToolCall, ToolError, ToolResult,
};
use aether_l5_policy::Decision;

const DEFAULT_BASE_URL: &str = "http://127.0.0.1:11434";
const DEFAULT_MODEL: &str = "gemma4:e4b";
const DEFAULT_TIMEOUT_MS: u64 = 60_000;

/// Configuration for [`OllamaProvider`]. All fields are required at
/// construction; [`OllamaConfig::from_env`] fills in sensible defaults.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OllamaConfig {
    /// Base URL, e.g. `http://127.0.0.1:11434`.
    pub base_url: String,
    /// Model id, e.g. `llama3`.
    pub model: String,
    /// Per-request timeout in milliseconds.
    pub timeout_ms: u64,
}

impl OllamaConfig {
    /// Build a config from environment variables, applying defaults for any
    /// unset field. Invalid numeric values surface as
    /// [`OllamaConfigError::InvalidTimeout`].
    pub fn from_env() -> Result<Self, OllamaConfigError> {
        let base_url =
            env::var("AETHER_OLLAMA_BASE_URL").unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let model = env::var("AETHER_OLLAMA_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let timeout_ms = match env::var("AETHER_OLLAMA_TIMEOUT_MS") {
            Ok(s) => s
                .parse::<u64>()
                .map_err(|_| OllamaConfigError::InvalidTimeout(s))?,
            Err(_) => DEFAULT_TIMEOUT_MS,
        };
        if base_url.is_empty() {
            return Err(OllamaConfigError::EmptyBaseUrl);
        }
        if model.is_empty() {
            return Err(OllamaConfigError::EmptyModel);
        }
        Ok(Self {
            base_url,
            model,
            timeout_ms,
        })
    }

    /// Whether env indicates the user explicitly opted in. A caller that
    /// wants "use Ollama only if the user asked for it" can key on
    /// `AETHER_OLLAMA_MODEL` being present.
    pub fn env_opts_in() -> bool {
        env::var("AETHER_OLLAMA_MODEL").is_ok() || env::var("AETHER_OLLAMA_BASE_URL").is_ok()
    }
}

/// Errors that can arise when reading [`OllamaConfig`] from env.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum OllamaConfigError {
    /// `AETHER_OLLAMA_TIMEOUT_MS` did not parse as `u64`.
    #[error("invalid AETHER_OLLAMA_TIMEOUT_MS: {0}")]
    InvalidTimeout(String),
    /// Base URL set to empty string explicitly.
    #[error("AETHER_OLLAMA_BASE_URL must not be empty")]
    EmptyBaseUrl,
    /// Model set to empty string explicitly.
    #[error("AETHER_OLLAMA_MODEL must not be empty")]
    EmptyModel,
}

/// Role tag for a `/api/chat` message. Mirrors Ollama's JSON enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MessageRole {
    /// Persona / instruction-level context the model should treat as
    /// background rules, not a prior turn.
    System,
    /// User-authored turn content.
    User,
    /// Prior assistant-authored reply.
    Assistant,
}

impl MessageRole {
    /// Ollama wire-format role name.
    pub fn wire(self) -> &'static str {
        match self {
            MessageRole::System => "system",
            MessageRole::User => "user",
            MessageRole::Assistant => "assistant",
        }
    }
}

/// A single role-tagged message for [`OllamaProvider::chat_with_messages`].
/// Owned so callers can build a `Vec<ChatMessage>` without lifetime gymnastics.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChatMessage {
    /// Speaker role.
    pub role: MessageRole,
    /// Message content.
    pub content: String,
}

impl ChatMessage {
    /// User-role convenience constructor.
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::User,
            content: content.into(),
        }
    }
    /// Assistant-role convenience constructor.
    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::Assistant,
            content: content.into(),
        }
    }
    /// System-role convenience constructor.
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: MessageRole::System,
            content: content.into(),
        }
    }
}

/// Wire shape for `/api/chat` request body. Kept internal; callers pass
/// plain strings / messages through the public methods.
#[derive(Debug, Clone, Serialize)]
struct ChatRequest<'a> {
    model: &'a str,
    messages: Vec<ChatMessageWire<'a>>,
    stream: bool,
    options: ChatOptions,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct ChatMessageWire<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Debug, Clone, Serialize, Default)]
struct ChatOptions {
    /// Keep `num_predict` generous; small models stop short of this.
    num_predict: Option<i32>,
}

/// Wire shape for `/api/chat` response body (non-streaming). Only the
/// fields the adapter consumes are declared.
#[derive(Debug, Clone, Deserialize)]
struct ChatResponse {
    message: OwnedChatMessage,
    #[serde(default)]
    done: bool,
    /// Tokens the model produced (completion side). Optional — older
    /// Ollama versions and some models omit it.
    #[serde(default)]
    eval_count: Option<u32>,
    /// Tokens on the prompt side (system + history + user). Optional.
    #[serde(default)]
    prompt_eval_count: Option<u32>,
}

#[derive(Debug, Clone, Deserialize)]
struct OwnedChatMessage {
    #[allow(dead_code)]
    role: String,
    content: String,
}

/// Completion returned by [`OllamaProvider::chat_with_messages_detailed`].
/// Carries the assistant text plus optional token counts parsed from the
/// `/api/chat` response body. Either count can be `None` when the daemon
/// didn't report it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChatCompletion {
    /// Assistant text (same string [`OllamaProvider::chat_with_messages`]
    /// returns today).
    pub text: String,
    /// Prompt-side token count if the daemon reported `prompt_eval_count`.
    pub prompt_tokens: Option<u32>,
    /// Completion-side token count if the daemon reported `eval_count`.
    pub completion_tokens: Option<u32>,
}

/// Build the JSON payload the provider sends to `/api/chat` for a single
/// user prompt. Pure; exposed for unit tests and for callers that want to
/// inspect the wire shape.
///
/// Back-compat path: callers that still concat a rendered transcript into
/// one prompt string (via the shell's `MemoryAwareRouter`) land here.
/// Role-tagged callers should use [`build_chat_payload_messages`].
pub fn build_chat_payload(model: &str, prompt: &str) -> serde_json::Value {
    let body = ChatRequest {
        model,
        messages: vec![ChatMessageWire {
            role: "user",
            content: prompt,
        }],
        stream: false,
        options: ChatOptions {
            num_predict: Some(512),
        },
    };
    serde_json::to_value(&body).expect("ChatRequest always serializes")
}

/// Build the JSON payload the provider sends to `/api/chat` from an
/// already-split message history. Pure; exposed for unit tests.
pub fn build_chat_payload_messages(model: &str, messages: &[ChatMessage]) -> serde_json::Value {
    let wire: Vec<ChatMessageWire<'_>> = messages
        .iter()
        .map(|m| ChatMessageWire {
            role: m.role.wire(),
            content: m.content.as_str(),
        })
        .collect();
    let body = ChatRequest {
        model,
        messages: wire,
        stream: false,
        options: ChatOptions {
            num_predict: Some(512),
        },
    };
    serde_json::to_value(&body).expect("ChatRequest always serializes")
}

/// Parse the JSON body returned by `/api/chat` (non-streaming) into the
/// assistant content string. Exposed for unit tests.
pub fn parse_chat_response(json: &serde_json::Value) -> Result<String, L4Error> {
    parse_chat_response_detailed(json).map(|c| c.text)
}

/// Parse the JSON body returned by `/api/chat` (non-streaming) into a
/// [`ChatCompletion`] that preserves the token counts Ollama reports
/// (`eval_count`, `prompt_eval_count`). Either field may be `None` if the
/// daemon omitted it. Exposed for unit tests.
pub fn parse_chat_response_detailed(json: &serde_json::Value) -> Result<ChatCompletion, L4Error> {
    let resp: ChatResponse =
        serde_json::from_value(json.clone()).map_err(|e| L4Error::ProviderBadResponse {
            detail: format!("ollama: invalid response: {e}"),
        })?;
    if !resp.done {
        // Non-fatal — some daemon versions omit `done` on terminal chunk.
        // We still take the content we got.
    }
    Ok(ChatCompletion {
        text: resp.message.content,
        prompt_tokens: resp.prompt_eval_count,
        completion_tokens: resp.eval_count,
    })
}

/// Classify a `ureq::Error` into the right typed `L4Error` variant so the
/// UI can show actionable language ("Ollama isn't running — start it with
/// `ollama serve`", "That model isn't installed", etc.) instead of a raw
/// transport string.
///
/// `model` is the model id the caller asked for — used only when the
/// classification lands on `ProviderModelNotFound`.
fn classify_ureq_error(err: ureq::Error, model: &str) -> L4Error {
    match err {
        ureq::Error::Status(status, resp) => {
            let body = resp.into_string().unwrap_or_default();
            let body_lc = body.to_ascii_lowercase();
            // Ollama's /api/chat returns 404 with a body like
            // `{"error":"model 'foo' not found, try pulling it first"}`.
            // Detect that shape rather than relying on the raw status.
            if status == 404 && (body_lc.contains("model") || body_lc.contains("not found")) {
                L4Error::ProviderModelNotFound {
                    model: model.to_string(),
                    detail: body,
                }
            } else {
                L4Error::ProviderUnknown {
                    detail: format!("HTTP {status}: {body}"),
                }
            }
        }
        ureq::Error::Transport(t) => {
            use ureq::ErrorKind;
            let msg = t.to_string();
            match t.kind() {
                ErrorKind::ConnectionFailed => L4Error::ProviderNotRunning { detail: msg },
                ErrorKind::Dns => L4Error::ProviderNotRunning { detail: msg },
                ErrorKind::Io => {
                    // ureq wraps timeouts under Io; the inner io::Error
                    // message is the only signal we have without
                    // reaching into nightly `.source()` typing.
                    let lc = msg.to_ascii_lowercase();
                    if lc.contains("timed out") || lc.contains("timeout") {
                        L4Error::ProviderTimeout { detail: msg }
                    } else {
                        L4Error::ProviderUnknown { detail: msg }
                    }
                }
                _ => L4Error::ProviderUnknown { detail: msg },
            }
        }
    }
}

/// Blocking Ollama provider.
pub struct OllamaProvider {
    config: OllamaConfig,
    agent: ureq::Agent,
}

impl OllamaProvider {
    /// Construct a provider from config. Does not probe the daemon;
    /// callers should call [`OllamaProvider::healthcheck`] first if they
    /// want to verify reachability.
    pub fn new(config: OllamaConfig) -> Self {
        let agent = ureq::AgentBuilder::new()
            .timeout(Duration::from_millis(config.timeout_ms))
            .build();
        Self { config, agent }
    }

    /// Model id this provider is pointed at.
    pub fn model(&self) -> &str {
        &self.config.model
    }

    /// Base URL this provider is pointed at.
    pub fn base_url(&self) -> &str {
        &self.config.base_url
    }

    /// Probe `/api/tags`. Returns `Ok(())` on HTTP 200 reachable; transport
    /// errors are classified into typed `L4Error` variants so the UI can
    /// tell "not running" from "timed out" from "unknown failure".
    pub fn healthcheck(&self) -> Result<(), L4Error> {
        let url = format!("{}/api/tags", self.config.base_url.trim_end_matches('/'));
        self.agent
            .get(&url)
            .call()
            .map_err(|e| classify_ureq_error(e, &self.config.model))?;
        Ok(())
    }

    /// Send a single prompt to `/api/chat` and return the assistant text.
    /// Back-compat single-prompt path; delegates to
    /// [`OllamaProvider::chat_with_messages`] with one `user` message.
    pub fn chat(&self, prompt: &str) -> Result<String, L4Error> {
        self.chat_with_messages(&[ChatMessage::user(prompt.to_string())])
    }

    /// Send a role-tagged message history to `/api/chat` and return the
    /// assistant text. Preferred over [`OllamaProvider::chat`] when the
    /// caller has a real transcript — Ollama's `/api/chat` endpoint uses
    /// the message array for its chat template, which is a better fit
    /// for instruction-tuned models than one concatenated prompt string.
    pub fn chat_with_messages(&self, messages: &[ChatMessage]) -> Result<String, L4Error> {
        self.chat_with_messages_detailed(messages).map(|c| c.text)
    }

    /// Role-tagged variant that preserves token counts. See
    /// [`OllamaProvider::chat_with_messages`] for the back-compat path that
    /// drops the counts.
    pub fn chat_with_messages_detailed(
        &self,
        messages: &[ChatMessage],
    ) -> Result<ChatCompletion, L4Error> {
        let url = format!("{}/api/chat", self.config.base_url.trim_end_matches('/'));
        let payload = build_chat_payload_messages(&self.config.model, messages);
        let resp = self
            .agent
            .post(&url)
            .set("content-type", "application/json")
            .send_json(payload)
            .map_err(|e| classify_ureq_error(e, &self.config.model))?;
        let json: serde_json::Value =
            resp.into_json().map_err(|e| L4Error::ProviderBadResponse {
                detail: format!("ollama body: {e}"),
            })?;
        parse_chat_response_detailed(&json)
    }
}

impl ProviderAdapter for OllamaProvider {
    fn id(&self) -> ProviderId {
        ProviderId("ollama".to_string())
    }

    fn healthcheck(&self) -> Result<(), L4Error> {
        OllamaProvider::healthcheck(self)
    }

    fn complete(&self, prompt: &str, _tier: RouterTier) -> Result<String, L4Error> {
        // Tier is recorded by the router layer above; Ollama itself is a
        // single-model backend for this wave.
        self.chat(prompt)
    }
}

impl ModelRouter for OllamaProvider {
    fn route(&self, _tier: RouterTier, prompt: &str) -> Result<String, L4Error> {
        self.chat(prompt)
    }

    fn execute_tool(&self, _call: &ToolCall) -> Result<ToolResult, ToolError> {
        Err(ToolError::Internal(String::from(
            "OllamaProvider does not execute tool calls yet (Wave 5+)",
        )))
    }

    fn on_policy_decision(&self, _decision: &Decision) -> Result<(), L4Error> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::MutexGuard;

    /// Unconditionally set the Ollama-related env vars for a test. Cleans
    /// up on drop. Holds the crate-wide env lock
    /// (`crate::providers::env_lock`) for the whole scope so no other
    /// env-mutating test — in this module or in siblings like
    /// `ollama_vision` — can interleave with us.
    struct EnvGuard {
        _lock: MutexGuard<'static, ()>,
    }

    impl EnvGuard {
        fn fresh(base_url: Option<&str>, model: Option<&str>, timeout_ms: Option<&str>) -> Self {
            let lock = crate::providers::env_lock();
            for (k, v) in [
                ("AETHER_OLLAMA_BASE_URL", base_url),
                ("AETHER_OLLAMA_MODEL", model),
                ("AETHER_OLLAMA_TIMEOUT_MS", timeout_ms),
            ] {
                match v {
                    Some(val) => env::set_var(k, val),
                    None => env::remove_var(k),
                }
            }
            EnvGuard { _lock: lock }
        }
    }

    impl Drop for EnvGuard {
        fn drop(&mut self) {
            for k in [
                "AETHER_OLLAMA_BASE_URL",
                "AETHER_OLLAMA_MODEL",
                "AETHER_OLLAMA_TIMEOUT_MS",
            ] {
                env::remove_var(k);
            }
        }
    }

    #[test]
    fn from_env_uses_defaults_when_vars_unset() {
        let _g = EnvGuard::fresh(None, None, None);
        let cfg = OllamaConfig::from_env().unwrap();
        assert_eq!(cfg.base_url, DEFAULT_BASE_URL);
        assert_eq!(cfg.model, DEFAULT_MODEL);
        assert_eq!(cfg.timeout_ms, DEFAULT_TIMEOUT_MS);
    }

    #[test]
    fn from_env_reads_explicit_values() {
        let _g = EnvGuard::fresh(Some("http://10.0.0.1:7777"), Some("phi3"), Some("5000"));
        let cfg = OllamaConfig::from_env().unwrap();
        assert_eq!(cfg.base_url, "http://10.0.0.1:7777");
        assert_eq!(cfg.model, "phi3");
        assert_eq!(cfg.timeout_ms, 5_000);
    }

    #[test]
    fn from_env_rejects_non_numeric_timeout() {
        let _g = EnvGuard::fresh(None, None, Some("lots"));
        assert!(matches!(
            OllamaConfig::from_env(),
            Err(OllamaConfigError::InvalidTimeout(_))
        ));
    }

    #[test]
    fn from_env_rejects_empty_base_url() {
        let _g = EnvGuard::fresh(Some(""), None, None);
        assert_eq!(
            OllamaConfig::from_env(),
            Err(OllamaConfigError::EmptyBaseUrl)
        );
    }

    #[test]
    fn env_opts_in_detects_either_var() {
        let _g = EnvGuard::fresh(None, None, None);
        assert!(!OllamaConfig::env_opts_in());
        drop(_g);
        let _g2 = EnvGuard::fresh(None, Some("llama3"), None);
        assert!(OllamaConfig::env_opts_in());
    }

    #[test]
    fn build_chat_payload_shapes_single_user_message() {
        let v = build_chat_payload("llama3", "hello there");
        assert_eq!(v["model"], "llama3");
        assert_eq!(v["stream"], false);
        assert_eq!(v["messages"].as_array().unwrap().len(), 1);
        assert_eq!(v["messages"][0]["role"], "user");
        assert_eq!(v["messages"][0]["content"], "hello there");
        assert_eq!(v["options"]["num_predict"], 512);
    }

    #[test]
    fn parse_chat_response_extracts_assistant_content() {
        let raw = serde_json::json!({
            "model": "llama3",
            "message": { "role": "assistant", "content": "why yes I am" },
            "done": true
        });
        assert_eq!(parse_chat_response(&raw).unwrap(), "why yes I am");
    }

    #[test]
    fn parse_chat_response_tolerates_missing_done_flag() {
        let raw = serde_json::json!({
            "model": "llama3",
            "message": { "role": "assistant", "content": "partial" }
        });
        assert_eq!(parse_chat_response(&raw).unwrap(), "partial");
    }

    #[test]
    fn parse_chat_response_errors_on_malformed_body() {
        let raw = serde_json::json!({ "not": "what we expected" });
        assert!(parse_chat_response(&raw).is_err());
    }

    #[test]
    fn parse_chat_response_detailed_extracts_token_counts() {
        let raw = serde_json::json!({
            "model": "llama3",
            "message": { "role": "assistant", "content": "hi" },
            "done": true,
            "prompt_eval_count": 12,
            "eval_count": 34,
        });
        let c = parse_chat_response_detailed(&raw).unwrap();
        assert_eq!(c.text, "hi");
        assert_eq!(c.prompt_tokens, Some(12));
        assert_eq!(c.completion_tokens, Some(34));
    }

    #[test]
    fn parse_chat_response_detailed_tolerates_missing_token_counts() {
        let raw = serde_json::json!({
            "model": "llama3",
            "message": { "role": "assistant", "content": "hi" },
            "done": true,
        });
        let c = parse_chat_response_detailed(&raw).unwrap();
        assert_eq!(c.prompt_tokens, None);
        assert_eq!(c.completion_tokens, None);
    }

    #[test]
    fn chat_with_messages_detailed_captures_counts_from_mock() {
        let response = r#"{"model":"llama3","message":{"role":"assistant","content":"ok"},"done":true,"prompt_eval_count":7,"eval_count":3}"#.to_string();
        let (base_url, handle) = spawn_mock_ollama(response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 3_000,
        });
        let completion = provider
            .chat_with_messages_detailed(&[ChatMessage::user("hi")])
            .expect("chat_with_messages_detailed ok");
        assert_eq!(completion.text, "ok");
        assert_eq!(completion.prompt_tokens, Some(7));
        assert_eq!(completion.completion_tokens, Some(3));
        let _ = handle.join();
    }

    // --- Mock-HTTP integration tests ------------------------------------
    //
    // We spin up a tiny single-shot HTTP/1.1 responder on an ephemeral
    // port using only `std::net::TcpListener`. No new dev-deps, no real
    // network — 127.0.0.1 only, timeouts short, each test owns its port.
    //
    // The responder reads request bytes until it has both the full header
    // block (terminated by `\r\n\r\n`) and the `Content-Length` bytes of
    // body, then writes a canned HTTP/1.1 response.

    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::thread;

    /// Captured request shape the responder hands back to the test thread.
    struct CapturedRequest {
        method: String,
        path: String,
        headers: Vec<(String, String)>,
        body: String,
    }

    /// Start a single-shot HTTP/1.1 responder on an ephemeral port.
    /// Returns `(base_url, join_handle)`. The spawned thread accepts
    /// exactly one connection, reads one request, and writes
    /// `response_body` as an HTTP/1.1 200 with JSON content-type. The join
    /// handle yields the captured request for assertions.
    fn spawn_mock_ollama(response_body: String) -> (String, thread::JoinHandle<CapturedRequest>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind 127.0.0.1:0 for mock ollama");
        let addr = listener.local_addr().expect("listener local_addr");
        let base_url = format!("http://{}", addr);

        let handle = thread::spawn(move || {
            let (mut stream, _peer) = listener.accept().expect("mock accept");
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .expect("read timeout");
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .expect("write timeout");

            // Read until headers complete, then drain Content-Length bytes.
            let mut buf = Vec::with_capacity(1024);
            let mut tmp = [0u8; 512];
            let header_end: usize;
            loop {
                let n = stream.read(&mut tmp).expect("mock read");
                if n == 0 {
                    panic!("mock peer closed before headers complete");
                }
                buf.extend_from_slice(&tmp[..n]);
                if let Some(idx) = find_subslice(&buf, b"\r\n\r\n") {
                    header_end = idx + 4;
                    break;
                }
            }
            let header_bytes = &buf[..header_end - 4];
            let header_text = std::str::from_utf8(header_bytes).expect("mock headers utf8");
            let mut lines = header_text.split("\r\n");
            let request_line = lines.next().unwrap_or("");
            let mut parts = request_line.splitn(3, ' ');
            let method = parts.next().unwrap_or("").to_string();
            let path = parts.next().unwrap_or("").to_string();

            let mut headers: Vec<(String, String)> = Vec::new();
            let mut content_length: usize = 0;
            for line in lines {
                if let Some((k, v)) = line.split_once(':') {
                    let k = k.trim().to_string();
                    let v = v.trim().to_string();
                    if k.eq_ignore_ascii_case("content-length") {
                        content_length = v.parse::<usize>().unwrap_or(0);
                    }
                    headers.push((k, v));
                }
            }

            let mut body = buf[header_end..].to_vec();
            while body.len() < content_length {
                let n = stream.read(&mut tmp).expect("mock body read");
                if n == 0 {
                    break;
                }
                body.extend_from_slice(&tmp[..n]);
            }
            body.truncate(content_length);
            let body_str = String::from_utf8(body).expect("mock body utf8");

            let response = format!(
                "HTTP/1.1 200 OK\r\n\
                 Content-Type: application/json\r\n\
                 Content-Length: {}\r\n\
                 Connection: close\r\n\
                 \r\n{}",
                response_body.len(),
                response_body
            );
            stream
                .write_all(response.as_bytes())
                .expect("mock write response");
            stream.flush().ok();
            // Dropping `stream` closes the connection.

            CapturedRequest {
                method,
                path,
                headers,
                body: body_str,
            }
        });

        (base_url, handle)
    }

    fn find_subslice(hay: &[u8], needle: &[u8]) -> Option<usize> {
        if needle.is_empty() || hay.len() < needle.len() {
            return None;
        }
        (0..=hay.len() - needle.len()).find(|&i| &hay[i..i + needle.len()] == needle)
    }

    #[test]
    fn build_chat_payload_messages_preserves_role_order() {
        let msgs = vec![
            ChatMessage::system("You are Aurora."),
            ChatMessage::user("hello"),
            ChatMessage::assistant("hi there"),
            ChatMessage::user("how are you"),
        ];
        let v = build_chat_payload_messages("llama3", &msgs);
        let arr = v["messages"].as_array().expect("messages array");
        assert_eq!(arr.len(), 4);
        assert_eq!(arr[0]["role"], "system");
        assert_eq!(arr[0]["content"], "You are Aurora.");
        assert_eq!(arr[1]["role"], "user");
        assert_eq!(arr[1]["content"], "hello");
        assert_eq!(arr[2]["role"], "assistant");
        assert_eq!(arr[2]["content"], "hi there");
        assert_eq!(arr[3]["role"], "user");
        assert_eq!(arr[3]["content"], "how are you");
        assert_eq!(v["model"], "llama3");
        assert_eq!(v["stream"], false);
    }

    #[test]
    fn chat_delegates_to_chat_with_messages_single_user() {
        // Proves the back-compat path still hits the wire as one `user`
        // message, not as something the old payload helper emitted.
        let response =
            r#"{"model":"llama3","message":{"role":"assistant","content":"ok"},"done":true}"#
                .to_string();
        let (base_url, handle) = spawn_mock_ollama(response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 3_000,
        });
        let reply = provider.chat("hi").expect("chat ok");
        assert_eq!(reply, "ok");

        let req = handle.join().expect("mock join");
        let sent: serde_json::Value = serde_json::from_str(&req.body).expect("JSON");
        let arr = sent["messages"].as_array().unwrap();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["role"], "user");
        assert_eq!(arr[0]["content"], "hi");
    }

    #[test]
    fn chat_with_messages_round_trips_system_user_assistant_user() {
        let response = r#"{"model":"llama3","message":{"role":"assistant","content":"fine thanks"},"done":true}"#
            .to_string();
        let (base_url, handle) = spawn_mock_ollama(response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 3_000,
        });
        let msgs = vec![
            ChatMessage::system("You are Aurora."),
            ChatMessage::user("hello"),
            ChatMessage::assistant("hi there"),
            ChatMessage::user("how are you"),
        ];
        let reply = provider
            .chat_with_messages(&msgs)
            .expect("chat_with_messages ok");
        assert_eq!(reply, "fine thanks");

        let req = handle.join().expect("mock join");
        assert_eq!(req.method, "POST");
        assert_eq!(req.path, "/api/chat");
        let sent: serde_json::Value = serde_json::from_str(&req.body).expect("JSON");
        let arr = sent["messages"].as_array().unwrap();
        assert_eq!(arr.len(), 4);
        assert_eq!(arr[0]["role"], "system");
        assert_eq!(arr[3]["role"], "user");
        assert_eq!(arr[3]["content"], "how are you");
    }

    #[test]
    fn chat_round_trips_through_mock_ollama() {
        let response =
            r#"{"model":"llama3","message":{"role":"assistant","content":"pong"},"done":true}"#
                .to_string();
        let (base_url, handle) = spawn_mock_ollama(response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 3_000,
        });
        let reply = provider.chat("ping").expect("chat ok");
        assert_eq!(reply, "pong");

        let req = handle.join().expect("mock thread join");
        assert_eq!(req.method, "POST");
        assert_eq!(req.path, "/api/chat");

        let has_json_ct = req
            .headers
            .iter()
            .any(|(k, v)| k.eq_ignore_ascii_case("content-type") && v.contains("application/json"));
        assert!(has_json_ct, "expected application/json Content-Type");

        let sent: serde_json::Value = serde_json::from_str(&req.body).expect("request body JSON");
        assert_eq!(sent["model"], "llama3");
        assert_eq!(sent["stream"], false);
        assert_eq!(sent["messages"].as_array().unwrap().len(), 1);
        assert_eq!(sent["messages"][0]["role"], "user");
        assert_eq!(sent["messages"][0]["content"], "ping");
    }

    #[test]
    fn chat_surfaces_provider_error_on_malformed_response_body() {
        let response = r#"{"not":"what we expected"}"#.to_string();
        let (base_url, handle) = spawn_mock_ollama(response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 3_000,
        });
        let err = provider
            .chat("ping")
            .expect_err("malformed body should fail");
        let _ = handle.join();
        match err {
            L4Error::ProviderBadResponse { detail } => assert!(
                detail.contains("invalid response") || detail.contains("missing field"),
                "unexpected error detail: {detail}"
            ),
            other => panic!("expected ProviderBadResponse, got {other:?}"),
        }
    }

    #[test]
    fn chat_classifies_connection_refused_as_not_running() {
        // Bind, capture the addr, then drop the listener so the port is
        // vacant. The provider will see connection-refused (Windows:
        // WSAECONNREFUSED, Linux: ECONNREFUSED).
        let port = {
            let l = TcpListener::bind("127.0.0.1:0").expect("bind for port grab");
            l.local_addr().expect("addr").port()
        };
        let base_url = format!("http://127.0.0.1:{}", port);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama3".into(),
            timeout_ms: 2_000,
        });
        let err = provider
            .chat("ping")
            .expect_err("connection should be refused");
        match err {
            L4Error::ProviderNotRunning { .. } => {}
            other => panic!("expected ProviderNotRunning, got {other:?}"),
        }
    }

    #[test]
    fn chat_classifies_404_model_not_found() {
        let response = r#"{"error":"model 'llama9' not found, try pulling it first"}"#.to_string();
        let (base_url, handle) = spawn_mock_ollama_with_status(404, "application/json", response);

        let provider = OllamaProvider::new(OllamaConfig {
            base_url,
            model: "llama9".into(),
            timeout_ms: 2_000,
        });
        let err = provider.chat("ping").expect_err("404 should fail");
        let _ = handle.join();
        match err {
            L4Error::ProviderModelNotFound { model, detail } => {
                assert_eq!(model, "llama9");
                assert!(detail.contains("not found"));
            }
            other => panic!("expected ProviderModelNotFound, got {other:?}"),
        }
    }

    /// Variant of `spawn_mock_ollama` that lets the caller pick the status
    /// line and content type. Still single-shot.
    fn spawn_mock_ollama_with_status(
        status: u16,
        content_type: &str,
        response_body: String,
    ) -> (String, thread::JoinHandle<CapturedRequest>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind 127.0.0.1:0 for mock ollama");
        let addr = listener.local_addr().expect("listener local_addr");
        let base_url = format!("http://{}", addr);
        let content_type = content_type.to_string();

        let handle = thread::spawn(move || {
            let (mut stream, _peer) = listener.accept().expect("mock accept");
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .expect("read timeout");
            stream
                .set_write_timeout(Some(Duration::from_secs(2)))
                .expect("write timeout");

            let mut buf = Vec::with_capacity(1024);
            let mut tmp = [0u8; 512];
            let header_end: usize;
            loop {
                let n = stream.read(&mut tmp).expect("mock read");
                if n == 0 {
                    panic!("mock peer closed before headers complete");
                }
                buf.extend_from_slice(&tmp[..n]);
                if let Some(idx) = find_subslice(&buf, b"\r\n\r\n") {
                    header_end = idx + 4;
                    break;
                }
            }
            let header_bytes = &buf[..header_end - 4];
            let header_text = std::str::from_utf8(header_bytes).expect("mock headers utf8");
            let mut lines = header_text.split("\r\n");
            let request_line = lines.next().unwrap_or("");
            let mut parts = request_line.splitn(3, ' ');
            let method = parts.next().unwrap_or("").to_string();
            let path = parts.next().unwrap_or("").to_string();

            let mut headers: Vec<(String, String)> = Vec::new();
            let mut content_length: usize = 0;
            for line in lines {
                if let Some((k, v)) = line.split_once(':') {
                    let k = k.trim().to_string();
                    let v = v.trim().to_string();
                    if k.eq_ignore_ascii_case("content-length") {
                        content_length = v.parse::<usize>().unwrap_or(0);
                    }
                    headers.push((k, v));
                }
            }

            let mut body = buf[header_end..].to_vec();
            while body.len() < content_length {
                let n = stream.read(&mut tmp).expect("mock body read");
                if n == 0 {
                    break;
                }
                body.extend_from_slice(&tmp[..n]);
            }
            body.truncate(content_length);
            let body_str = String::from_utf8(body).expect("mock body utf8");

            let reason = match status {
                200 => "OK",
                404 => "Not Found",
                500 => "Internal Server Error",
                _ => "Status",
            };
            let response = format!(
                "HTTP/1.1 {status} {reason}\r\n\
                 Content-Type: {content_type}\r\n\
                 Content-Length: {}\r\n\
                 Connection: close\r\n\
                 \r\n{}",
                response_body.len(),
                response_body
            );
            stream
                .write_all(response.as_bytes())
                .expect("mock write response");
            stream.flush().ok();

            CapturedRequest {
                method,
                path,
                headers,
                body: body_str,
            }
        });

        (base_url, handle)
    }

    #[test]
    fn provider_id_is_stable() {
        let p = OllamaProvider::new(OllamaConfig {
            base_url: "http://127.0.0.1:11434".into(),
            model: "llama3".into(),
            timeout_ms: 1_000,
        });
        assert_eq!(p.id().0, "ollama");
        assert_eq!(p.model(), "llama3");
        assert_eq!(p.base_url(), "http://127.0.0.1:11434");
    }
}
