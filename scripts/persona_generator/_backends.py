"""Image-generation backends for the persona generator tools.

Provides a thin shared API that the generator scripts use, falling back
across available providers in order:

    fal (nano-banana-pro) -> GPT Image 1.5 -> Gemini 3 Flash Image

A script requests a square 1024x1024 image for a prompt. Whichever
backend succeeds writes bytes to the given path. Post-processing (resize
to exact dims, strip alpha) is centralised here so generators stay
linear.

Design notes:
    * Env vars: FAL_KEY, OPENAI_API_KEY, GEMINI_API_KEY.
    * Only the PIL dependency is required, so this works against the
      same environment the backend uses (pillow is in requirements.txt).
    * fal is invoked by shelling to the fal-generate skill's CLI
      (`generate.sh`) — we don't re-implement the queue API.
"""

from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image  # type: ignore[import-not-found]  # pillow in requirements.txt


class BackendError(RuntimeError):
    """Raised when every configured backend fails."""


# Path to the fal-generate skill's queue CLI. This is the standard install
# location for Claude Code skills on Windows — if a future session moves
# skills the path must be updated or the FAL branch will skip.
_FAL_SCRIPT = Path(
    os.environ.get(
        "FAL_GENERATE_SH",
        str(Path.home() / ".claude" / "skills" / "fal-generate" / "scripts" / "generate.sh"),
    )
)

# Default fal model for portraits. nano-banana-pro produced the most
# consistent identity + skin texture across aurora/caelum/luma tests.
_FAL_MODEL = os.environ.get("FAL_PORTRAIT_MODEL", "fal-ai/nano-banana-pro")


@dataclass
class GenerationResult:
    """What a backend returns to the caller."""

    path: Path
    backend: str
    model: str
    prompt: str


def generate_square_image(
    prompt: str,
    out_path: Path,
    *,
    size: int = 1024,
    prefer: tuple[str, ...] = ("fal", "openai", "gemini"),
) -> GenerationResult:
    """Generate a square image and save to `out_path`.

    Tries the backends in `prefer` order. First success writes the bytes
    to disk (resized to `size` x `size` if the backend returned a slightly
    different resolution) and returns a GenerationResult.

    Args:
        prompt: Full prompt text.
        out_path: Destination PNG path. Parent directories must exist.
        size: Target square dimension. Defaults to 1024.
        prefer: Backend order. Use to pin a specific provider.

    Raises:
        BackendError: Every configured backend failed or was unavailable.
    """
    if out_path.parent and not out_path.parent.exists():
        raise ValueError(f"parent directory does not exist: {out_path.parent}")

    errors: list[str] = []
    for name in prefer:
        try:
            if name == "fal":
                bytes_ = _generate_fal(prompt)
                model = _FAL_MODEL
            elif name == "openai":
                bytes_ = _generate_openai(prompt, size=size)
                model = "gpt-image-1.5"
            elif name == "gemini":
                bytes_ = _generate_gemini(prompt)
                model = "gemini-3.1-flash-image-preview"
            else:
                errors.append(f"{name}: unknown backend")
                continue
        except _BackendUnavailable as exc:
            errors.append(f"{name}: unavailable — {exc}")
            continue
        except Exception as exc:  # pragma: no cover — surfaced to caller
            errors.append(f"{name}: {exc}")
            continue

        _write_normalised_square(bytes_, out_path, size=size)
        return GenerationResult(path=out_path, backend=name, model=model, prompt=prompt)

    raise BackendError(
        "no image backend succeeded:\n    " + "\n    ".join(errors)
    )


# ---------------------------------------------------------------------------
# Internals.
# ---------------------------------------------------------------------------


class _BackendUnavailable(RuntimeError):
    """Soft failure — try the next backend."""


