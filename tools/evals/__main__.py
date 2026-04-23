#!/usr/bin/env python3
"""Aether quality / eval harness — v1.1.

See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`. This entry point:

  - loads every JSONL scenario under `tools/evals/scenarios/`,
  - produces an `actual` response via one of:
      * `--dry-run` — replay the scenario's pre-recorded `actual`,
      * `--backend ollama` — POST the last user turn to a local
        Ollama instance and capture the response (v1.1),
  - evaluates each expectation against the response,
  - emits a markdown report and/or a JSON report.

Live backend config (Ollama):

  env AETHER_EVAL_OLLAMA_BASE_URL  default `http://127.0.0.1:11434`
  env AETHER_EVAL_OLLAMA_MODEL     default `llama3.2`
  env AETHER_EVAL_OLLAMA_TIMEOUT_S default `30`

Live-backend mode is deliberately minimal: single-turn, no persona
prompt compilation, no memory window. The goal is "did this scenario
regress when we re-ran it?", not full end-to-end fidelity. Richer
wiring (persona compile, memory context, presence injection) lands
with later slices.

Exit codes:
  0  — every scenario either passed or had no evaluable expectations.
  1  — one or more scenarios failed.
  2  — usage / IO error.

Run:

  python tools/evals/__main__.py --dry-run
  python tools/evals/__main__.py --backend ollama --capture-into captured/
  python tools/evals/__main__.py --report-md out/eval_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
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


def _last_user_prompt(s: Scenario) -> str | None:
    """Extract the final `role=user` turn's `content` for live
    backend prompting. Returns None when the scenario has no user
    turn (e.g. presence scenarios where the only turn is a system
    annotation)."""
    turns = s.raw.get("turns") or []
    for t in reversed(turns):
        if isinstance(t, dict) and t.get("role") == "user":
            content = t.get("content")
            if isinstance(content, str):
                return content
    return None


def _ollama_generate(prompt: str) -> tuple[bool, str]:
    """POST `prompt` to the Ollama `/api/generate` endpoint.
    Returns `(ok, text)` where `ok=False` carries the error message
    in `text` so the runner can surface it in the scenario note.

    Intentionally minimal: no streaming, no options, no persona
    prompt — v1.1 lands the hook, not the full integration."""
    base = os.environ.get(
        "AETHER_EVAL_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    ).rstrip("/")
    model = os.environ.get("AETHER_EVAL_OLLAMA_MODEL", "llama3.2")
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
        return False, f"ollama transport error ({base}): {exc}"
    except json.JSONDecodeError as exc:
        return False, f"ollama response not JSON: {exc}"
    text = payload.get("response")
    if not isinstance(text, str):
        return False, f"ollama response missing 'response' field: {payload!r}"
    return True, text


def _resolve_actual(
    s: Scenario, backend: str, dry_run: bool
) -> tuple[str | None, str | None]:
    """Produce an `actual` string for scenario `s` or explain why
    one is not available. Returns `(text, note)` where exactly one
    is non-None."""
    if backend == "ollama":
        prompt = _last_user_prompt(s)
        if prompt is None:
            return None, "scenario has no user turn — skipped (ollama backend)"
        ok, out = _ollama_generate(prompt)
        if not ok:
            return None, out
        return out, None
    # Default: dry-run / recorded replay.
    text = s.actual_text
    if text is not None:
        return text, None
    if dry_run:
        return None, "no `actual` recorded — skipped in --dry-run"
    return None, "no `actual` recorded and no backend selected"


def _run_scenario(
    s: Scenario, backend: str, dry_run: bool, capture_into: Path | None
) -> ScenarioResult:
    text, note = _resolve_actual(s, backend, dry_run)
    if text is None:
        return ScenarioResult(
            scenario=s,
            status="skip",
            response=None,
            expectations=[],
            note=note,
        )

    # Live-backend capture: dump the captured `actual` alongside the
    # scenario so a later dry-run can replay the exact response.
    # One file per scenario id, markdown for human review.
    if capture_into is not None and backend != "dry-run":
        capture_into.mkdir(parents=True, exist_ok=True)
        safe = s.id.replace("/", "_").replace(" ", "_")
        out_path = capture_into / f"{safe}.md"
        out_path.write_text(
            f"# {s.id}\n\n**domain:** {s.domain}\n\n"
            f"**backend:** {backend}\n\n"
            f"## Prompt\n\n```\n{_last_user_prompt(s) or ''}\n```\n\n"
            f"## Captured response\n\n```\n{text}\n```\n",
            encoding="utf-8",
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
        "--backend",
        choices=["dry-run", "ollama"],
        default="dry-run",
        help="Response source. `dry-run` (default) replays recorded "
             "`actual` fields. `ollama` POSTs the last user turn to "
             "a local Ollama instance (see env vars in module doc).",
    )
    parser.add_argument(
        "--capture-into",
        default=None,
        help="When using a live backend, write per-scenario captured "
             "responses to this directory as markdown.",
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

    # Resolve the effective backend. `--dry-run` is preserved as a
    # convenience alias for `--backend dry-run`.
    backend = "dry-run" if args.dry_run else args.backend
    capture_into = Path(args.capture_into) if args.capture_into else None
    results = [
        _run_scenario(s, backend=backend, dry_run=args.dry_run, capture_into=capture_into)
        for s in scenarios
    ]

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
