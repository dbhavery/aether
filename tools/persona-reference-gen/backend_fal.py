"""fal.ai adapter for the reference-image batch runner.

Mirrors the style of `scripts/persona_generator/generate_anchor_set.py` but
keeps a clean dependency boundary: this module never imports from `scripts/`
(scripts are run-as-script, not importable as a stable surface).

Live calls are gated behind the `PERSONA_REFGEN_LIVE` environment variable
so the default `pytest` run does not burn fal.ai credits. When the gate is
off, the backend writes a 1×1 PNG placeholder + a stub-shaped result so the
manifest pipeline still round-trips end-to-end.

Model default: `fal-ai/flux-pro/v1.1-ultra` (matches the v0 anchor-set
runs). RealVisXL Lightning is referenced in ADR-0015 as the alternate
primitive; switching to it is a one-line constant change here once the
fal.ai endpoint id is locked.
"""

from __future__ import annotations

import os
import struct
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "fal-ai/flux-pro/v1.1-ultra"
DEFAULT_ASPECT = "9:16"  # vertical full-body framing — doctrine §5
"""9:16 (vertical) is the default: doctrine §5 requires full-body, head-to-feet.
A vertical aspect captures that with less wasted side-bleed than 16:9. Override
via the runner CLI if a wider environmental context is wanted."""

MODEL_PULID = "fal-ai/flux-pulid"
"""Identity-conditioned FLUX. Takes a `reference_image_url` (e.g. the
persona's `personas/<slug>/avatar/anchor.png`) and locks the candidate's
face identity to it. Locked-recipe path for ADR-0014 Step 1 once the
hardening pass lands. Pricing: $0.0333 per megapixel."""

LIVE_ENV_VAR = "PERSONA_REFGEN_LIVE"


@dataclass
class FalResult:
    """Backend-agnostic generation result. Field names match output_schema
    `Candidate` so the runner can map directly."""

    image_path: Path
    backend: str
    backend_request_id: str | None
    backend_source_url: str | None


def is_live_mode() -> bool:
    """True if the env var gate is set to a truthy value."""
    val = os.environ.get(LIVE_ENV_VAR, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _write_stub_png(path: Path, *, seed: int) -> None:
    """Write a deterministic minimal valid PNG to `path`.

    A 1×1 grayscale PNG keyed off `seed` so that different seeds produce
    different file bytes (helps assert determinism in tests). No external
    dependency on Pillow.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 1×1 grayscale, value derived from seed.
    pixel = bytes([seed % 256])
    raw = b"\x00" + pixel  # filter byte + 1 pixel
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    ihdr_chunk = _png_chunk(b"IHDR", ihdr)
    idat_chunk = _png_chunk(b"IDAT", zlib.compress(raw))
    iend_chunk = _png_chunk(b"IEND", b"")
    path.write_bytes(sig + ihdr_chunk + idat_chunk + iend_chunk)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def upload_reference_image(local_path: Path) -> str:
    """Upload `local_path` to fal storage and return its public URL.

    Used to feed the persona's anchor image into PuLID once per batch
    (the URL is reused across every prompt). Live-only — there is no
    stub for storage uploads since the URL is not consulted in stub
    mode (`_generate_stub` ignores `reference_image_url`).
    """
    try:
        import fal_client  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — environment-specific
        raise RuntimeError(
            "upload_reference_image requires `fal_client` to be installed."
        ) from exc
    return fal_client.upload_file(str(local_path))


def generate(
    *,
    prompt_text: str,
    negative_prompt: str,
    seed: int,
    out_path: Path,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT,
    reference_image_url: str | None = None,
) -> FalResult:
    """Generate one image. Live or stub depending on env gate.

    The stub path is deterministic and free; the live path requires
    `FAL_KEY` and burns credits. Both return the same FalResult shape.

    `reference_image_url` is forwarded to identity-conditioned models
    (e.g. PuLID). Ignored by text-only models like
    `fal-ai/flux-pro/v1.1-ultra`. Stub ignores it but accepts the
    parameter so callers can stay model-agnostic.
    """
    if not is_live_mode():
        return _generate_stub(
            prompt_text=prompt_text,
            seed=seed,
            out_path=out_path,
            model=model,
        )
    return _generate_live(
        prompt_text=prompt_text,
        negative_prompt=negative_prompt,
        seed=seed,
        out_path=out_path,
        model=model,
        aspect_ratio=aspect_ratio,
        reference_image_url=reference_image_url,
    )


def _generate_stub(
    *,
    prompt_text: str,
    seed: int,
    out_path: Path,
    model: str,
) -> FalResult:
    _ = prompt_text  # logged by runner; not needed for stub bytes
    _write_stub_png(out_path, seed=seed)
    return FalResult(
        image_path=out_path,
        backend="stub",
        backend_request_id=f"stub-{seed}",
        backend_source_url=None,
    )


def _generate_live(
    *,
    prompt_text: str,
    negative_prompt: str,
    seed: int,
    out_path: Path,
    model: str,
    aspect_ratio: str,
    reference_image_url: str | None = None,
) -> FalResult:
    """Live fal.ai call. Imported lazily so stub/test runs never need fal_client.

    Argument shape diverges by model family:

    - **text-only** (default `fal-ai/flux-pro/v1.1-ultra`): uses
      `aspect_ratio` + optional `negative_prompt`.
    - **identity-conditioned** (`fal-ai/flux-pulid`): uses
      `reference_image_url` for face/body identity lock; PuLID does not
      take `aspect_ratio` or `negative_prompt` in its v0 schema, so we
      skip them.
    """
    try:
        import fal_client  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — environment-specific
        raise RuntimeError(
            "PERSONA_REFGEN_LIVE is set but `fal_client` is not installed. "
            "Install per scripts/persona_generator/README.md."
        ) from exc

    is_pulid = model == MODEL_PULID
    arguments: dict[str, object] = {
        "prompt": prompt_text,
        "num_images": 1,
        "enable_safety_checker": False,
        "output_format": "png",
        "seed": seed,
    }
    if is_pulid:
        if not reference_image_url:
            raise RuntimeError(
                f"{MODEL_PULID} requires reference_image_url; pass --use-pulid "
                "to the runner so it uploads the persona anchor before calling."
            )
        arguments["reference_image_url"] = reference_image_url
    else:
        arguments["aspect_ratio"] = aspect_ratio
        if negative_prompt:
            arguments["negative_prompt"] = negative_prompt

    result = fal_client.subscribe(model, arguments=arguments, with_logs=False)
    images = result.get("images") if isinstance(result, dict) else None
    if not images:
        raise RuntimeError(f"fal.ai returned no images for seed={seed}")
    url = images[0]["url"]
    request_id = result.get("request_id") if isinstance(result, dict) else None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp, out_path.open("wb") as f:  # noqa: S310 — known fal.ai URL
        f.write(resp.read())

    return FalResult(
        image_path=out_path,
        backend=f"fal.ai/{model}",
        backend_request_id=str(request_id) if request_id else None,
        backend_source_url=url,
    )
