"""Sequential body-extension driver for curation keepers.

Reads a list of source images, runs `extend_to_full_body` on each,
writes `<src>_extended.png` siblings, and logs wall-clock per image.
Avoids the tee + tqdm progress-hiding problem by printing direct
to stderr after each image completes.

Usage:
    PERSONA_REFGEN_LIVE=1 PERSONA_REFGEN_OFFLOAD=sequential \
      python tools/persona-reference-gen/batch_body_extend.py \
        --inputs path1.png path2.png ... \
        [--extend-down 1024] [--seed-base 7777]

Designed for the curation keepers in
`personas/aurora/_pipeline/step1_references/2026-05-02-curation-1to2/`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from body_extension import (  # noqa: E402
    DEFAULT_EXTEND_DOWN,
    DEFAULT_EXTENSION_PROMPT,
    DEFAULT_NEGATIVE_PROMPT,
    extend_to_full_body,
)
from backend_local_flux import is_live_mode  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="batch-body-extend")
    parser.add_argument("--inputs", required=True, nargs="+", type=Path)
    parser.add_argument(
        "--extend-down",
        type=int,
        default=DEFAULT_EXTEND_DOWN,
        help=(
            "Pixels to extend below the source image. 1024 produces "
            "true feet-visible full body; 512 is more conservative."
        ),
    )
    parser.add_argument(
        "--seed-base",
        type=int,
        default=7777,
        help="Per-image seed = seed-base + index (deterministic).",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_EXTENSION_PROMPT,
    )
    parser.add_argument(
        "--negative-prompt",
        default=DEFAULT_NEGATIVE_PROMPT,
    )
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--guidance-scale", type=float, default=30.0)
    parser.add_argument("--strength", type=float, default=1.0)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip inputs whose <src>_extended.png already exists.",
    )
    args = parser.parse_args(argv)

    mode = "LIVE" if is_live_mode() else "STUB"
    print(f"[batch] {mode} mode, {len(args.inputs)} input(s)", file=sys.stderr)

    overall_start = time.time()
    for idx, src in enumerate(args.inputs):
        if not src.exists():
            print(f"[batch] {idx+1}/{len(args.inputs)} MISSING {src}", file=sys.stderr)
            continue
        out = src.with_name(src.stem + "_extended.png")
        if args.skip_existing and out.exists():
            print(
                f"[batch] {idx+1}/{len(args.inputs)} SKIP (exists) {out.name}",
                file=sys.stderr,
            )
            continue

        seed = args.seed_base + idx
        t0 = time.time()
        print(
            f"[batch] {idx+1}/{len(args.inputs)} START {src.name} "
            f"seed={seed} extend_down={args.extend_down}",
            file=sys.stderr,
            flush=True,
        )
        try:
            result = extend_to_full_body(
                src_path=src,
                out_path=out,
                extension_prompt=args.prompt,
                negative_prompt=args.negative_prompt,
                seed=seed,
                extend_down=args.extend_down,
                steps=args.steps,
                guidance_scale=args.guidance_scale,
                strength=args.strength,
            )
        except Exception as exc:  # noqa: BLE001 — operator wants the trace
            elapsed = time.time() - t0
            print(
                f"[batch] {idx+1}/{len(args.inputs)} FAIL {src.name} "
                f"after {elapsed:.1f}s: {exc!r}",
                file=sys.stderr,
                flush=True,
            )
            continue

        elapsed = time.time() - t0
        print(
            f"[batch] {idx+1}/{len(args.inputs)} DONE {src.name} -> "
            f"{result.output_path.name} ({result.width}x{result.height}) "
            f"in {elapsed:.1f}s",
            file=sys.stderr,
            flush=True,
        )

    overall_elapsed = time.time() - overall_start
    print(
        f"[batch] all done in {overall_elapsed:.1f}s "
        f"({overall_elapsed/60.0:.1f} min)",
        file=sys.stderr,
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
