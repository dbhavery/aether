//! Speech provider surface.
//!
//! A small, deliberately narrow interface for "give the model a single
//! audio utterance and get a textual transcription back". This is the
//! Voice V1 analogue of [`crate::vision::VisionProvider`]: single-
//! utterance only, no streaming, no batching, no continuous listening,
//! no wake word, no voice activity detection.
//!
//! The shell is expected to consult this surface from a future
//! `transcribe_utterance` command when a speech provider has been
//! configured at boot. When none is configured the shell must surface
//! a clear error to the user — there is no silent text fallback for
//! voice (losing a user's utterance without notice would be a worse
//! UX than a visible error, unlike vision where a text-only fallback
//! is acceptable).
//!
//! This module is provider-agnostic. Concrete adapters live next to
//! the vision providers (see `providers/whispercpp_speech.rs` for the
//! whisper.cpp wiring).
//!
//! The full contract is documented in
//! `docs/VOICE-V1-ARCHITECTURE.md`.

use crate::error::L4Error;

/// Single-utterance transcription request. Owned so the trait method
/// can be boxed without lifetime gymnastics; the audio payload is a
/// *raw* base64 string (no `data:audio/...;base64,` prefix) so
/// adapters do not have to re-parse the data URL.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpeechRequest {
    /// Base64-encoded audio bytes, **without** the `data:` URL prefix.
    /// Adapters that need the prefix can reattach it locally.
    pub audio_b64: String,
    /// MIME type (e.g. `audio/wav`). Informational; adapters may use
    /// it to pick the decode path, or ignore it entirely.
    pub mime: String,
    /// Sample rate of the decoded PCM, in Hz. Voice V1 captures
    /// 16 kHz mono — adapters MAY reject other rates, or resample.
    pub sample_rate: u32,
    /// Channel count of the decoded PCM. Voice V1 captures mono (1).
    /// Adapters MAY down-mix or reject as they see fit.
    pub channels: u16,
    /// Optional ISO-639-1 language hint (e.g. `"en"`, `"ja"`).
    /// `None` → adapter auto-detects per its own configuration
    /// (e.g. `AETHER_WHISPERCPP_SPEECH_LANGUAGE` env override).
    pub language: Option<String>,
}

/// Transcription response — the transcribed text plus optional
/// confidence + token counts that the underlying provider may or may
/// not report. All fields except `text` are `Option` so passive
/// adapters can return `None` without loss.
#[derive(Debug, Clone, PartialEq)]
pub struct SpeechResponse {
    /// Transcribed text. Empty string is a valid response — the
    /// utterance may genuinely have been silence. The shell decides
    /// how to render an empty transcript (Voice V1 design says:
    /// show the error-tier system message, not an empty user turn).
    pub text: String,
    /// Average per-token logprob or similar confidence signal, when
    /// the provider exposes one. Range is provider-specific — the UI
    /// should treat this as informational, not load-bearing.
    pub confidence: Option<f32>,
    /// Prompt-side (audio-side) token count if reported. Most STT
    /// providers do not report this; left optional for symmetry
    /// with `VisionResponse`.
    pub prompt_tokens: Option<u32>,
    /// Output-side (transcript) token count if reported.
    pub completion_tokens: Option<u32>,
}

/// Speech provider trait. Concrete implementations live next to the
/// vision providers (e.g. `WhisperCppSpeechProvider`).
///
/// Implementors MUST be `Send + Sync` because the shell is expected
/// to store the active provider behind an `Arc<dyn SpeechProvider>`
/// (same pattern as [`crate::vision::VisionProvider`]) for cheap
/// sharing across IPC handlers.
///
/// The trait is deliberately object-safe — no generic methods, no
/// `Self` in return positions. Locked by a compile-time test in this
/// module.
pub trait SpeechProvider: Send + Sync {
    /// Stable provider id (e.g. `"whispercpp-speech"`). Used for
    /// telemetry and audit tagging. Must be unique across registered
    /// speech providers.
    fn id(&self) -> &str;

