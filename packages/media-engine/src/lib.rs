//! # aether-media-engine
//!
//! Media pipeline abstractions: STT, TTS, VAD, streaming chunk timing, viseme
//! metadata. **Wave 1 placeholder — traits only, no implementations.**
//!
//! Canonical reference: `ARCHITECTURE.md` (the speech stack and the L1/L3
//! layers this media surface serves, including the VAD hook).
//!
//! Borrowed models (Parakeet/Whisper, XTTS/Piper, Silero/WebRTC VAD) are isolated
//! behind these traits; the control plane (chunking, interruption, viseme sync)
//! is custom.

#![deny(unsafe_code)]
#![warn(missing_docs)]

use serde::{Deserialize, Serialize};

/// Streaming chunk of transcribed text from STT.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SttChunk {
    /// Partial vs final marker.
    pub is_final: bool,
    /// Text content.
    pub text: String,
    /// Milliseconds since turn start.
    pub t_ms: u64,
}

/// Streaming chunk of synthesized audio from TTS plus viseme metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TtsChunk {
    /// PCM or codec frame bytes.
    pub audio: Vec<u8>,
    /// Viseme id aligned with chunk boundary.
    pub viseme: Option<String>,
    /// Milliseconds since turn start.
    pub t_ms: u64,
}

/// VAD (voice activity detection) snapshot.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct VadState {
    /// Is voice currently detected?
    pub speaking: bool,
    /// Probability (0.0–1.0).
    pub p: f32,
    /// Milliseconds since turn start.
    pub t_ms: u64,
}

/// Media-layer error shape.
#[derive(Debug, thiserror::Error)]
pub enum MediaError {
    /// Placeholder while no implementation exists.
    #[error("not yet implemented — Wave 3+")]
    NotImplemented,
}

// TODO(wave-3): `SttAdapter`, `TtsAdapter`, `VadAdapter` traits.
// TODO(wave-3): borrowed-model wrappers gated behind cargo features
// (`stt-whisper`, `stt-parakeet`, `tts-xtts`, `tts-piper`, `vad-silero`).
// TODO(wave-3): custom chunker + interruption state machine (L1 / L3 consumers).

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stt_chunk_is_serializable() {
        let c = SttChunk {
            is_final: true,
            text: "hello".into(),
            t_ms: 100,
        };
        let j = serde_json::to_string(&c).unwrap();
        assert!(j.contains("\"hello\""));
    }
}
