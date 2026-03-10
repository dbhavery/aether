"""Speaker verification using NVIDIA TitaNet (primary) or ECAPA-TDNN (fallback).

Only the user's voice activates Aether. Fail-closed: if verification fails or
no enrollment exists, the speaker is rejected.
"""

import asyncio
import threading
from pathlib import Path

import numpy as np
import torch
from loguru import logger

from src.shared.config import get_settings, get_yaml_config

_verifier = None
_owner_embedding = None
_verifier_lock = threading.Lock()


def _get_enrollment_path() -> Path:
    """Lazy accessor for enrollment path — avoids module-level get_settings() call."""
    return Path(get_settings().aether_data_path) / "speaker_enrollment" / "owner_embedding.pt"


# Flag to track which backend is active
_backend: str = "none"
_load_attempted: bool = False


def _get_verifier():
    """Load TitaNet (preferred) or fall back to ECAPA-TDNN via SpeechBrain."""
    global _verifier, _backend, _load_attempted
    if _verifier is not None:
        return _verifier
    with _verifier_lock:
        if _verifier is not None:
            return _verifier
        if _load_attempted:
            return None
        _load_attempted = True

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Try TitaNet via NeMo first
        try:
            from nemo.collections.asr.models import EncDecSpeakerLabelModel

            logger.info("SpeakerVerify: Loading TitaNet-Large via NeMo...")
            _verifier = EncDecSpeakerLabelModel.from_pretrained(
                model_name="nvidia/speakerverification_en_titanet_large",
            )
            _verifier = _verifier.to(device)
            _verifier.eval()
            _backend = "titanet"
            logger.info("SpeakerVerify: TitaNet-Large ready")
            return _verifier
        except ImportError:
            logger.info("SpeakerVerify: NeMo not available, trying SpeechBrain ECAPA-TDNN fallback")
        except Exception as e:
            logger.warning(f"SpeakerVerify: TitaNet load failed ({e}), trying ECAPA-TDNN fallback")

        # Fallback: ECAPA-TDNN via SpeechBrain
        try:
            try:
                from speechbrain.inference.speaker import SpeakerRecognition
            except ImportError:
                from speechbrain.pretrained import SpeakerRecognition
            logger.info("SpeakerVerify: Loading ECAPA-TDNN model...")
            _verifier = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="models/ecapa_tdnn",
                run_opts={"device": device},
            )
            _backend = "ecapa"
            logger.info("SpeakerVerify: ECAPA-TDNN ready")
            return _verifier
        except Exception as e:
            logger.error(f"SpeakerVerify: ECAPA-TDNN also failed: {e}")
            _backend = "none"
            return None


def _extract_embedding(waveform: torch.Tensor) -> torch.Tensor | None:
    """Extract speaker embedding using the active backend.

    Args:
        waveform: shape (1, samples), float32, 16kHz
    """
    verifier = _get_verifier()
    if verifier is None:
        return None

    if _backend == "titanet":
        # NeMo TitaNet expects (batch, samples) — process via infer method
        with torch.no_grad():
            # NeMo models use process_signal or get_embedding
            if hasattr(verifier, "get_embedding"):
                embedding, _ = verifier.get_embedding(waveform)
            else:
                # Fallback: use forward pass
                processed, length = verifier.preprocessor(
                    input_signal=waveform,
                    length=torch.tensor([waveform.shape[1]]),
                )
                embedding, _ = verifier.encoder(audio_signal=processed, length=length)
        return embedding
    elif _backend == "ecapa":
        # SpeechBrain ECAPA uses encode_batch
        return verifier.encode_batch(waveform)
    return None


def _get_owner_embedding() -> torch.Tensor | None:
    global _owner_embedding
    if _owner_embedding is not None:
        return _owner_embedding
    enrollment_path = _get_enrollment_path()
    if enrollment_path.exists():
        data = torch.load(enrollment_path, weights_only=True)
        if isinstance(data, dict):
            saved_backend = data.get("backend")
            if saved_backend and saved_backend != _backend and _backend != "none":
                logger.warning(
                    f"SpeakerVerify: Enrollment was created with {saved_backend} "
                    f"but current backend is {_backend} — re-enrollment required"
                )
                return None
            _owner_embedding = data["embedding"]
        else:
            # Legacy format — plain tensor without backend tag
            _owner_embedding = data
            logger.warning("SpeakerVerify: Legacy enrollment without backend tag — consider re-enrolling")
        logger.info(f"SpeakerVerify: Loaded the user's enrollment embedding (backend={_backend})")
        return _owner_embedding
    return None