    /// Human-friendly label
    /// (`"whisper.cpp · ggml-base.en · http://..."`) suitable for the
    /// Trust drawer's provider badge.
    fn label(&self) -> String;

    /// Light reachability probe. Same semantics as the vision-provider
    /// healthcheck: `Ok(())` means the daemon answered something
    /// non-fatal at this configuration.
    fn healthcheck(&self) -> Result<(), L4Error>;

    /// Single-utterance transcription. Implementations should keep the
    /// audio data only in-transit; never log the full payload, never
    /// persist it.
    ///
    /// Adapters that have not yet wired their inference backend (e.g.
    /// a scaffold-only phase) MUST return a clear
    /// `L4Error::ProviderUnknown` so the shell can surface the error
    /// to the user rather than silently falling back.
    fn transcribe(&self, req: SpeechRequest) -> Result<SpeechResponse, L4Error>;

    /// List the speech model ids the underlying daemon currently has
    /// available. Default returns an empty vec — adapters that do not
    /// expose a model-listing endpoint inherit this and the UI shows
    /// a "models unavailable" state.
    ///
    /// `Err` is reserved for transport-level failures the caller may
    /// want to surface differently from "no models known"; today both
    /// the UI and the future Tauri command can treat them the same —
    /// silently — so the dropdown never spams the user.
    fn list_models(&self) -> Result<Vec<String>, L4Error> {
        Ok(Vec::new())
    }

