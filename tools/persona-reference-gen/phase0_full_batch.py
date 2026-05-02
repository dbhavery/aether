"""Larger Phase 0 batch — recipe-locked at 1:2 aspect.

After the 1:2 aspect-ratio probe established the recipe (1024×2048 +
sequential offload → ~80% body coverage + pose variation + strong
identity), this driver runs a real curation-grade batch:

  4 framings × 1 lighting × 4 seeds = 16 images

Wall clock: ~80 min with warm pipeline cache (~5 min per inference at
1024×2048 + per-image VAE). Output is the curation set Don walks
through to pick training images for Phase 3 LoRA.
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
        prog="phase0-full-batch",
        description=(
            "Recipe-locked Phase 0 batch at 1:2 aspect ratio. Produces "
            "16 candidates (4 framings × 4 seeds) for Don's curation."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True)
    parser.add_argument(
        "--aspect-ratio",
        default="1:2",
        help="aspect-ratio key — defaults to 1:2 per the probe finding",
    )
    args = parser.parse_args(argv)

    axes = MatrixAxes(
        framings=DEFAULT_FRAMINGS,
        lightings=(DEFAULT_LIGHTINGS[0],),
        seeds=DEFAULT_SEEDS,
    )

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        axes=axes,
        backend="local-flux",
        aspect_ratio=args.aspect_ratio,
        notes=(
            f"Phase 0 full curation batch — recipe-locked at "
            f"{args.aspect_ratio}. 4 framings × 4 seeds = 16 candidates."
        ),
    )

    print(
        f"[full-batch] persona={args.persona} batch={args.batch} "
        f"aspect={args.aspect_ratio} prompts={len(manifest.prompts)} "
        f"candidates={len(manifest.candidates)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
