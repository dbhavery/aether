"""Voice Activity Detection using Silero VAD — CPU, lightweight, accurate."""

import threading

import numpy as np
import torch
from loguru import logger

from src.shared.config import get_yaml_config
from src.voice.silence_detector import ContextAwareSilenceDetector

_model = None
_utils = None
_model_lock = threading.Lock()


def _load_model():
    global _model, _utils
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("VAD: loading Silero VAD model...")
                _model, _utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    trust_repo=True,
                )
                _model.eval()
                logger.info("VAD: Silero VAD ready")
    return _model, _utils


def reset_model_state() -> None:
    """Reset Silero VAD internal LSTM state.

    Call between speech segments or after barge-in mode transitions to prevent
    stale hidden states from corrupting subsequent speech detection.
    """
    if _model is not None:
        with _model_lock:
            _model.reset_states()
        logger.debug("VAD: LSTM state reset")


def is_speech(audio_chunk: np.ndarray, sample_rate: int = 16000) -> float:
    """Returns speech probability 0.0-1.0 for an audio chunk."""
    model, _ = _load_model()
    tensor = torch.FloatTensor(audio_chunk)
    if tensor.dim() == 1:
        tensor = tensor.unsqueeze(0)
    with torch.no_grad():
        prob = model(tensor, sample_rate).item()
    return prob


class VADStream:
    """Streaming VAD — buffers audio, fires callbacks on speech start/end."""

    # 60 seconds at 16kHz = 960,000 samples — hard ceiling to prevent memory
    # exhaustion when VAD gets stuck in the speech-detected state.
    MAX_BUFFER_SAMPLES: int = 960_000

    def __init__(self, on_speech_start=None, on_speech_end=None):
        config = get_yaml_config()
        self.threshold = config["audio"]["vad_threshold"]
        self.min_speech_ms = config["audio"]["vad_min_speech_ms"]
        self.max_silence_ms = config["audio"]["vad_max_silence_ms"]
        self.sample_rate = config["audio"]["sample_rate"]
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self._in_speech = False
        self._speech_buffer: list[np.ndarray] = []
        self._buffer_sample_count: int = 0
        self._silence_ms = 0
        self._speech_ms = 0
        self._silence_detector = ContextAwareSilenceDetector(base_silence_ms=self.max_silence_ms)
        self._partial_transcript: str | None = None

    def _reset_buffer(self) -> None:
        """Clear the speech buffer and all tracking counters."""
        self._speech_buffer = []
        self._buffer_sample_count = 0
        self._speech_ms = 0
        self._silence_ms = 0
        # Reset Silero LSTM hidden state to prevent cross-segment corruption
        reset_model_state()

    def _check_buffer_overflow(self) -> bool:
        """Return True and reset if the buffer has exceeded MAX_BUFFER_SAMPLES.

        This guards against memory exhaustion when VAD is stuck detecting
        speech (e.g. persistent background noise above threshold).
        Fires on_speech_end with buffered audio before resetting so at least
        a partial transcription can be attempted.
        """
        if self._buffer_sample_count > self.MAX_BUFFER_SAMPLES:
            logger.warning(
                "VAD: speech buffer exceeded {} samples ({:.1f}s at {}Hz) — "
                "flushing to STT and resetting. "
                "Possible stuck-open VAD or continuous background noise.",
                self.MAX_BUFFER_SAMPLES,
                self.MAX_BUFFER_SAMPLES / self.sample_rate,
                self.sample_rate,
            )
            # Attempt transcription of the accumulated audio before discarding
            if self._speech_ms >= self.min_speech_ms and self.on_speech_end and self._speech_buffer:
                audio = np.concatenate(self._speech_buffer)
                self.on_speech_end(audio)
            self._in_speech = False
            self._reset_buffer()
            return True
        return False

    def update_partial_transcript(self, text: str | None) -> None:
        """Feed partial transcript for context-aware silence detection."""
        self._partial_transcript = text

    def _get_effective_silence_ms(self) -> float:
        """Get silence threshold, dynamically adjusted by context if available."""
        return self._silence_detector.get_effective_silence_ms(self._partial_transcript)

    def process_chunk(self, chunk: np.ndarray, chunk_duration_ms: float) -> None:
        prob = is_speech(chunk, self.sample_rate)
        if prob >= self.threshold:
            if not self._in_speech:
                self._in_speech = True
                self._reset_buffer()
                self._partial_transcript = None  # Reset on new speech segment
                if self.on_speech_start:
                    self.on_speech_start()
            self._speech_buffer.append(chunk)
            self._buffer_sample_count += chunk.shape[0]
            self._speech_ms += chunk_duration_ms
            self._silence_ms = 0
            # Guard: prevent unbounded growth from stuck-open VAD
            self._check_buffer_overflow()
        else:
            if self._in_speech:
                self._silence_ms += chunk_duration_ms
                self._speech_buffer.append(chunk)
                self._buffer_sample_count += chunk.shape[0]
                effective_silence_ms = self._get_effective_silence_ms()
                if self._silence_ms >= effective_silence_ms:
                    self._in_speech = False
                    if self._speech_ms >= self.min_speech_ms:
                        audio = np.concatenate(self._speech_buffer)
                        if self.on_speech_end:
                            self.on_speech_end(audio)
                    self._reset_buffer()
                else:
                    # Guard: also check during silence-within-speech
                    self._check_buffer_overflow()
