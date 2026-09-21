# Module 02/03: Voice

Handles all audio input and output, from the push-to-talk trigger to TTS playback.

## Responsibility

The frontend holds the trigger. It publishes `USER_SPEECH_START` when the user
presses the key and `USER_SPEECH_END` when they release it. This module captures
the microphone audio between those two events, transcribes it, and publishes the
result to the EventBus so the brain handles voice identically to chat. On the
output side it subscribes to response text events, synthesizes speech using
Chatterbox Turbo (with ElevenLabs as fallback), and plays the audio through the
system speakers.

Wake-word detection and speaker verification are deliberately absent. Per
`docs/PRODUCT-PLAN.md` §1 decision 10, v1.0 replaces the wake word with
push-to-talk, and the `wake_word.py`, `wake_context.py` and `speaker_verify.py`
modules were removed during the port.

## Key Files

- `pipeline.py` - `VoicePipeline`: subscribes to `USER_SPEECH_START` /
  `USER_SPEECH_END`, captures 16 kHz mono audio on the `sounddevice` callback
  thread between them, and hands the buffer to `transcribe()`
- `stt.py` - `transcribe()`: faster-whisper local primary (model from
  `config.voice.stt_model`), optional ElevenLabs Scribe fallback
- `tts.py` - `synthesize()`: Chatterbox Turbo (CUDA, cloned voice from reference WAV)
  primary, ElevenLabs Flash v2.5 cloud fallback; parses emotion tags for exaggeration
- `tts_handler.py` - `register_tts_handlers()`: bridges `RESPONSE_TEXT_READY` EventBus
  event to TTS synthesis + playback; signals avatar when speaking ends
- `audio_player.py` - `play_audio()` / `stop_playback()`: sounddevice playback with
  asyncio lock to prevent concurrent audio streams

Carried forward from v1.0 and present in the tree, but not wired into the
push-to-talk path: `vad.py` (Silero VAD streaming detector), `silence_detector.py`
(context-aware silence thresholds, imported by `vad.py`), `silent_gate.py`
(speaker + intent gating), `echo_cancel.py` (input gate during TTS playback).
Nothing in `pipeline.py` imports them.

## Interface Contract

Publishes:
- `TRANSCRIPT_READY` - payload: `{"text": str, "confidence": float}`
- `USER_MESSAGE` - payload: `{"text": str, "mode": "voice"}`
- `RESPONSE_AUDIO_CHUNK` / `RESPONSE_AUDIO_END` - from `tts_handler.py`

Subscribes to:
- `USER_SPEECH_START` / `USER_SPEECH_END` - the push-to-talk trigger, published
  by the frontend
- `RESPONSE_TEXT_READY` - triggers TTS synthesis and playback

Exports:
- `start_voice_pipeline()` / `stop_voice_pipeline()` - called by startup orchestration
- `register_tts_handlers()` - registers TTS EventBus subscription

## Dependencies

External packages:
- `faster-whisper` - local STT primary (CUDA)
- `chatterbox` - local TTS primary (CUDA, requires reference WAV)
- `elevenlabs` - Scribe STT and Flash v2.5 TTS fallbacks (requires
  `ELEVENLABS_API_KEY`; both are optional and off unless a key is present)
- `sounddevice`, `soundfile` - audio I/O
- `torch`, `torchaudio` - tensor ops
- `numpy` - audio array manipulation
- `silero-vad` (via `torch.hub`) - used only by the unwired `vad.py`

Internal modules:
- `src.core.events` - EventBus publish/subscribe
- `src.shared.config` - `get_settings()`, `get_yaml_config()`
- `src.shared.types` - `EventType`, `AetherEvent`
- `src.core.health` - `update_module_status()`
- `src.avatar.client` - signals avatar speaking state after TTS playback
