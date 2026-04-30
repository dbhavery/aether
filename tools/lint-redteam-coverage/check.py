#!/usr/bin/env python3
"""Aether red-team scenario coverage guard.

Mirror of `tools/lint-quality-doc/check.py` in spirit — but instead
of validating doc anchors, this asserts every required attack
category in `tools/redteam/scenarios/` has at least N scenarios.

Why a guard: T2.2 explicitly enumerates five required attack
categories. A regression that quietly drops one (renamed folder,
deleted JSONL, scenarios moved without an audit) silently shrinks
the red-team surface. CI would not catch it without this.

Run:

  python tools/lint-redteam-coverage/check.py            # validate
  python tools/lint-redteam-coverage/check.py --json     # machine-readable
  python tools/lint-redteam-coverage/check.py --min 3    # raise the floor

Exit codes:
  0 — every category meets the minimum.
  1 — one or more categories fall below the minimum.
  2 — usage error / missing tree.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Required categories — kept in lockstep with
# `tools/redteam/harness.py::CATEGORIES`. If they disagree, this
# linter (and probably the harness) is wrong; cross-check on edit.
REQUIRED_CATEGORIES: tuple[str, ...] = (
    "prompt_attack",
    "memory_poisoning",
    "browser_misuse",
    "permission_bypass",
    "exfiltration",
)


def _resolve_repo_root() -> Path:
    env = os.environ.get("AETHER_REPO_ROOT")
    if env:
        return Path(env)
    # tools/lint-redteam-coverage/check.py -> two parents up.
    return Path(__file__).resolve().parents[2]


def _count_scenarios(scenarios_root: Path, category: str) -> int:
    """Count JSONL scenario lines under a category folder. Counts
    *non-empty, non-comment* lines so a category with two files but
    only one real scenario still surfaces honestly."""
    cat_dir = scenarios_root / category
    if not cat_dir.is_dir():
        return 0
    n = 0
    for path in cat_dir.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                stripped = line.strip()
                if not stripped or stripped.startswith("//"):
                    continue
                # Cheap validity check — full parsing happens in the
                # harness loader. Here we only need a count.
                n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lint-redteam-coverage")
    parser.add_argument(
        "--min",
        type=int,
        default=2,
        help="Minimum scenarios required per category (default 2 per T2.2).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report on stdout.",
    )
    parser.add_argument(
        "--scenarios-root",
        default=None,
        help="Override scenarios root (default: <repo>/tools/redteam/scenarios).",
    )
    args = parser.parse_args(argv)

    repo_root = _resolve_repo_root()
    scenarios_root = (
        Path(args.scenarios_root)
        if args.scenarios_root
        else repo_root / "tools" / "redteam" / "scenarios"
    )
    if not scenarios_root.is_dir():
        print(
            f"error: scenarios root not found: {scenarios_root}",
            file=sys.stderr,
        )
        return 2

    counts: dict[str, int] = {}
    for cat in REQUIRED_CATEGORIES:
        counts[cat] = _count_scenarios(scenarios_root, cat)

    failures = [
        (cat, n) for cat, n in counts.items() if n < args.min
    ]

    if args.json:
        report = {
            "scenarios_root": str(scenarios_root),
            "min_required": args.min,
            "counts": counts,
            "failures": [{"category": c, "count": n} for c, n in failures],
        }
        print(json.dumps(report, indent=2))
    else:
        print(f"redteam coverage (min {args.min} per category):")
        for cat, n in counts.items():
            badge = "OK" if n >= args.min else "MISS"
            print(f"  [{badge}] {cat:22s} {n}")

    if failures:
        if not args.json:
            print(
                f"\nFAIL: {len(failures)} category(ies) below threshold:",
                file=sys.stderr,
            )
            for cat, n in failures:
                print(
                    f"  - {cat}: {n} scenarios (need ≥{args.min})",
                    file=sys.stderr,
                )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