    /// Switch the model this provider uses for subsequent `transcribe`
    /// calls. Default impl is a no-op returning `Ok(())` so passive
    /// adapters (ones that cannot change model at runtime) inherit the
    /// right behaviour without forcing every implementor to override.
    ///
    /// Implementors that support runtime model swap should store the
    /// id behind interior mutability (e.g. `RwLock<String>`) so the
    /// trait stays `&self`. Existing in-flight `transcribe` calls
    /// keep whichever model they captured on entry — the swap is
    /// per-call.
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

/// Strip the `data:audio/...;base64,` prefix off a data URL and
/// return `(mime, base64_body)`. Errors when the input does not start
/// with the `data:` protocol prefix, is missing the `;base64,`
/// separator, declares a non-base64 encoding, or advertises an empty
/// MIME type.
///
/// Pure helper exposed for unit tests; a future
/// `transcribe_utterance` command will use it before constructing a
/// `SpeechRequest`. Mirrors [`crate::vision::split_data_url`] but is
/// deliberately a separate function because the MIME prefix differs
/// (`audio/` vs `image/`) — see §5 "Utterance validation" in
/// `docs/VOICE-V1-ARCHITECTURE.md`.
pub fn split_audio_data_url(data_url: &str) -> Result<(String, String), L4Error> {
    let stripped = data_url
        .strip_prefix("data:")
        .ok_or_else(|| L4Error::ProviderBadResponse {
            detail: "audio data URL missing 'data:' prefix".to_string(),
        })?;
    let (header, body) = stripped
        .split_once(',')
        .ok_or_else(|| L4Error::ProviderBadResponse {
            detail: "audio data URL missing ',' separator".to_string(),
        })?;
    let (mime, encoding) = header
        .split_once(';')
        .map(|(m, e)| (m.to_string(), e.to_string()))
        .unwrap_or_else(|| (header.to_string(), String::new()));
    if encoding != "base64" {
        return Err(L4Error::ProviderBadResponse {
            detail: format!("only base64 audio data URLs supported (got {encoding:?})"),
        });
    }
    if mime.is_empty() {
        return Err(L4Error::ProviderBadResponse {
            detail: "audio data URL missing MIME type".to_string(),
        });
    }
    if !mime.starts_with("audio/") {
        return Err(L4Error::ProviderBadResponse {
            detail: format!("audio data URL has non-audio MIME type: {mime}"),
        });
    }
    Ok((mime, body.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    /// Compile-time proof that `SpeechProvider` is object-safe. The
    /// shell is expected to hold adapters behind `Arc<dyn
    /// SpeechProvider>`; if the trait ever gains a method that breaks
    /// object-safety (generic method, `Self` in return position, etc.)
    /// this function stops compiling.
    #[allow(dead_code)]
    fn _assert_object_safe(p: Arc<dyn SpeechProvider>) -> Arc<dyn SpeechProvider> {
        p
    }

    /// A minimal in-test implementation used to exercise the default
    /// methods without pulling in a concrete adapter.
    struct DummySpeech;

    impl SpeechProvider for DummySpeech {
        fn id(&self) -> &str {
            "dummy-speech"
        }
        fn label(&self) -> String {
            "dummy".to_string()
        }
        fn healthcheck(&self) -> Result<(), L4Error> {
            Ok(())
        }
        fn transcribe(&self, _req: SpeechRequest) -> Result<SpeechResponse, L4Error> {
            Err(L4Error::ProviderUnknown {
                detail: "dummy speech adapter does not transcribe".to_string(),
            })
        }
    }

    #[test]
    fn default_list_models_is_empty() {
        let d = DummySpeech;
        assert!(d.list_models().unwrap().is_empty());
    }

    #[test]
    fn default_set_model_is_noop_ok() {
        let d = DummySpeech;
        assert!(d.set_model("anything").is_ok());
    }

    #[test]
    fn default_current_model_is_none() {
        let d = DummySpeech;
        assert!(d.current_model().is_none());
    }

    #[test]
    fn default_transcribe_is_required() {
        // Trait does NOT provide a default impl for `transcribe`.
        // If someone adds one, this test's intent (ensure every
        // adapter consciously implements transcription) is broken;
        // update this assertion and the trait doc together.
        let d = DummySpeech;
        let req = SpeechRequest {
            audio_b64: "AAAA".to_string(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: None,
        };
        assert!(d.transcribe(req).is_err());
    }

    #[test]
    fn dyn_speech_provider_is_callable() {
        let p: Arc<dyn SpeechProvider> = Arc::new(DummySpeech);
        assert_eq!(p.id(), "dummy-speech");
        assert!(p.healthcheck().is_ok());
    }

    #[test]
    fn split_audio_data_url_parses_wav() {
        let url = "data:audio/wav;base64,UklGRgAA";
        let (mime, body) = split_audio_data_url(url).unwrap();
        assert_eq!(mime, "audio/wav");
        assert_eq!(body, "UklGRgAA");
    }

    #[test]
    fn split_audio_data_url_rejects_non_data_url() {
        let err = split_audio_data_url("https://example.com/clip.wav").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_audio_data_url_rejects_missing_separator() {
        let err = split_audio_data_url("data:audio/wav;base64").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_audio_data_url_rejects_non_base64_encoding() {
        let err = split_audio_data_url("data:audio/wav,rawbytes").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_audio_data_url_rejects_empty_mime() {
        let err = split_audio_data_url("data:;base64,abc").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn split_audio_data_url_rejects_non_audio_mime() {
        // Prevent accidentally routing an image payload through the
        // speech pipeline.
        let err = split_audio_data_url("data:image/jpeg;base64,abc").unwrap_err();
        assert!(matches!(err, L4Error::ProviderBadResponse { .. }));
    }

    #[test]
    fn speech_request_struct_roundtrips_defaults() {
        let req = SpeechRequest {
            audio_b64: "DATA".to_string(),
            mime: "audio/wav".to_string(),
            sample_rate: 16000,
            channels: 1,
            language: Some("en".to_string()),
        };
        assert_eq!(req.sample_rate, 16000);
        assert_eq!(req.channels, 1);
        assert_eq!(req.language.as_deref(), Some("en"));
    }

    #[test]
    fn speech_response_optional_fields_default_to_none() {
        let r = SpeechResponse {
            text: "ok".to_string(),
            confidence: None,
            prompt_tokens: None,
            completion_tokens: None,
        };
        assert_eq!(r.text, "ok");
        assert!(r.confidence.is_none());
    }
}