def _generate_fal(prompt: str) -> bytes:
    """Call fal via the skill's generate.sh and return the downloaded image bytes.

    Falls back gracefully when the account balance is exhausted (the API
    returns a specific string we sniff for so the caller can try GPT).
    """
    if not os.environ.get("FAL_KEY"):
        raise _BackendUnavailable("FAL_KEY not set")
    if not _FAL_SCRIPT.exists():
        raise _BackendUnavailable(f"fal-generate skill script missing at {_FAL_SCRIPT}")

    completed = subprocess.run(
        [
            "bash",
            str(_FAL_SCRIPT),
            "--prompt",
            prompt,
            "--model",
            _FAL_MODEL,
            "--size",
            "square",
            "--num-images",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = completed.stdout + "\n" + completed.stderr
    if "Exhausted balance" in output or "User is locked" in output:
        raise _BackendUnavailable("fal balance exhausted")
    if completed.returncode != 0:
        raise RuntimeError(
            f"fal-generate returned {completed.returncode}: {output.strip()[:400]}"
        )

    # Parse the last JSON block in stdout — the skill prints the final
    # response at the tail. Be defensive: fall back to regex-finding a URL.
    url = _extract_image_url(output)
    if not url:
        raise RuntimeError(
            f"fal-generate produced no recognisable image URL:\n{output.strip()[:600]}"
        )
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def _generate_openai(prompt: str, *, size: int) -> bytes:
    """Call OpenAI Images API with gpt-image-1.5 and return PNG bytes."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise _BackendUnavailable("OPENAI_API_KEY not set")

    supported = {1024, 1536, 2048}
    api_size = 1024 if size not in supported else size
    payload = json.dumps(
        {
            "model": "gpt-image-1.5",
            "prompt": prompt,
            "n": 1,
            "size": f"{api_size}x{api_size}",
            "output_format": "png",
            "quality": "high",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())
    if "data" not in result or not result["data"]:
        raise RuntimeError(f"openai image response malformed: {str(result)[:400]}")

    item = result["data"][0]
    if "b64_json" in item:
        return base64.b64decode(item["b64_json"])
    if "url" in item:
        with urllib.request.urlopen(item["url"], timeout=120) as resp:
            return resp.read()
    raise RuntimeError(f"openai image response missing b64_json/url: {str(item)[:400]}")


def _generate_gemini(prompt: str) -> bytes:
    """Call Gemini 3 Flash Image and return PNG bytes."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise _BackendUnavailable("GEMINI_API_KEY not set")

    model = "gemini-3.1-flash-image-preview"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={key}"
    )
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "temperature": 0.7,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "aether-persona-generator/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        result = json.loads(resp.read())
    parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        if "inlineData" in part and part["inlineData"].get("data"):
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError(
        f"gemini image response had no inline image data: {str(result)[:400]}"
    )


def _extract_image_url(output: str) -> str | None:
    """Find the first fal-CDN image URL in mixed stdout/stderr text."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{") and "images" in line:
            # JSON blob — parse it.
            try:
                blob = json.loads(line)
            except json.JSONDecodeError:
                continue
            images = blob.get("images") or blob.get("image") or []
            if isinstance(images, list) and images and isinstance(images[0], dict):
                return images[0].get("url")
        if "v3.fal.media" in line and ".png" in line.lower():
            # Fallback: scrape first URL-shaped token containing fal.media.
            for token in line.split():
                if "fal.media" in token and "." in token:
                    return token.strip().strip('",')
    return None


def _write_normalised_square(raw: bytes, out_path: Path, *, size: int) -> None:
    """Ensure the saved PNG is exactly `size` x `size` square RGB.

    The schema's aspect tolerance is ±10% but keeping a hard `size x size`
    guarantees every downstream tool (LivePortrait, wizard thumbnail) gets
    a predictable input. Alpha channels are flattened to white because
    LivePortrait expects opaque source.
    """
    img = Image.open(io.BytesIO(raw))
    # Flatten alpha to white if present; keeps loader's opacity assumption.
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    if img.size != (size, size):
        # Crop to square from center if non-square, then resize.
        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((size, size), Image.LANCZOS)

    img.save(out_path, format="PNG", optimize=True)


def main(argv: list[str]) -> int:  # pragma: no cover — ad-hoc smoke test
    if len(argv) < 3:
        print("usage: _backends.py <prompt> <out_path>", file=sys.stderr)
        return 2
    prompt = argv[1]
    out = Path(argv[2])
    result = generate_square_image(prompt, out)
    print(f"{result.backend}:{result.model} -> {result.path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))


__all__ = [
    "BackendError",
    "GenerationResult",
    "generate_square_image",
]
