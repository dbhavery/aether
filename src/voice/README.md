# Module 02/03: Voice

Handles all audio input and output — from wake word detection to TTS playback.

## Responsibility

Captures microphone audio continuously, detects the wake word, runs VAD to segment
speech, verifies the speaker is the owner, transcribes the audio to text, and publishes the
result to the EventBus. On the output side, it subscribes to response text events,
synthesizes speech using Chatterbox Turbo (with ElevenLabs as fallback), and plays
the audio through the system speakers.

## Key Files

- `pipeline.py` — `VoicePipeline`: main orchestrator, runs audio capture in a background
  thread, routes audio frames through wake word -> VAD -> speaker verify -> STT
- `wake_word.py` — `WakeWordDetector`: Picovoice Porcupine wrapper; loads custom
  `Aether_windows.ppn` keyword, falls back to built-in "jarvis" if not found
- `wake_context.py` — `evaluate_wake_context()`: post-wake-word false-positive filter;
  rejects transcript if The user is talking about Aether to someone else, not to her
- `vad.py` — `VADStream` + `is_speech()`: Silero VAD streaming detector; buffers audio
  between speech_start/speech_end callbacks based on configurable thresholds
- `speaker_verify.py` — `verify_speaker()` / `enroll_owner()`: SpeechBrain ECAPA-TDNN
  cosine similarity check against stored enrollment embedding; fails closed on error
- `stt.py` — `transcribe()`: ElevenLabs Scribe v2 primary, faster-whisper
  distil-large-v3 CUDA fallback (falls further back to base.en if model unavailable)
- `tts.py` — `synthesize()`: Chatterbox Turbo (CUDA, cloned voice from reference WAV)
  primary, ElevenLabs Flash v2.5 cloud fallback; parses emotion tags for exaggeration
- `tts_handler.py` — `register_tts_handlers()`: bridges `RESPONSE_TEXT_READY` EventBus
  event to TTS synthesis + playback; signals avatar when speaking ends
- `audio_player.py` — `play_audio()` / `stop_playback()`: sounddevice playback with
  asyncio lock to prevent concurrent audio streams

## Interface Contract

Publishes:
- `WAKE_WORD_DETECTED` — wake word fired, no payload
- `SPEAKER_VERIFIED` — speaker check passed, payload: `{"score": float}`
- `TRANSCRIPT_READY` — payload: `{"text": str, "confidence": float}`
- `USER_MESSAGE` — payload: `{"text": str, "mode": "voice"}`

Subscribes to:
- `RESPONSE_TEXT_READY` — triggers TTS synthesis and playback

Exports:
- `start_voice_pipeline()` / `stop_voice_pipeline()` — called by startup orchestration
- `register_tts_handlers()` — registers TTS EventBus subscription

## Dependencies

External packages:
- `pvporcupine` — Picovoice Porcupine wake word (requires `PICOVOICE_ACCESS_KEY`)
- `silero-vad` (via `torch.hub`) — voice activity detection
- `speechbrain` — ECAPA-TDNN speaker verification model
- `elevenlabs` — Scribe v2 STT and Flash v2.5 TTS (requires `ELEVENLABS_API_KEY`)
- `faster-whisper` — local STT fallback (CUDA, distil-large-v3)
- `chatterbox` — local TTS primary (CUDA, requires reference WAV)
- `sounddevice`, `soundfile` — audio I/O
- `torch`, `torchaudio` — tensor ops for VAD and speaker verify
- `numpy` — audio array manipulation

Internal modules:
- `src.core.events` — EventBus publish/subscribe
- `src.shared.config` — `get_settings()`, `get_yaml_config()`
- `src.shared.types` — `EventType`, `AetherEvent`
- `src.core.health` — `update_module_status()`
- `src.avatar.client` — signals avatar speaking state after TTS playback
