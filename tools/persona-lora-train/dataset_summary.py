"""Quick read-only inspection of the LoRA training corpus.

Calls `dataset_builder.build_dataset` against a temporary directory and
prints a structured summary of the result without polluting the
project tree. Exists to answer:

  - How many images would the LoRA train on?
  - What's the source-kind breakdown (anchor vs batch_candidate vs
    body_extended)?
  - Which batches contributed?
  - What captions does each row carry?

Use BEFORE `phase3_pipeline.py --execute` to confirm the corpus is
what you expect (especially after a fresh body_extension batch lands
new sibling images).

Usage:

    python tools/persona-lora-train/dataset_summary.py --persona aurora

By default applies `--relax-selftest-verdict` (matches the recipe-
locked Phase 3 launch). Pass `--strict` to reproduce the no-relax path.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from dataset_builder import build_dataset  # noqa: E402


def summarise(
    *,
    persona_slug: str,
    repo_root: Path,
    relax_selftest_verdict: bool,
    min_photoreal_score: int,
    include_anchor_set: bool,
    batch_ids: list[str] | None,
) -> dict:
    """Build dataset in a temp dir + return a summary dict."""
    with tempfile.TemporaryDirectory() as workdir:
        report = build_dataset(
            persona_slug=persona_slug,
            output_dir=Path(workdir) / "dataset",
            repo_root=repo_root,
            relax_selftest_verdict=relax_selftest_verdict,
            min_photoreal_score=min_photoreal_score,
            include_anchor_set=include_anchor_set,
            batch_ids=batch_ids,
        )

    # Group sources for the summary.
    by_kind = Counter(s.source_kind for s in report.sources)
    by_batch: dict[str, list] = {}
    for s in report.sources:
        key = s.batch_id or "<anchor>"
        by_batch.setdefault(key, []).append(s)

    return {
        "persona_slug": report.persona_slug,
        "instance_token": report.instance_token,
        "num_images": report.num_images,
        "by_kind": dict(by_kind),
        "by_batch": {
            batch: [
                {
                    "output_index": s.output_index,
                    "source_kind": s.source_kind,
                    "prompt_id": s.prompt_id,
                    "caption": s.caption,
                }
                for s in srcs
            ]
            for batch, srcs in by_batch.items()
        },
    }


def _print_summary(summary: dict) -> None:
    print(
        f"persona={summary['persona_slug']} "
        f"token={summary['instance_token']} "
        f"num_images={summary['num_images']}"
    )
    print()
    print("source_kind breakdown:")
    for kind, count in sorted(summary["by_kind"].items()):
        print(f"  {kind}: {count}")
    print()
    print("by batch:")
    for batch, srcs in summary["by_batch"].items():
        print(f"  {batch}: {len(srcs)} images")
        for s in srcs:
            cap = s["caption"][:60]
            print(
                f"    [{s['output_index']:02d}] "
                f"{s['source_kind']:>15}: {cap}"
            )

    if summary["num_images"] < 8:
        print()
        print(
            "WARNING: corpus < 8 images — LoRA may underfit. "
            "Recommended minimum 15."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dataset-summary")
    parser.add_argument("--persona", required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "drop --relax-selftest-verdict (default ON). Strict mode "
            "requires every candidate to have a selftest verdict of "
            "pass — useful for catching how many candidates would survive "
            "a Doctrine §8 strict gate."
        ),
    )
    parser.add_argument("--min-photoreal-score", type=int, default=6)
    parser.add_argument(
        "--no-anchor-set",
        action="store_true",
        help="exclude the v0 anchor images",
    )
    parser.add_argument(
        "--batch-ids",
        nargs="*",
        default=None,
        help="restrict to specific Step 1 batch ids",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    summary = summarise(
        persona_slug=args.persona,
        repo_root=repo_root,
        relax_selftest_verdict=not args.strict,
        min_photoreal_score=args.min_photoreal_score,
        include_anchor_set=not args.no_anchor_set,
        batch_ids=args.batch_ids,
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
