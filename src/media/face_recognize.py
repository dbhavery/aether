"""
Face recognition using InsightFace — identify known people in images.
Used for: "Find that photo with Bryan" type queries.
NOTE: InsightFace has a commercial restriction — personal use only.
"""

import asyncio
from pathlib import Path

import numpy as np
from loguru import logger

from src.shared.config import get_settings

_app = None
_known_embeddings: dict[str, np.ndarray] = {}


def _get_known_faces_dir() -> Path:
    """Resolve known faces directory from config."""
    return Path(get_settings().aether_data_path) / "known_faces"


def _get_app():
    global _app
    if _app is None:
        try:
            import insightface
        except ImportError:
            logger.warning(
                "FaceRecognize: insightface not installed. Install with: pip install insightface onnxruntime-gpu"
            )
            raise
        _app = insightface.app.FaceAnalysis(providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("FaceRecognize: InsightFace initialized")
    return _app


def _load_known_faces():
    global _known_embeddings
    if _known_embeddings:
        return
    known_faces_dir = _get_known_faces_dir()
    if not known_faces_dir.exists():
        logger.warning(f"FaceRecognize: known faces dir not found: {known_faces_dir}")
        return
    import cv2

    app = _get_app()
    for face_file in known_faces_dir.glob("*.jpg"):
        name = face_file.stem
        img = cv2.imread(str(face_file))
        if img is None:
            continue
        faces = app.get(img)
        if faces:
            _known_embeddings[name] = faces[0].normed_embedding
            logger.debug(f"FaceRecognize: loaded embedding for '{name}'")
    logger.info(f"FaceRecognize: loaded {len(_known_embeddings)} known faces")


async def identify_faces_in_image(image_path: str | Path) -> list[str]:
    """Return list of identified person names in the image."""
    try:
        _load_known_faces()
        app = _get_app()
        import cv2

        img = cv2.imread(str(image_path))
        if img is None:
            return []
        faces = await asyncio.to_thread(app.get, img)
        identified = []
        for face in faces:
            emb = face.normed_embedding
            best_match = None
            best_score = 0.0
            for name, known_emb in _known_embeddings.items():
                score = float(np.dot(emb, known_emb))
                if score > best_score and score > 0.4:
                    best_score = score
                    best_match = name
            if best_match:
                identified.append(best_match)
        return identified
    except Exception as e:
        logger.error(f"FaceRecognize: error: {e}")
        return []
