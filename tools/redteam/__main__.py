#!/usr/bin/env python3
"""Aether red-team scenario harness — CLI runner.

See `tools/redteam/README.md` and `tools/redteam/harness.py`.

Default mode (`--dry-run`) replays each scenario's recorded
`actual.text` against its checks. This is the deterministic test
mode the harness's own self-test runs in: no live model calls, no
network. CI / CPU-only.

Other modes:

  --replay-from <dir>  — load responses from a Quality-Eval V1
                         capture directory (same JSON schema).
  --backend ollama     — POST the last user turn to a local Ollama
                         instance. Mirrors `tools/evals/__main__.py`.

Status taxonomy:

  pass     — every check passed, ≥1 check evaluated.
  fail     — at least one check failed (compliance with attack,
             leak, missing approval handoff, etc.).
  unknown  — no checks evaluable, or every check resolved to
             unknown. Distinguished from fail so a human can
             review without conflating with a regression.

Exit codes:

  0  — no failures (passes + unknowns only). Unknowns are flagged
       in the report but do not gate the run by default.
  1  — at least one scenario failed.
  2  — usage / IO error.
  3  — at least one scenario was UNKNOWN and `--strict` was set.

Run:

  python tools/redteam/__main__.py --dry-run
  python tools/redteam/__main__.py --report-md out/redteam.md
  python tools/redteam/__main__.py --replay-from captures/2026-05-18/
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# Sibling import: load harness as a package-relative module when run
# both as `python tools/redteam/__main__.py` and as
# `python -m tools.redteam`.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402  (sys.path insert above)
    CATEGORIES,
    RedTeamScenario,
    ScenarioOutcome,
    iter_scenarios,
    load_replay_response,
    run_scenario,
)


def _last_user_prompt(s: RedTeamScenario) -> str | None:
    turns = s.raw.get("turns") or []
    for t in reversed(turns):
        if isinstance(t, dict) and t.get("role") == "user":
            content = t.get("content")
            if isinstance(content, str):
                return content
    return None


def _resolve_response(
    s: RedTeamScenario,
    backend: str,
    replay_dir: Path | None,
) -> tuple[str | None, str | None]:
    if backend == "replay":
        assert replay_dir is not None
        return load_replay_response(replay_dir, s.id)
    if backend == "ollama":
        # Live mode is intentionally a thin shim — same contract as
        # the eval runner. Errors surface as `unknown` outcomes
        # rather than crashing the sweep.
        try:
            import urllib.error
            import urllib.request
        except ImportError as exc:  # pragma: no cover — stdlib
            return None, f"urllib unavailable: {exc}"
        prompt = _last_user_prompt(s)
        if prompt is None:
            return None, "scenario has no user turn — skipped (ollama)"
        import os

        base = os.environ.get(
            "AETHER_EVAL_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        ).rstrip("/")
        model = os.environ.get("AETHER_EVAL_OLLAMA_MODEL", "gemma4:e4b")
        timeout = float(os.environ.get("AETHER_EVAL_OLLAMA_TIMEOUT_S", "30"))
        body = json.dumps(
            {"model": model, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return None, f"ollama transport error ({base}): {exc}"
        text = payload.get("response")
        if not isinstance(text, str):
            return None, f"ollama response missing 'response': {payload!r}"
        return text, None
    # dry-run
    text = s.actual_text
    if text is not None:
        return text, None
    return None, "no `actual` recorded — scenario skipped (dry-run)"


def _capture_filename(scenario_id: str) -> str:
    return scenario_id.replace("/", "_").replace(" ", "_")


def _write_capture(
    capture_dir: Path,
    s: RedTeamScenario,
    backend: str,
    prompt: str,
    response: str,
) -> None:
    """Write a Quality-Eval V1-compatible capture so subsequent
    runs (red-team or eval) can replay from the same directory."""
    capture_dir.mkdir(parents=True, exist_ok=True)
    safe = _capture_filename(s.id)
    payload = {
        "scenario_id": s.id,
        "domain": s.category,
        "backend": backend,
        "captured_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "prompt": prompt,
        "response": response,
        "metadata": {"harness": "redteam", "attack": s.attack},
    }
    (capture_dir / f"{safe}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (capture_dir / f"{safe}.md").write_text(
        f"# {s.id}\n\n**category:** {s.category}\n\n"
        f"**attack:** {s.attack}\n\n"
        f"**backend:** {backend}\n\n"
        f"## Prompt\n\n```\n{prompt}\n```\n\n"
        f"## Captured response\n\n```\n{response}\n```\n",
        encoding="utf-8",
    )


def _build_report_md(outcomes: list[ScenarioOutcome]) -> str:
    lines = ["# Red-Team Run Report", ""]
    by_cat: dict[str, list[ScenarioOutcome]] = {c: [] for c in CATEGORIES}
    other: list[ScenarioOutcome] = []
    for o in outcomes:
        if o.scenario.category in by_cat:
            by_cat[o.scenario.category].append(o)
        else:
            other.append(o)
    p = sum(1 for o in outcomes if o.status == "pass")
    f = sum(1 for o in outcomes if o.status == "fail")
    u = sum(1 for o in outcomes if o.status == "unknown")
    lines.append(
        f"**Summary:** {p} pass · {f} fail · {u} unknown "
        f"(of {len(outcomes)} scenarios)"
    )
    lines.append("")
    for cat, scenarios in by_cat.items():
        lines.append(f"## {cat}")
        if not scenarios:
            lines.append("_no scenarios in this category_")
            lines.append("")
            continue
        for o in scenarios:
            badge = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKN"}[o.status]
            lines.append(f"- **[{badge}]** `{o.scenario.id}` (attack: {o.scenario.attack})")
            lines.append(f"  - reason: {o.reason}")
            for c in o.checks:
                lines.append(f"  - check `{c.kind}`: {c.status} — {c.detail}")
        lines.append("")
    if other:
        lines.append("## (uncategorized)")
        for o in other:
            lines.append(
                f"- `{o.scenario.id}` (category={o.scenario.category}): {o.status}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether-redteam")
    parser.add_argument(
        "--scenarios-root",
        default=str(HERE / "scenarios"),
        help="Root folder to scan for *.jsonl scenarios.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replay checks against pre-recorded `actual` fields. "
             "No backend invoked. Default test mode.",
    )
    parser.add_argument(
        "--backend",
        choices=["dry-run", "ollama"],
        default="dry-run",
        help="Response source. dry-run replays recorded `actual`. "
             "ollama POSTs the last user turn to a local Ollama.",
    )
    parser.add_argument(
        "--replay-from",
        default=None,
        help="Replay previously captured responses from this dir "
             "(Quality-Eval V1 capture schema). Implies --backend "
             "replay; mutually exclusive with --backend ollama and "
             "with --capture-into.",
    )
    parser.add_argument(
        "--capture-into",
        default=None,
        help="When using a live backend, write capture files to "
             "this dir (Quality-Eval V1 schema for cross-tool replay).",
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat UNKNOWN scenarios as a non-zero exit (code 3).",
    )
    parser.add_argument(
        "--category",
        default=None,
        help=f"Restrict to one category: {', '.join(CATEGORIES)}.",
    )
    args = parser.parse_args(argv)

    root = Path(args.scenarios_root)
    if not root.is_dir():
        print(f"error: scenarios root not found: {root}", file=sys.stderr)
        return 2

    replay_dir: Path | None = None
    if args.replay_from is not None:
        replay_dir = Path(args.replay_from)
        if not replay_dir.is_dir():
            print(
                f"error: --replay-from directory not found: {replay_dir}",
                file=sys.stderr,
            )
            return 2
        if args.backend == "ollama":
            print(
                "error: --replay-from incompatible with --backend ollama",
                file=sys.stderr,
            )
            return 2
        if args.capture_into is not None:
            print(
                "error: --replay-from cannot be combined with --capture-into",
                file=sys.stderr,
            )
            return 2
        backend = "replay"
    elif args.dry_run:
        backend = "dry-run"
    else:
        backend = args.backend

    capture_into = Path(args.capture_into) if args.capture_into else None

    scenarios = list(iter_scenarios(root))
    if args.category:
        if args.category not in CATEGORIES:
            print(
                f"error: --category {args.category!r} not in "
                f"{CATEGORIES!r}",
                file=sys.stderr,
            )
            return 2
        scenarios = [s for s in scenarios if s.category == args.category]
    if not scenarios:
        print(f"no scenarios found under {root}", file=sys.stderr)
        return 2

    outcomes: list[ScenarioOutcome] = []
    for s in scenarios:
        text, note = _resolve_response(s, backend, replay_dir)
        outcome = run_scenario(s, text)
        if outcome.note is None and note is not None and outcome.response is None:
            outcome.note = note
        outcomes.append(outcome)
        if (
            text is not None
            and capture_into is not None
            and backend not in ("dry-run", "replay")
        ):
            prompt = _last_user_prompt(s) or ""
            _write_capture(capture_into, s, backend, prompt, text)

    p = sum(1 for o in outcomes if o.status == "pass")
    f = sum(1 for o in outcomes if o.status == "fail")
    u = sum(1 for o in outcomes if o.status == "unknown")
    print(
        f"redteam: {p} pass · {f} fail · {u} unknown "
        f"(of {len(outcomes)} scenarios)"
    )
    for o in outcomes:
        if o.status == "fail":
            print(f"  FAIL {o.scenario.id} ({o.scenario.category}/{o.scenario.attack})")
            print(f"      reason: {o.reason}")
        elif o.status == "unknown":
            print(f"  UNKN {o.scenario.id} ({o.scenario.category}/{o.scenario.attack})")
            print(f"      reason: {o.reason}")

    if args.report_md:
        out = Path(args.report_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_build_report_md(outcomes), encoding="utf-8")
        print(f"markdown report: {out}")

    if args.report_json:
        out = Path(args.report_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": {"pass": p, "fail": f, "unknown": u},
            "scenarios": [
                {
                    "id": o.scenario.id,
                    "category": o.scenario.category,
                    "attack": o.scenario.attack,
                    "status": o.status,
                    "reason": o.reason,
                    "checks": [
                        {"kind": c.kind, "status": c.status, "detail": c.detail}
                        for c in o.checks
                    ],
                }
                for o in outcomes
            ],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"json report:     {out}")

    if f > 0:
        return 1
    if u > 0 and args.strict:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
