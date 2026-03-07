"""Wake word detection using Picovoice Porcupine — 92.5% detection rate, free personal tier."""

from pathlib import Path

from loguru import logger

from src.shared.config import get_settings, get_yaml_config

CUSTOM_KEYWORD_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "wakeword" / "Aether_windows.ppn"


class WakeWordDetector:
    def __init__(self, on_detected=None):
        self._handle = None
        self._on_detected = on_detected
        self._frame_length = None
        self._sample_rate = None

    def initialize(self) -> bool:
        """Initialize Porcupine. Returns True if successful."""
        try:
            import pvporcupine

            settings = get_settings()
            config = get_yaml_config()

            if not settings.picovoice_access_key:
                logger.warning("WakeWord: PICOVOICE_ACCESS_KEY not set — wake word disabled")
                return False

            sensitivity = [config["audio"]["wake_word_sensitivity"]]

            if CUSTOM_KEYWORD_PATH.exists():
                # Custom 'Hey Aether' keyword trained via console.picovoice.ai
                self._handle = pvporcupine.create(
                    access_key=settings.picovoice_access_key,
                    keyword_paths=[str(CUSTOM_KEYWORD_PATH)],
                    sensitivities=sensitivity,
                )
                logger.info("WakeWord: using custom 'Aether' keyword")
            else:
                # Fallback to built-in 'jarvis' until custom keyword is trained
                self._handle = pvporcupine.create(
                    access_key=settings.picovoice_access_key,
                    keywords=["jarvis"],
                    sensitivities=sensitivity,
                )
                logger.warning(
                    "WakeWord: Custom keyword not found at models/wakeword/Aether_windows.ppn. "
                    "Using built-in 'jarvis' placeholder. "
                    "Train at console.picovoice.ai for production."
                )
            self._frame_length = self._handle.frame_length
            self._sample_rate = self._handle.sample_rate
            logger.info(
                f"WakeWord: Porcupine initialized. "
                f"Frame length: {self._frame_length}, "
                f"Sample rate: {self._sample_rate}Hz"
            )
            return True
        except Exception as e:
            logger.error(f"WakeWord: Porcupine initialization failed: {e}")
            return False

    def process_frame(self, pcm_frame: list[int]) -> bool:
        """Process one PCM frame. Returns True if wake word detected."""
        if self._handle is None:
            return False
        try:
            result = self._handle.process(pcm_frame)
            if result >= 0:
                logger.info(f"WakeWord: DETECTED (keyword index={result})")
                if self._on_detected:
                    self._on_detected()
                return True
            return False
        except Exception as e:
            logger.error(f"WakeWord: process error: {e}")
            return False

    @property
    def frame_length(self) -> int:
        return self._frame_length or 512

    @property
    def sample_rate(self) -> int:
        return self._sample_rate or 16000

    def cleanup(self):
        if self._handle:
            self._handle.delete()
            self._handle = None
            logger.info("WakeWord: Porcupine cleaned up")
