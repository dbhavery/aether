//! Vision provider surface.
//!
//! A small, deliberately narrow interface for "give the model a single
//! image plus a text cue and get a textual response back". This is the
//! foundation hook the multimodal v0 work needs — no streaming, no
//! batching, no tool-call dispatch, just one frame at a time.
//!
//! The shell consults this surface from the `analyze_frame` command
//! when a vision provider has been configured at boot. When none is
//! configured, the shell keeps its existing text-only fallback path —
//! adapter authors are expected to surface configuration via env-only
//! opt-in so the OSS default build stays network-free.
//!
//! This module is provider-agnostic. Concrete adapters live next to
//! the text providers (see `providers/ollama.rs` for the Ollama
//! vision wiring).

use crate::error::L4Error;

/// Single-image analysis request. Owned so the trait method can be
/// boxed without lifetime gymnastics; the image payload is a *raw*
/// base64 string (no `data:image/...;base64,` prefix) so adapters do
/// not have to re-parse the data URL.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VisionRequest {
    /// Human cue ("describe what you see", "is the kettle on?", …).
    /// May be empty — adapters should default to a neutral instruction
    /// in that case.
    pub cue: String,
    /// Base64-encoded image bytes, **without** the `data:` URL prefix.
    /// Adapters that need the prefix can reattach it locally.
    pub image_b64: String,
    /// MIME type (e.g. `image/jpeg`, `image/png`). Informational; some
    /// adapters require it, others infer.
    pub mime: String,
}

/// Vision response — the assistant text plus the same optional token
/// counts the text completion path returns. Either count is `None`
/// when the provider does not report it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VisionResponse {
    /// Assistant text.
    pub text: String,
    /// Prompt-side token count if the provider reported it.
    pub prompt_tokens: Option<u32>,
    /// Completion-side token count if the provider reported it.
    pub completion_tokens: Option<u32>,
}

/// Vision provider trait. Concrete implementations live next to the
/// text providers (e.g. `OllamaVisionProvider`).
///
/// Implementors MUST be `Send + Sync` because the shell stores the
/// active provider behind an `Arc<dyn VisionProvider>` for cheap
/// sharing across IPC handlers.
pub trait VisionProvider: Send + Sync {
    /// Stable provider id (e.g. `"ollama"`, `"llamacpp"`). Used for
    /// telemetry and audit tagging.
    fn id(&self) -> &str;
    /// Human-friendly label (`"Ollama vision · llava · http://..."`)
    /// suitable for the Trust drawer's provider badge.
    fn label(&self) -> String;
    /// Light reachability probe. Same semantics as the text-provider
    /// healthcheck: `Ok(())` means the daemon answered something
    /// non-fatal at this configuration.
    fn healthcheck(&self) -> Result<(), L4Error>;
    /// Single-image analysis. Implementations should keep the image
    /// data only in-transit; never log the full payload.
    fn analyze(&self, req: VisionRequest) -> Result<VisionResponse, L4Error>;
    /// List the model ids the underlying daemon currently has
    /// available. Default returns an empty vec — adapters that do not
    /// expose a model-listing endpoint inherit this and the UI shows
    /// a "models unavailable" state.
    ///
    /// `Err` is reserved for transport-level failures the caller may
    /// want to surface differently from "no models known"; today both
    /// the UI and the Tauri command treat them the same — silently —
    /// so the dropdown never spams the user.
    fn list_models(&self) -> Result<Vec<String>, L4Error> {
        Ok(Vec::new())
    }
    /// Switch the model this provider uses for subsequent `analyze`
    /// calls. Default impl is a no-op returning `Ok(())` so passive
    /// adapters (ones that cannot change model at runtime) inherit the
    /// right behaviour without forcing every implementor to override.
    ///
    /// Implementors that support runtime model swap should store the id
    /// behind interior mutability (e.g. `RwLock<String>`) so the trait
    /// stays `&self`. Existing in-flight `analyze` calls keep whichever
    /// model they captured on entry — the swap is per-call.
    fn set_model(&self, _id: &str) -> Result<(), L4Error> {
        Ok(())
    }
    /// Current model id this provider is pointed at. `None` when the
    /// adapter does not expose a model field (passive adapters). The
    /// default impl returns `None` so implementors that have a concept
    /// of "current model" must opt in.
    fn current_model(&self) -> Option<String> {
        None
    }
}

/// Strip the `data:image/...;base64,` prefix off a data URL and return
/// `(mime, base64_body)`. Errors when the input does not start with the
/// `data:` protocol prefix or is missing the `;base64,` separator.
///
/// Pure helper exposed for unit tests; the shell uses it before
/// constructing a `VisionRequest`.
pub fn split_data_url(data_url: &str) -> Result<(String, String), L4Error> {
    let stripped = data_url
        .strip_prefix("data:")
        .ok_or_else(|| L4Error::ProviderBadResponse {
            detail: "data URL missing 'data:' prefix".to_string(),
        })?;
    let (header, body) = stripped
        .split_once(",")
        .ok_or_else(|| L4Error::ProviderBadResponse {
            detail: "data URL missing ',' separator".to_string(),
        })?;
    let (mime, encoding) = header
        .split_once(";")
        .map(|(m, e)| (m.to_string(), e.to_string()))
        .unwrap_or_else(|| (header.to_string(), String::new()));
    if encoding != "base64" {
        return Err(L4Error::ProviderBadResponse {
            detail: format!("only base64 data URLs supported (got {encoding:?})"),
        });
    }
    if mime.is_empty() {
        return Err(L4Error::ProviderBadResponse {
            detail: "data URL missing MIME type".to_string(),
        });
    }
    Ok((mime, body.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_data_url_parses_jpeg() {
        let url = "data:image/jpeg;base64,/9j/4AAQSkZJ";
        let (mime, body) = split_data_url(url).unwrap();
        assert_eq!(mime, "image/jpeg");
        assert_eq!(body, "/9j/4AAQSkZJ");
    }

    #[test]
    fn split_data_url_parses_png() {
        let url = "data:image/png;base64,iVBORw0KGgo=";
        let (mime, body) = split_data_url(url).unwrap();
        assert_eq!(mime, "image/png");
        assert_eq!(body, "iVBORw0KGgo=");
    }

    #[test]
    fn split_data_url_rejects_non_data_url() {
        let err = split_data_url("https://example.com/x.jpg").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_data_url_rejects_missing_separator() {
        let err = split_data_url("data:image/jpeg;base64").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_data_url_rejects_non_base64_encoding() {
        let err = split_data_url("data:text/plain,hello").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_data_url_rejects_empty_mime() {
        let err = split_data_url("data:;base64,abc").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }
}
