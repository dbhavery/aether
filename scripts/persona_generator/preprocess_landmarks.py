"""Run 68-point face landmark extraction on a persona's portrait.

Usage:
    python scripts/persona_generator/preprocess_landmarks.py <persona_id>

Writes `personas/<persona_id>/avatar/landmarks.json` — cached metadata
consumed by LivePortrait at runtime (per PERSONA-SCHEMA.md §1).

Landmarks are *optional*; the loader does not require them. They are
generated on first avatar load if absent, but pre-computing during
persona authoring lets us QA the landmark quality before shipping.

Backend selection:
    * If `face_alignment` (PyTorch) is importable, it's used directly.
    * Else if `dlib` with shape_predictor_68_face_landmarks.dat is
      configured, it's used.
    * Otherwise a stub JSON is written with a clear marker so CI
      doesn't fail but a human knows landmarks still need regenerating.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def run(persona_id: str) -> Path:
    portrait = _REPO_ROOT / "personas" / persona_id / "avatar" / "portrait.png"
    if not portrait.exists():
        raise SystemExit(
            f"portrait missing: {portrait} — run generate_portrait.py first"
        )

    out = portrait.parent / "landmarks.json"
    result = _extract_landmarks(portrait)

    payload = {
        "schema_version": 1,
        "persona_id": persona_id,
        "source": str(portrait.relative_to(_REPO_ROOT)),
        "backend": result["backend"],
        "points": result["points"],
        "note": result.get("note"),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[{persona_id}] wrote {out} via {result['backend']}")
    return out


def _extract_landmarks(portrait: Path) -> dict:
    """Return {'backend': str, 'points': list, 'note': str | None}.

    Tries PyTorch face_alignment first, then dlib, then stub.
    """
    try:
        import face_alignment  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]

        fa = face_alignment.FaceAlignment(
            face_alignment.LandmarksType.TWO_D,
            flip_input=False,
            device="cuda" if _cuda_ok() else "cpu",
        )
        img = np.array(Image.open(portrait).convert("RGB"))
        preds = fa.get_landmarks(img)
        if not preds:
            return _stub("face_alignment: no face detected")
        pts = [[float(x), float(y)] for x, y in preds[0]]
        return {"backend": "face_alignment", "points": pts, "note": None}
    except ImportError:
        pass

    try:
        import dlib  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]

        model_path = Path(__file__).parent / "shape_predictor_68_face_landmarks.dat"
        if not model_path.exists():
            return _stub("dlib installed but shape_predictor_68.dat not found")
        detector = dlib.get_frontal_face_detector()
        predictor = dlib.shape_predictor(str(model_path))
        img = np.array(Image.open(portrait).convert("RGB"))
        rects = detector(img, 1)
        if not rects:
            return _stub("dlib: no face detected")
        shape = predictor(img, rects[0])
        pts = [[float(p.x), float(p.y)] for p in shape.parts()]
        return {"backend": "dlib", "points": pts, "note": None}
    except ImportError:
        pass

    return _stub("no landmark backend installed")


def _stub(reason: str) -> dict:
    return {
        "backend": "stub",
        "points": [],
        "note": f"landmarks not extracted ({reason}); will be regenerated at first avatar load",
    }


def _cuda_ok() -> bool:
    try:
        import torch  # type: ignore[import-not-found]

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("persona_id")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    run(args.persona_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