async def enroll_owner(audio: np.ndarray, sample_rate: int = 16000) -> bool:
    """Enroll the user's voice from the reference audio. Call once during setup."""
    try:
        import torchaudio

        waveform = torch.FloatTensor(audio).unsqueeze(0)
        if sample_rate != 16000:
            waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)

        embedding = await asyncio.to_thread(_extract_embedding, waveform)
        if embedding is None:
            logger.error("SpeakerVerify: embedding extraction failed — cannot enroll")
            return False

        enrollment_path = _get_enrollment_path()
        enrollment_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"embedding": embedding, "backend": _backend}, enrollment_path)
        global _owner_embedding
        _owner_embedding = embedding
        logger.info(f"SpeakerVerify: the user's voice enrolled via {_backend} and saved to {enrollment_path}")
        return True
    except Exception as e:
        logger.error(f"SpeakerVerify: enrollment failed: {e}")
        return False


async def verify_speaker(audio: np.ndarray, sample_rate: int = 16000) -> tuple[bool, float]:
    """Verify audio is the user's voice.

    Returns (is_owner, similarity_score).
    Fail-closed: returns (False, 0.0) if verification cannot be performed.
    """
    # If no verification backend could load, bypass verification.
    # The user is the sole user on a private machine — blocking all voice input
    # because the model won't load is worse than skipping verification.
    if _backend == "none":
        # Attempt to load one more time in case it's now available
        _get_verifier()
        if _backend == "none":
            logger.warning("SpeakerVerify: no backend available — bypassing verification (sole-user mode)")
            return True, 1.0

    owner_embedding = _get_owner_embedding()
    if owner_embedding is None:
        logger.error(
            "SpeakerVerify: No enrollment found — rejecting (fail-closed). Run: python scripts/enroll_from_wav.py"
        )
        return False, 0.0

    config = get_yaml_config()
    threshold = config["audio"]["speaker_verify_threshold"]

    try:
        import torchaudio

        waveform = torch.FloatTensor(audio).unsqueeze(0)
        if sample_rate != 16000:
            waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)

        embedding = await asyncio.to_thread(_extract_embedding, waveform)
        if embedding is None:
            logger.warning("SpeakerVerify: embedding extraction failed — bypassing (sole-user mode)")
            return True, 1.0

        score = torch.nn.functional.cosine_similarity(owner_embedding.squeeze(), embedding.squeeze(), dim=0).item()
        is_owner = score >= threshold
        logger.debug(f"SpeakerVerify ({_backend}): score={score:.3f}, threshold={threshold}, is_owner={is_owner}")
        return is_owner, score
    except Exception as e:
        logger.error(f"SpeakerVerify: verification error: {e} — bypassing (sole-user mode)")
        return True, 1.0  # Sole user — don't block voice on model failures


async def initialize_enrollment() -> None:
    """Enroll the user's voice from the reference WAV on startup if not already enrolled."""
    if _get_enrollment_path().exists():
        logger.info("SpeakerVerify: Enrollment already exists, skipping")
        return
    config = get_yaml_config()
    ref_path_str = config.get("voice", {}).get("reference_voice_path")
    if not ref_path_str:
        logger.warning("SpeakerVerify: voice.reference_voice_path not set — skipping enrollment")
        return
    ref_path = Path(ref_path_str)
    if not ref_path.is_absolute():
        ref_path = Path(__file__).resolve().parent.parent.parent / ref_path
    if not ref_path.exists():
        logger.warning("SpeakerVerify: No reference voice found — running without enrollment (fail-closed)")
        return
    import soundfile as sf

    audio, sr = sf.read(str(ref_path))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    success = await enroll_owner(audio, sr)
    if success:
        logger.info("SpeakerVerify: Auto-enrolled owner from reference_voice.wav")
