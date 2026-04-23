#!/usr/bin/env python3
"""Aether quality / eval harness — v1 scaffold.

See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`. This entry point:

  - loads every JSONL scenario under `tools/evals/scenarios/`,
  - either replays expectations against a scenario's pre-recorded
    `actual` field (`--dry-run`) or errors out if no backend is
    available (live backend wiring is a later slice),
  - evaluates each expectation against the response,
  - emits a markdown report and/or a JSON report.

Exit codes:
  0  — every scenario either passed or had no evaluable expectations.
  1  — one or more scenarios failed.
  2  — usage / IO error.

Run:

  python tools/evals/__main__.py --dry-run
  python tools/evals/__main__.py --report-md out/eval_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from expectations import EVALUATED_KINDS, evaluate_expectation, ExpectationResult
from report import build_markdown_report


@dataclass
class Scenario:
    path: Path
    line_no: int
    raw: dict

    @property
    def id(self) -> str:
        return self.raw.get("id", f"{self.path.name}:{self.line_no}")

    @property
    def domain(self) -> str:
        return self.raw.get("domain", "unknown")

    @property
    def actual_text(self) -> str | None:
        actual = self.raw.get("actual")
        if isinstance(actual, dict):
            text = actual.get("text")
            return text if isinstance(text, str) else None
        if isinstance(actual, str):
            return actual
        return None

    @property
    def expectations(self) -> list[dict]:
        raw = self.raw.get("expectations")
        return raw if isinstance(raw, list) else []


@dataclass
class ScenarioResult:
    scenario: Scenario
    status: str                      # "pass" | "fail" | "skip"
    response: str | None
    expectations: list[ExpectationResult]
    note: str | None = None


def _iter_scenarios(root: Path) -> Iterable[Scenario]:
    for path in sorted(root.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"warning: {path}:{line_no}: invalid JSON ({exc})",
                        file=sys.stderr,
                    )
                    continue
                yield Scenario(path=path, line_no=line_no, raw=obj)


def _run_scenario(s: Scenario, dry_run: bool) -> ScenarioResult:
    # v1 scaffold: live backend wiring is a later slice. For now,
    # the runner consumes the scenario's pre-recorded `actual`
    # field. When none is present in `--dry-run` mode, we skip
    # with a clear note so the author knows they need to record
    # one (or wait for the live backend to land).
    text = s.actual_text
    if text is None:
        if dry_run:
            return ScenarioResult(
                scenario=s,
                status="skip",
                response=None,
                expectations=[],
                note="no `actual` recorded — skipped in --dry-run",
            )
        return ScenarioResult(
            scenario=s,
            status="skip",
            response=None,
            expectations=[],
            note="no `actual` recorded and live backend is not yet wired in v1",
        )

    results: list[ExpectationResult] = []
    any_eval = False
    for exp in s.expectations:
        kind = exp.get("kind")
        if kind not in EVALUATED_KINDS:
            results.append(
                ExpectationResult(
                    kind=kind or "<unknown>",
                    status="skip",
                    detail=f"runner does not know kind {kind!r}",
                )
            )
            continue
        any_eval = True
        results.append(evaluate_expectation(exp, text))

    if not any_eval:
        return ScenarioResult(
            scenario=s,
            status="skip",
            response=text,
            expectations=results,
            note="no known expectations evaluated",
        )

    failed = any(r.status == "fail" for r in results)
    return ScenarioResult(
        scenario=s,
        status="fail" if failed else "pass",
        response=text,
        expectations=results,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether-evals")
    parser.add_argument(
        "--scenarios-root",
        default=str(Path(__file__).resolve().parent / "scenarios"),
        help="Root folder to scan for *.jsonl scenarios.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay expectations against pre-recorded `actual` "
             "fields only. Does not invoke any backend.",
    )
    parser.add_argument(
        "--report-md",
        default=None,
        help="Write a markdown report to this path.",
    )
    parser.add_argument(
        "--report-json",
        default=None,
        help="Write a JSON report to this path.",
    )
    args = parser.parse_args(argv)

    root = Path(args.scenarios_root)
    if not root.is_dir():
        print(f"error: scenarios root not found: {root}", file=sys.stderr)
        return 2

    scenarios = list(_iter_scenarios(root))
    if not scenarios:
        print(f"no scenarios found under {root}", file=sys.stderr)
        return 2

    results = [_run_scenario(s, dry_run=args.dry_run) for s in scenarios]

    # Print a compact summary to stdout.
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    print(f"evals: {passed} pass · {failed} fail · {skipped} skip "
          f"(of {len(results)} scenarios)")
    for r in results:
        if r.status == "fail":
            print(f"  FAIL {r.scenario.id} ({r.scenario.domain})")
            for er in r.expectations:
                if er.status == "fail":
                    print(f"      - {er.kind}: {er.detail}")

    if args.report_md:
        out = Path(args.report_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_markdown_report(results), encoding="utf-8")
        print(f"markdown report: {out}")

    if args.report_json:
        out = Path(args.report_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": {"pass": passed, "fail": failed, "skip": skipped},
            "scenarios": [
                {
                    "id": r.scenario.id,
                    "domain": r.scenario.domain,
                    "status": r.status,
                    "note": r.note,
                    "expectations": [
                        {"kind": er.kind, "status": er.status, "detail": er.detail}
                        for er in r.expectations
                    ],
                }
                for r in results
            ],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"json report:     {out}")

    return 1 if failed else 0


if __name__ == "__main__":
    # Allow `python tools/evals/__main__.py` without a package install
    # by inserting this directory on sys.path for the sibling imports.
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    raise SystemExit(main())
