"""One-off probe — test all 4 default framings against the same lighting + seed.

Phase 0 baseline (`phase0_baseline.py`) produced one image with
framing-fail at the FIRST default framing. This driver answers:
**does the same bias hit all 4 framings, or just the first?**

Generates exactly 4 images — one per `prompt_matrix.DEFAULT_FRAMINGS`
entry, with `DEFAULT_LIGHTINGS[0]` + `DEFAULT_SEEDS[0]` fixed. Same
backend (local-flux), same offload strategy (sequential). Run after
the FLUX pipeline is already loaded if you can — pipeline load is
~15 min, the 4 inferences are ~25 min total at 1024×1536.
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
        prog="phase0-framing-probe",
        description=(
            "Probe whether FLUX.1-dev's framing bias hits all 4 default "
            "framings or just the first. 4 images, ~25 min inference."
        ),
    )
    parser.add_argument("--persona", default="aurora")
    parser.add_argument("--batch", required=True, help="batch id, e.g. 2026-05-02-framing-probe")
    args = parser.parse_args(argv)

    axes = MatrixAxes(
        framings=DEFAULT_FRAMINGS,
        lightings=(DEFAULT_LIGHTINGS[0],),
        seeds=(DEFAULT_SEEDS[0],),
    )

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        axes=axes,
        backend="local-flux",
        notes=(
            "Phase 0 framing probe — does FLUX's framing bias hit all 4 "
            "default framings or just the first? Phase 0 baseline showed "
            "framing-fail; this batch tests scope."
        ),
    )

    print(
        f"[framing-probe] persona={args.persona} batch={args.batch} "
        f"prompts={len(manifest.prompts)} candidates={len(manifest.candidates)} "
        f"backend={manifest.backend}"
    )
    for c in manifest.candidates:
        print(f"  image: personas/{args.persona}/_pipeline/step1_references/{args.batch}/{c.image_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
