"""
Voice input pipeline — orchestrates wake word -> VAD -> STT -> speaker verify -> EventBus.
This is the main entry point for all voice input.
"""

import asyncio
import threading
import traceback

import numpy as np
from loguru import logger

from src.core.events import event_bus
from src.shared.config import get_yaml_config
from src.shared.types import EventType, AetherEvent
from src.voice.echo_cancel import get_echo_canceller
from src.voice.silent_gate import get_silent_gate
from src.voice.speaker_verify import initialize_enrollment, verify_speaker
from src.voice.stt import get_circuit_breaker, transcribe
from src.voice.vad import VADStream
from src.voice.wake_context import evaluate_wake_context
from src.voice.wake_word import WakeWordDetector


class VoicePipeline:
    # Health watchdog constants
    _WATCHDOG_INTERVAL = 15.0  # seconds between health checks
    _CB_TRIP_RESET_THRESHOLD = 3  # consecutive CB trips before full pipeline reset
    _AUDIO_STARVATION_TIMEOUT = 300.0  # 5 minutes without audio callback → restart

    def __init__(self):
        config = get_yaml_config()
        self._sample_rate = config["audio"]["sample_rate"]
        self._chunk_size = config["audio"]["chunk_size"]
        self._input_device = config["audio"]["input_device"]
        self._running = False
        self._wake_word_available = False
        # threading.Lock guards _listening_for_speech which is read/written from
        # the PortAudio callback thread, the capture thread, and the asyncio thread.
        self._state_lock = threading.Lock()
        self._listening_for_speech = False
        self._loop = None
        self._wake_word = WakeWordDetector(on_detected=self._on_wake_word)
        self._vad = VADStream(
            on_speech_start=self._on_speech_start,
            on_speech_end=self._on_speech_end,
        )
        # Barge-in config
        voice_config = config.get("voice", {})
        self._barge_in_enabled = voice_config.get("barge_in_enabled", True)
        self._barge_in_delay_ms = voice_config.get("barge_in_delay_ms", 300)
        self._barge_in_speech_ms: float = 0.0  # Accumulated speech during TTS
        self._barge_in_triggered = threading.Event()  # Signal from callback to capture loop
        # Thread reference — set in start(), joined in stop()
        self._capture_thread: threading.Thread | None = None
        # Health tracking
        self._last_audio_callback_time: float = 0.0
        self._last_successful_transcription: float = 0.0
        self._consecutive_cb_trips: int = 0
        self._watchdog_task: asyncio.Task | None = None

    def _on_wake_word(self):
        with self._state_lock:
            if self._listening_for_speech:
                return  # Already listening — ignore duplicate wake word
            self._listening_for_speech = True
        logger.info("Pipeline: Wake word detected — listening for speech")
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                event_bus.publish(
                    AetherEvent(
                        type=EventType.WAKE_WORD_DETECTED,
                        data={},
                        source_module="voice_pipeline",
                    )
                ),
                self._loop,
            )

    def _on_speech_start(self):
        with self._state_lock:
            listening = self._listening_for_speech
        if listening:
            logger.debug("Pipeline: Speech started")

    def _on_speech_end(self, audio: np.ndarray):
        with self._state_lock:
            if not self._listening_for_speech:
                return
            self._listening_for_speech = False
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._process_speech_and_relisten(audio),
                self._loop,
            )

    async def _process_speech_and_relisten(self, audio: np.ndarray):
        """Process speech then re-enable listening (prevents overlapping speech processing)."""
        await self._process_speech(audio)
        # In always-listen mode (no wake word), re-enable listening AFTER processing
        if not self._wake_word_available:
            with self._state_lock:
                self._listening_for_speech = True

    async def _health_watchdog(self) -> None:
        """Background task: monitors pipeline health every 15s.

        Detects:
        - Repeated circuit breaker trips → full pipeline reset
        - Audio starvation (no callbacks for 5 min) → restart audio device
        """
        import time

        logger.info("Pipeline: Health watchdog started")
        while self._running:
            await asyncio.sleep(self._WATCHDOG_INTERVAL)
            if not self._running:
                break

            cb = get_circuit_breaker()
            now = time.monotonic()

            # Check circuit breaker state
            if cb.is_tripped:
                self._consecutive_cb_trips += 1
                logger.warning(
                    f"Pipeline/Watchdog: CB tripped ({self._consecutive_cb_trips}/{self._CB_TRIP_RESET_THRESHOLD})"
                )
                if self._consecutive_cb_trips >= self._CB_TRIP_RESET_THRESHOLD:
                    logger.error("Pipeline/Watchdog: 3 consecutive CB trips — resetting pipeline")
                    self._consecutive_cb_trips = 0
                    cb.reset()
                    # Reset the listening state
                    with self._state_lock:
                        self._listening_for_speech = False
            else:
                self._consecutive_cb_trips = 0

            # Check audio starvation
            if self._last_audio_callback_time > 0:
                silence = now - self._last_audio_callback_time
                if silence > self._AUDIO_STARVATION_TIMEOUT:
                    logger.error(
                        f"Pipeline/Watchdog: No audio callback for {silence:.0f}s — audio device may have disconnected"
                    )
                    from src.core.health import update_module_status

                    update_module_status("voice_in", "degraded")

            # Log health summary
            logger.debug(
                f"Pipeline/Watchdog: CB trips={cb.trip_count}, "
                f"consecutive={self._consecutive_cb_trips}, "
                f"tripped={cb.is_tripped}"
            )

    async def _process_speech(self, audio: np.ndarray):
        import time as _time

        logger.info(f"Pipeline: Processing speech ({len(audio) / self._sample_rate:.1f}s)")
        try:
            # Speaker verification
            is_owner, score = await verify_speaker(audio, self._sample_rate)
            if not is_owner:
                logger.warning(f"Pipeline: Speaker verification failed (score={score:.3f}) — ignoring")
                return

            await event_bus.publish(
                AetherEvent(
                    type=EventType.SPEAKER_VERIFIED,
                    data={"is_owner": is_owner, "score": score},
                    source_module="voice_pipeline",
                )
            )

            # Transcribe
            text = await transcribe(audio, self._sample_rate)
            if not text:
                logger.warning("Pipeline: STT returned empty text")
                return

            # False wake-up filter: check if The user is talking TO Aether
            if not evaluate_wake_context(text):
                logger.info(f"Pipeline: Wake context rejected transcript — false wake-up: '{text[:60]}'")
                return

            # SilentGate: triple gate check — is this speech directed at Aether?
            gate = get_silent_gate()
            should_respond = await gate.should_respond(text, is_owner=is_owner)
            if not should_respond:
                logger.info(f"Pipeline: SilentGate blocked response for: '{text[:60]}'")
                return

            self._last_successful_transcription = _time.monotonic()
            logger.info(f"Pipeline: Transcript ready: '{text}'")
            await event_bus.publish(
                AetherEvent(
                    type=EventType.TRANSCRIPT_READY,
                    data={"text": text, "confidence": 1.0},
                    source_module="voice_pipeline",
                )
            )

            # Also publish as USER_MESSAGE so Brain handles it
            await event_bus.publish(
                AetherEvent(
                    type=EventType.USER_MESSAGE,
                    data={"text": text, "mode": "voice"},
                    source_module="voice_pipeline",
                )
            )

        except Exception as e:
            logger.error(f"Pipeline: speech processing error: {e}\n{traceback.format_exc()}")

    async def start(self):
        """Start the voice pipeline. Initializes wake word and begins audio capture."""
        logger.info("Pipeline: Initializing voice pipeline...")
        # Set loop BEFORE starting capture thread — callback needs it immediately
        self._loop = asyncio.get_running_loop()

        # Enroll the user's voice if not already enrolled
        await initialize_enrollment()

        # Initialize wake word
        wake_word_available = self._wake_word.initialize()
        self._wake_word_available = wake_word_available

        # If wake word is not available, always listen for speech (no trigger needed)
        if not wake_word_available:
            with self._state_lock:
                self._listening_for_speech = True
            logger.info("Pipeline: Wake word unavailable — always-listen mode enabled")

        # Update health status
        from src.core.health import update_module_status

        update_module_status("voice_in", "ready")

        # Start audio capture in a thread
        self._running = True
        self._capture_thread = threading.Thread(
            target=self._audio_capture_loop,
            args=(wake_word_available,),
            daemon=True,
        )
        self._capture_thread.start()

        # Start health watchdog
        self._watchdog_task = asyncio.create_task(self._health_watchdog())

        logger.info("Pipeline: Voice pipeline running. Say 'Aether' to activate.")

    def _audio_capture_loop(self, use_wake_word: bool):
        """Runs in a background thread — captures audio and feeds wake word + VAD."""
        import time as _time

        import sounddevice as sd

        sample_rate = self._sample_rate
        frame_length = self._wake_word.frame_length if use_wake_word else 512
        chunk_duration_ms = (frame_length / sample_rate) * 1000

        echo = get_echo_canceller()

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Pipeline: Audio status: {status}")
            self._last_audio_callback_time = _time.monotonic()
            audio_chunk = indata[:, 0].copy()  # Mono

            # Echo cancellation + barge-in
            if echo.is_speaking:
                if self._barge_in_enabled:
                    # Barge-in detection: use RMS energy (not ML) to stay real-time safe.
                    # Silero VAD has LSTM state and is too heavy for PortAudio callbacks.
                    rms = float(np.sqrt(np.mean(audio_chunk**2)))
                    if rms >= 0.03:  # Energy threshold for speech presence
                        self._barge_in_speech_ms += chunk_duration_ms
                        if self._barge_in_speech_ms >= self._barge_in_delay_ms:
                            logger.info("Pipeline: Barge-in detected — signaling stop")
                            self._barge_in_speech_ms = 0.0
                            # Signal capture loop to stop TTS (never call sd.stop from callback)
                            self._barge_in_triggered.set()
                            echo.on_tts_stop()
                            # Transition to listening for full speech
                            with self._state_lock:
                                self._listening_for_speech = True
                            if self._loop:
                                asyncio.run_coroutine_threadsafe(
                                    event_bus.publish(
                                        AetherEvent(
                                            type=EventType.WAKE_WORD_DETECTED,
                                            data={"source": "barge_in"},
                                            source_module="voice_pipeline",
                                        )
                                    ),
                                    self._loop,
                                )
                    else:
                        self._barge_in_speech_ms = 0.0
                return  # Either barge-in handled it, or echo gate suppresses
            elif echo.should_gate_input:
                # Ring-down period after TTS — suppress input
                return

            with self._state_lock:
                listening = self._listening_for_speech

            if use_wake_word and not listening:
                # Feed to wake word detector
                pcm = (audio_chunk * 32767).astype(np.int16).tolist()
                # Porcupine needs exact frame_length
                if len(pcm) == frame_length:
                    self._wake_word.process_frame(pcm)
            elif listening:
                # Feed to VAD
                self._vad.process_chunk(audio_chunk, chunk_duration_ms)

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=frame_length,
                device=self._input_device,
                callback=audio_callback,
            ):
                logger.info(f"Pipeline: Audio capture started at {sample_rate}Hz")
                while self._running:
                    # Check for barge-in signal from callback thread
                    if self._barge_in_triggered.is_set():
                        self._barge_in_triggered.clear()
                        sd.stop()
                        logger.debug("Pipeline: TTS stopped via barge-in (from capture thread)")
                    sd.sleep(100)
        except Exception as e:
            logger.error(
                f"Pipeline: Audio capture loop DIED — voice input is no longer "
                f"functional. Error: {e}\n{traceback.format_exc()}"
            )
            self._running = False
            # Update health to reflect that voice input is broken
            try:
                from src.core.health import update_module_status

                update_module_status("voice_in", "error")
            except Exception:  # nosec B110
                logger.debug("Pipeline: could not update health status during shutdown")

    def stop(self):
        self._running = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
        self._wake_word.cleanup()
        logger.info("Pipeline: Voice pipeline stopped")


_pipeline_instance: VoicePipeline | None = None


async def start_voice_pipeline() -> None:
    global _pipeline_instance
    # Stop any existing pipeline to prevent resource leak on restart
    if _pipeline_instance is not None:
        _pipeline_instance.stop()
    _pipeline_instance = VoicePipeline()
    await _pipeline_instance.start()


def stop_voice_pipeline() -> None:
    global _pipeline_instance
    if _pipeline_instance:
        _pipeline_instance.stop()
