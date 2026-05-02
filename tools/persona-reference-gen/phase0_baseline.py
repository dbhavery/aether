"""One-off driver — Phase 0 unaided FLUX.1-dev baseline image.

Bare-metal pivot Phase 0 per
HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md. Generates a single
Aurora full-body image with no identity locking — establishes ground
truth for unaided FLUX quality on Don's RTX 3090 Ti before adding
the local-PuLID identity layer in Phase 1.

Lives separately from runner.py because it intentionally trims the
matrix axes to 1×1×1 (one framing × one lighting × one seed) — that's
not a useful default for the runner CLI, but it is the right shape
for "let's see what one frame looks like" baselines.

Usage (live, runs FLUX on the GPU):

    PERSONA_REFGEN_LIVE=1 python tools/persona-reference-gen/phase0_baseline.py \\
        --persona aurora --batch 2026-05-02-phase0

Set PERSONA_REFGEN_OFFLOAD=sequential to force the small-VRAM offload
path (~3-4 GB peak GPU); without override the loader auto-picks based
on free VRAM.

Stub mode (no env var) is honoured — useful for re-verifying the
runner glue without burning GPU cycles.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from prompt_matrix import (  # noqa: E402  — sys.path mutation above is intentional
    DEFAULT_FRAMINGS,
    DEFAULT_LIGHTINGS,
    DEFAULT_SEEDS,
    MatrixAxes,
)
from runner import run_batch  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="phase0-baseline",
        description=(
            "Generate ONE unaided FLUX.1-dev baseline image for a persona. "
            "Phase 0 of the bare-metal local inference pivot. No identity "
            "locking — just the persona's anchor prompt + the first default "
            "framing/lighting/seed combination."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True, help="batch id, e.g. 2026-05-02-phase0")
    parser.add_argument(
        "--framing",
        default=DEFAULT_FRAMINGS[0],
        help=f"single framing string (default: first DEFAULT_FRAMINGS entry — {DEFAULT_FRAMINGS[0]!r})",
    )
    parser.add_argument(
        "--lighting",
        default=DEFAULT_LIGHTINGS[0],
        help="single lighting string (default: first DEFAULT_LIGHTINGS entry)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEEDS[0])
    args = parser.parse_args(argv)

    axes = MatrixAxes(
        framings=(args.framing,),
        lightings=(args.lighting,),
        seeds=(args.seed,),
    )

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        axes=axes,
        backend="local-flux",
        notes=(
            "Phase 0 baseline — local FLUX.1-dev unaided, no identity "
            "locking. Establishes ground truth for unaided quality on the "
            "3090 Ti per HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md."
        ),
    )

    print(
        f"[phase0] persona={args.persona} batch={args.batch} "
        f"prompts={len(manifest.prompts)} candidates={len(manifest.candidates)} "
        f"backend={manifest.backend}"
    )
    for c in manifest.candidates:
        print(f"  image: personas/{args.persona}/_pipeline/step1_references/{args.batch}/{c.image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
