"""Probe — aggressive framing language to escape FLUX prior bias.

Phase 0 baseline + framing probe established that FLUX's default
behaviour pulls toward 3/4 body / portrait crops even with explicit
"full-body, head to feet visible" framing. This driver tests
escalating framing-prompt language to find what (if anything) escapes
that bias.

Each variant is a known-effective trick from the FLUX community:

  V1 — distance: "shot from 5 meters away, full body in frame"
  V2 — lens: "wide angle 24mm photograph, low camera angle"
  V3 — cinematic: "wide establishing shot, person centered between
                   crown and feet, head not cropped"
  V4 — composition: "long shot, subject occupies central 50% of
                     vertical frame top to bottom"

Lighting + seed are pinned so framing is the only varying axis.

Run only AFTER `phase0_framing_probe.py` lands its results, so we
know whether the default framings need replacing entirely or whether
some subset works. If 0/4 default framings produce full-body, this
probe proposes the replacement set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from prompt_matrix import (  # noqa: E402
    DEFAULT_LIGHTINGS,
    DEFAULT_SEEDS,
    MatrixAxes,
)
from runner import run_batch  # noqa: E402


AGGRESSIVE_FRAMINGS: tuple[str, ...] = (
    "shot from 5 meters away, full body in frame, feet visible at bottom of frame",
    "wide angle 24mm photograph, low camera angle, person standing fully visible head to feet",
    "wide establishing shot, person centered between crown and feet, head not cropped, feet visible",
    "long shot, subject occupies central 50 percent of vertical frame from top to bottom",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-engineering-probe",
        description=(
            "Test aggressive framing language to escape FLUX prior bias. "
            "4 images, ~14 min inference (warm cache)."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True)
    args = parser.parse_args(argv)

    axes = MatrixAxes(
        framings=AGGRESSIVE_FRAMINGS,
        lightings=(DEFAULT_LIGHTINGS[0],),
        seeds=(DEFAULT_SEEDS[0],),
    )

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        axes=axes,
        backend="local-flux",
        notes=(
            "Phase 0 prompt-engineering probe — aggressive framing "
            "language to escape FLUX prior bias toward portrait crops."
        ),
    )

    print(
        f"[prompt-eng-probe] persona={args.persona} batch={args.batch} "
        f"prompts={len(manifest.prompts)} candidates={len(manifest.candidates)}"
    )
    for c in manifest.candidates:
        print(f"  image: personas/{args.persona}/_pipeline/step1_references/{args.batch}/{c.image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
