"""Body extension via FLUX outpainting.

When prompts can't escape FLUX's portrait-crop bias (see
2026-05-02-prompt-eng-probe EVALUATION.md), the alternative is to
take a 3/4 body or portrait crop and physically extend the canvas
downward, then inpaint the extension with body continuation. The
result is a synthetic full-body image suitable for Phase 3 LoRA
training.

Stack: `diffusers.FluxInpaintPipeline` on top of the regular
`black-forest-labs/FLUX.1-dev` checkpoint (no separate Fill model
download). Sequential offload by default for tight VRAM.

Pattern:

    input.png (1024×1536, head-to-waist)
    ↓ pad downward → 1024×2048 (head-to-waist + gray padding)
    ↓ mask: original area = 0, padding = 1
    ↓ FluxInpaintPipeline(image, mask, prompt="full body continuation, ...")
    ↓ output.png (1024×2048, head-to-feet)

Stub mode (no `PERSONA_REFGEN_LIVE=1`) writes a vertically-padded
copy of the input as a deterministic placeholder so downstream
tools can be exercised without GPU.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from backend_local_flux import (  # noqa: E402
    LIVE_ENV_VAR,
    OFFLOAD_ENV_VAR,
    is_live_mode,
)


DEFAULT_MODEL = "black-forest-labs/FLUX.1-dev"

# Default extension settings — empirically reasonable for a 1024×1536
# input becoming 1024×2048 (added 512px of body extension below). Bigger
# extensions (1024×2304+) increase the chance of artifacts at the seam.
DEFAULT_EXTEND_DOWN = 512
DEFAULT_EXTEND_TARGET_WIDTH = 1024

DEFAULT_EXTENSION_PROMPT = (
    "full body continuation, photorealistic, dark slim jeans, casual "
    "shoes, feet visible, standing on hardwood floor, natural lighting, "
    "85mm lens, no airbrushing, natural skin texture"
)
"""Aurora-tuned default. Override per-persona via CLI arg."""

DEFAULT_NEGATIVE_PROMPT = (
    "headshot, bust crop, cartoon, anime, 3d render, plastic skin, "
    "magenta gradient background, deformed, extra fingers, low resolution"
)

# Process-local cached pipeline.
_PIPELINE: object | None = None


@dataclass
class ExtensionResult:
    output_path: Path
    backend: str
    seed: int
    width: int
    height: int


def _load_inpaint_pipeline(model: str):
    """Lazy-load `FluxInpaintPipeline`. Cached process-locally."""
    global _PIPELINE
    if _PIPELINE is not None:
        return _PIPELINE

    import torch  # noqa: PLC0415
    from diffusers import FluxInpaintPipeline  # noqa: PLC0415

    pipe = FluxInpaintPipeline.from_pretrained(model, torch_dtype=torch.float16)
    strategy = os.environ.get(OFFLOAD_ENV_VAR, "").strip().lower() or "sequential"
    if strategy == "model":
        pipe.enable_model_cpu_offload()
    elif strategy == "none":
        pipe.to("cuda")
    else:
        pipe.enable_sequential_cpu_offload()
    _PIPELINE = pipe
    return pipe


def _prepare_canvas(
    src_path: Path,
    *,
    extend_down: int,
    target_width: int,
):
    """Open `src_path`, scale to target_width, pad bottom with gray.

    Returns (image, mask) — both PIL.Image. Mask is white in the padded
    region and black in the original region (FLUX inpainting convention).
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    src = Image.open(src_path).convert("RGB")
    if src.size[0] != target_width:
        new_h = int(src.size[1] * target_width / src.size[0])
        src = src.resize((target_width, new_h), Image.LANCZOS)

    canvas = Image.new(
        "RGB",
        (target_width, src.size[1] + extend_down),
        color=(127, 127, 127),
    )
    canvas.paste(src, (0, 0))

    mask = Image.new("L", canvas.size, color=0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(
        [(0, src.size[1]), (canvas.size[0], canvas.size[1])],
        fill=255,
    )
    return canvas, mask


def _stub_extend(src_path: Path, out_path: Path, extend_down: int, target_width: int) -> ExtensionResult:
    """Free + offline path: write a vertically-padded copy of the input.

    The padding region is gray (deterministic) so downstream tools can
    be exercised without GPU. Mirrors the live-path output shape so
    callers stay backend-agnostic.
    """
    canvas, _mask = _prepare_canvas(
        src_path, extend_down=extend_down, target_width=target_width,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return ExtensionResult(
        output_path=out_path,
        backend="stub",
        seed=0,
        width=canvas.size[0],
        height=canvas.size[1],
    )


def extend_to_full_body(
    src_path: Path,
    out_path: Path,
    *,
    extension_prompt: str = DEFAULT_EXTENSION_PROMPT,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    seed: int = 7777,
    extend_down: int = DEFAULT_EXTEND_DOWN,
    target_width: int = DEFAULT_EXTEND_TARGET_WIDTH,
    steps: int = 28,
    guidance_scale: float = 30.0,
    strength: float = 1.0,
    model: str = DEFAULT_MODEL,
) -> ExtensionResult:
    """Inpaint the bottom-padded region of `src_path` with a body extension.

    Live mode loads FluxInpaintPipeline and runs inference. Stub mode
    writes the gray-padded source as a deterministic placeholder.
    """
    if not is_live_mode():
        return _stub_extend(src_path, out_path, extend_down, target_width)

    import torch  # noqa: PLC0415

    pipe = _load_inpaint_pipeline(model)
    canvas, mask = _prepare_canvas(
        src_path, extend_down=extend_down, target_width=target_width,
    )
    width, height = canvas.size

    generator = torch.Generator(device="cuda").manual_seed(seed)
    image = pipe(
        prompt=extension_prompt,
        image=canvas,
        mask_image=mask,
        height=height,
        width=width,
        num_inference_steps=steps,
        guidance_scale=guidance_scale,
        strength=strength,
        generator=generator,
    ).images[0]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return ExtensionResult(
        output_path=out_path,
        backend=f"local-flux-inpaint/{model}",
        seed=seed,
        width=width,
        height=height,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="body-extension",
        description=(
            "Extend a 3/4 body / portrait crop downward via FLUX inpainting "
            "to produce a synthetic full-body image. Used to bootstrap "
            "Phase 3 LoRA training data when prompt engineering can't "
            "escape FLUX's portrait-crop bias."
        ),
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prompt", default=DEFAULT_EXTENSION_PROMPT)
    parser.add_argument("--negative-prompt", default=DEFAULT_NEGATIVE_PROMPT)
    parser.add_argument("--seed", type=int, default=7777)
    parser.add_argument("--extend-down", type=int, default=DEFAULT_EXTEND_DOWN)
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--guidance-scale", type=float, default=30.0)
    parser.add_argument("--strength", type=float, default=1.0)
    args = parser.parse_args(argv)

    result = extend_to_full_body(
        src_path=args.input,
        out_path=args.output,
        extension_prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        extend_down=args.extend_down,
        steps=args.steps,
        guidance_scale=args.guidance_scale,
        strength=args.strength,
    )

    mode = "LIVE" if is_live_mode() else "STUB"
    print(
        f"[body-extension] {mode} backend={result.backend} "
        f"in={args.input} out={result.output_path} "
        f"dims={result.width}x{result.height} seed={result.seed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
