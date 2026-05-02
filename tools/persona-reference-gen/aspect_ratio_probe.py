"""Probe — extreme vertical aspect ratio to force full-body output.

After 8/9 framing fails on default + aggressive prompt language,
the bare-metal pivot's last cheap prompt-side experiment is whether
DOUBLING the vertical pixel area (1024x2048 = 1:2) forces FLUX to
fill more of the frame with body content.

Generates 2 images at 1024x2048 with the first DEFAULT_FRAMINGS
entry. Cheap (~10 min wall clock with warm cache). If 1/2 produces
full-body, we have a winning recipe; if 0/2, prompts are
definitively dead and we move to inpainting / body extension.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from prompt_matrix import (  # noqa: E402
    DEFAULT_FRAMINGS,
    DEFAULT_LIGHTINGS,
    DEFAULT_SEEDS,
    MatrixAxes,
)
from runner import run_batch  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aspect-ratio-probe",
        description=(
            "Test extreme vertical aspect ratio (1:2 = 1024×2048) to force "
            "full-body output. 2 images, ~7 min inference (warm cache)."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--aspect-ratio",
        default="1:2",
        help="aspect ratio key — defaults to extreme vertical 1:2 (1024×2048)",
    )
    args = parser.parse_args(argv)

    # Two seeds for variation; one framing for clarity.
    axes = MatrixAxes(
        framings=(DEFAULT_FRAMINGS[0],),
        lightings=(DEFAULT_LIGHTINGS[0],),
        seeds=(DEFAULT_SEEDS[0], DEFAULT_SEEDS[1]),
    )

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        axes=axes,
        backend="local-flux",
        aspect_ratio=args.aspect_ratio,
        notes=(
            f"Aspect-ratio probe — {args.aspect_ratio}. Tests whether "
            "doubling vertical pixel area escapes FLUX framing bias."
        ),
    )

    print(
        f"[aspect-probe] persona={args.persona} batch={args.batch} "
        f"aspect={args.aspect_ratio} prompts={len(manifest.prompts)} "
        f"candidates={len(manifest.candidates)}"
    )
    for c in manifest.candidates:
        print(f"  image: personas/{args.persona}/_pipeline/step1_references/{args.batch}/{c.image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
