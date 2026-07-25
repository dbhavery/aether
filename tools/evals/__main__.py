#!/usr/bin/env python3
"""Aether quality / eval harness — v1.2.

See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`. This entry point:

  - loads every JSONL scenario under `tools/evals/scenarios/`,
  - produces an `actual` response via one of:
      * `--dry-run` — replay the scenario's pre-recorded `actual`,
      * `--backend ollama` — POST the last user turn to a local
        Ollama instance and capture the response (v1.1),
      * `--replay-from <dir>` — load a previously captured
        response from a structured JSON capture directory (v1.2),
  - evaluates each expectation against the response,
  - emits a markdown report and/or a JSON report.

Live backend config (Ollama):

  env AETHER_EVAL_OLLAMA_BASE_URL  default `http://127.0.0.1:11434`
  env AETHER_EVAL_OLLAMA_MODEL     default `gemma4:e4b` (ADR-0003 pin)
  env AETHER_EVAL_OLLAMA_TIMEOUT_S default `30`

Live-backend mode is deliberately minimal: single-turn, no persona
prompt compilation, no memory window. The goal is "did this scenario
regress when we re-ran it?", not full end-to-end fidelity. Richer
wiring (persona compile, memory context, presence injection) lands
with later slices.

Capture / replay flow (v1.2):

  # 1. Capture live responses once:
  python tools/evals/__main__.py --backend ollama \\
      --capture-into captures/2026-05-17/

  # 2. Replay those captures later without hitting the backend:
  python tools/evals/__main__.py --replay-from captures/2026-05-17/

Each capture produces two files per scenario:
  - `<scenario_id>.md`   — human-readable (unchanged from v1.1),
  - `<scenario_id>.json` — machine-replayable structured payload.

The JSON carries `scenario_id`, `domain`, `backend`, `captured_at`
(UTC ISO-8601), `prompt`, `response`, and `metadata` (model id,
base URL, timeout used). Unknown fields are ignored on replay so
the schema stays additive.

Exit codes:
  0  — every scenario either passed or had no evaluable expectations.
  1  — one or more scenarios failed.
  2  — usage / IO error.

Run:

  python tools/evals/__main__.py --dry-run
  python tools/evals/__main__.py --backend ollama --capture-into captured/
  python tools/evals/__main__.py --replay-from captured/
  python tools/evals/__main__.py --report-md out/eval_report.md
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from composition import COMPOSER_NAMES, ComposedPrompt, CompositionContext, compose_prompt
from expectations import EVALUATED_KINDS, evaluate_expectation, ExpectationResult
from report import build_markdown_report


# Default composition set when `--compose` is omitted. v1 ran no
# composers at all; the v2 default ("persona") matches the
# minimum-viable identity injection while keeping legacy capture
# files re-usable as long as the persona composer is opt-out.
DEFAULT_COMPOSE = "persona"


# Repo root inferred from this file's location: tools/evals/__main__.py
# -> two parents up. Used by the composition layer to resolve
# personas/ and tools/evals/fixtures/ without an env-var dance.
REPO_ROOT = Path(__file__).resolve().parents[2]


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

    @property
    def requires_composition(self) -> bool:
        """A scenario "requires composition" when its `setup` block
        carries inputs that the live `--backend ollama` minimal mode
        does NOT compose into the prompt: prior memory, presence
        state, vision frames, voice audio. Running such scenarios
        through the minimal backend produces false failures (the
        model has no way to know it's Away, has no fridge image to
        describe, etc.).

        On-hardware validation 2026-04-24 confirmed: 4 of 6 scenarios
        in the v1 suite failed under `--backend ollama` for exactly
        this reason. They are now skipped with a clear note rather
        than silently fail.

        See the 2026-04-24 on-hardware validation data and the
        decisions log (D-006) for the design rationale.
        """
        setup = self.raw.get("setup")
        if not isinstance(setup, dict):
            return False
        if isinstance(setup.get("memory"), list) and setup["memory"]:
            return True
        if isinstance(setup.get("presence"), dict) and setup["presence"]:
            return True
        if "frame" in setup or "audio" in setup:
            return True
        return False


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


def _ollama_env() -> tuple[str, str, float]:
    """Snapshot the Ollama live-backend env into one tuple. Split
    out so capture metadata and the generate call agree on exactly
    which values were in effect at the time of the call."""
    base = os.environ.get(
        "AETHER_EVAL_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    ).rstrip("/")
    model = os.environ.get("AETHER_EVAL_OLLAMA_MODEL", "gemma4:e4b")
    timeout = float(os.environ.get("AETHER_EVAL_OLLAMA_TIMEOUT_S", "30"))
    return base, model, timeout


def _ollama_generate(prompt: str) -> tuple[bool, str]:
    """POST `prompt` to the Ollama `/api/generate` endpoint.
    Returns `(ok, text)` where `ok=False` carries the error message
    in `text` so the runner can surface it in the scenario note.

    Intentionally minimal: no streaming, no options, no persona
    prompt — v1.1 lands the hook, not the full integration."""
    base, model, timeout = _ollama_env()
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


def _ollama_chat(composed: ComposedPrompt) -> tuple[bool, str]:
    """POST a composed prompt to Ollama's `/api/chat` endpoint.

    Used when the harness has at least one composer enabled — chat
    is the only Ollama surface that accepts both a system message
    and the multimodal `images` field on a user message. Returns
    `(ok, text)`; `ok=False` carries the transport error so the
    runner can surface it in the scenario note.

    Retries once on transport / 500 errors per Phase 7 heavy-usage
    protocol — Ollama returns 500s under sustained load while the
    parallel synthetic-corpus phase is also pinging gemma4:e4b.
    """
    base, model, timeout = _ollama_env()
    messages: list[dict[str, object]] = []
    if composed.system is not None:
        messages.append({"role": "system", "content": composed.system})
    user_msg: dict[str, object] = {"role": "user", "content": composed.user}
    if composed.images:
        user_msg["images"] = list(composed.images)
    messages.append(user_msg)
    body = json.dumps(
        {"model": model, "messages": messages, "stream": False}
    ).encode("utf-8")

    last_error: str = ""
    for attempt in range(2):
        if attempt > 0:
            # Single backoff retry per Phase 7 heavy-usage protocol.
            # 250ms is short enough to not stall the 6-scenario sweep
            # but long enough to clear a transient overlap with the
            # parallel embed/generate workload.
            import time
            time.sleep(0.25)
        req = urllib.request.Request(
            f"{base}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = f"ollama HTTP {exc.code} ({base}): {exc.reason}"
            if exc.code >= 500:
                continue
            return False, last_error
        except urllib.error.URLError as exc:
            last_error = f"ollama transport error ({base}): {exc}"
            continue
        except json.JSONDecodeError as exc:
            return False, f"ollama response not JSON: {exc}"
        message = payload.get("message")
        if not isinstance(message, dict):
            return False, f"ollama chat response missing 'message': {payload!r}"
        text = message.get("content")
        if not isinstance(text, str):
            return False, f"ollama chat response missing 'content': {payload!r}"
        return True, text
    return False, last_error or "ollama chat failed after retries"


def _capture_filename(scenario_id: str) -> str:
    """Filesystem-safe base name derived from a scenario id. Same
    rule v1.1 used for its markdown captures; the v1.2 JSON
    captures share the same stem so manual inspection pairs cleanly
    with `*.md`."""
    return scenario_id.replace("/", "_").replace(" ", "_")


def _write_capture_json(
    capture_dir: Path,
    scenario: "Scenario",
    backend: str,
    prompt: str,
    response: str,
) -> Path:
    """Emit the machine-replayable capture. Always paired with the
    v1.1 markdown — the markdown is for humans, the JSON is for
    the replay loader."""
    capture_dir.mkdir(parents=True, exist_ok=True)
    path = capture_dir / f"{_capture_filename(scenario.id)}.json"
    metadata: dict[str, object] = {}
    if backend == "ollama":
        base, model, timeout = _ollama_env()
        metadata = {
            "ollama_base_url": base,
            "ollama_model": model,
            "ollama_timeout_s": timeout,
        }
    payload = {
        "scenario_id": scenario.id,
        "domain": scenario.domain,
        "backend": backend,
        "captured_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "prompt": prompt,
        "response": response,
        "metadata": metadata,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _load_replay_capture(
    replay_dir: Path, scenario_id: str
) -> tuple[str | None, str | None]:
    """Load a previously captured response for a scenario.
    Returns `(response, note)` with exactly one field populated.
    Unknown top-level fields are ignored so the capture schema
    stays additive."""
    path = replay_dir / f"{_capture_filename(scenario_id)}.json"
    if not path.is_file():
        return None, f"no capture at {path} — skipped (replay mode)"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"capture {path} is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"capture {path} must be a JSON object"
    response = payload.get("response")
    if not isinstance(response, str):
        return None, f"capture {path} missing string `response` field"
    return response, None


def _scenario_needs_uncomposed(s: Scenario, enabled: set[str]) -> str | None:
    """Return a skip note when the scenario needs a composition
    surface that the active `--compose` set does not provide.

    The check mirrors `Scenario.requires_composition` but is
    context-aware: a memory-dependent scenario is fine when
    `memory` is enabled, a vision scenario fine when `vision` is
    enabled, etc. Presence has no composer in this slice (the
    persona system prompt does not surface presence state); a
    presence-dependent scenario therefore always requires a manual
    presence injection that the v2 layer does not yet provide.
    """
    setup = s.raw.get("setup")
    if not isinstance(setup, dict):
        return None
    if isinstance(setup.get("memory"), list) and setup["memory"] and "memory" not in enabled:
        return "scenario sets memory but --compose excludes memory"
    if "frame" in setup and "vision" not in enabled:
        return "scenario sets frame but --compose excludes vision"
    if "audio" in setup and "voice" not in enabled:
        return "scenario sets audio but --compose excludes voice"
    if isinstance(setup.get("presence"), dict) and setup["presence"]:
        return (
            "scenario sets presence state — Quality-Eval V2 has no presence "
            "composer (presence injection deferred; see "
            "ARCHITECTURE.md)"
        )
    return None


def _resolve_actual(
    s: Scenario,
    backend: str,
    dry_run: bool,
    replay_dir: Path | None,
    composers: set[str],
    composition_ctx: CompositionContext,
) -> tuple[str | None, str | None]:
    """Produce an `actual` string for scenario `s` or explain why
    one is not available. Returns `(text, note)` where exactly one
    is non-None.

    When at least one composer is enabled and the backend is live,
    the harness routes through `compose_prompt` + `_ollama_chat`
    so persona / memory / vision / voice surfaces reach the model
    end-to-end. When `--compose` is disabled (empty set), the
    legacy `_ollama_generate` single-turn path remains, preserving
    pre-Phase-7 baseline reproducibility.
    """
    if backend == "replay":
        assert replay_dir is not None, "replay backend requires --replay-from"
        return _load_replay_capture(replay_dir, s.id)
    if backend == "ollama":
        prompt = _last_user_prompt(s)
        if prompt is None:
            return None, "scenario has no user turn — skipped (ollama backend)"
        skip_note = _scenario_needs_uncomposed(s, composers)
        if skip_note is not None:
            return None, (
                f"{skip_note} — skipped (ollama backend; re-run with the "
                "missing composer enabled)"
            )
        if not composers:
            # Legacy uncomposed path — preserved so prior captures stay
            # reproducible. The composition-aware skip above prevents
            # composition-dependent scenarios from false-failing here.
            ok, out = _ollama_generate(prompt)
            if not ok:
                return None, out
            return out, None
        composed = compose_prompt(
            user_prompt=prompt,
            setup=s.raw.get("setup") if isinstance(s.raw.get("setup"), dict) else None,
            enabled=composers,
            ctx=composition_ctx,
        )
        ok, out = _ollama_chat(composed)
        if not ok:
            return None, out
        if composed.notes:
            # Surface composer-side substitutions in the scenario note;
            # the response itself stays clean for evaluation.
            joined = "; ".join(composed.notes)
            return out, f"composed (notes: {joined})"
        return out, None
    # Default: dry-run / recorded replay.
    text = s.actual_text
    if text is not None:
        return text, None
    if dry_run:
        return None, "no `actual` recorded — skipped in --dry-run"
    return None, "no `actual` recorded and no backend selected"


def _run_scenario(
    s: Scenario,
    backend: str,
    dry_run: bool,
    capture_into: Path | None,
    replay_dir: Path | None,
    composers: set[str],
    composition_ctx: CompositionContext,
) -> ScenarioResult:
    text, note = _resolve_actual(
        s, backend, dry_run, replay_dir, composers, composition_ctx
    )
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
    # v1.1 writes the markdown for human review; v1.2 also writes a
    # structured JSON so `--replay-from` can re-evaluate without a
    # backend. Replay mode itself never writes captures — it is
    # already reading them.
    if capture_into is not None and backend not in ("dry-run", "replay"):
        capture_into.mkdir(parents=True, exist_ok=True)
        safe = _capture_filename(s.id)
        prompt = _last_user_prompt(s) or ""
        md_path = capture_into / f"{safe}.md"
        md_path.write_text(
            f"# {s.id}\n\n**domain:** {s.domain}\n\n"
            f"**backend:** {backend}\n\n"
            f"## Prompt\n\n```\n{prompt}\n```\n\n"
            f"## Captured response\n\n```\n{text}\n```\n",
            encoding="utf-8",
        )
        _write_capture_json(capture_into, s, backend, prompt, text)

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
        # Carry composer-side substitution notes through so the
        # report can show why a "pass" was qualified or why a
        # "fail" might be a fixture-substitution artifact.
        note=note,
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
             "responses to this directory (markdown for humans, JSON "
             "for `--replay-from`).",
    )
    parser.add_argument(
        "--replay-from",
        default=None,
        help="Replay previously captured responses from this "
             "directory. Implies --backend replay; incompatible with "
             "--backend ollama and with --capture-into.",
    )
    parser.add_argument(
        "--compose",
        default=DEFAULT_COMPOSE,
        help=(
            "CSV of composition surfaces to inject into live-backend "
            "runs. Choices: persona, memory, vision, voice. "
            f"Default: {DEFAULT_COMPOSE!r}. Use '' (empty string) to "
            "disable all composers and run the legacy uncomposed "
            "single-turn path. Composition-dependent scenarios that "
            "lack a required composer are skipped with a clear note."
        ),
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
    # convenience alias for `--backend dry-run`. `--replay-from`
    # implies the `replay` backend and is mutually exclusive with
    # live backends and with capture.
    replay_dir: Path | None = None
    if args.replay_from is not None:
        replay_dir = Path(args.replay_from)
        if not replay_dir.is_dir():
            print(
                f"error: --replay-from directory not found: {replay_dir}",
                file=sys.stderr,
            )
            return 2
        if args.backend not in ("dry-run",):
            print(
                "error: --replay-from is incompatible with "
                f"--backend {args.backend}",
                file=sys.stderr,
            )
            return 2
        if args.capture_into is not None:
            print(
                "error: --replay-from cannot be combined with "
                "--capture-into (captures already exist)",
                file=sys.stderr,
            )
            return 2
        backend = "replay"
    elif args.dry_run:
        backend = "dry-run"
    else:
        backend = args.backend
    capture_into = Path(args.capture_into) if args.capture_into else None

    # Parse the --compose CSV into the validated composer set.
    # Empty string disables all composers explicitly. Unknown names
    # are rejected loudly so a typo doesn't silently produce an
    # uncomposed run that looks composed in the logs.
    raw_compose = args.compose.strip()
    composers: set[str] = set()
    if raw_compose:
        for token in raw_compose.split(","):
            name = token.strip()
            if not name:
                continue
            if name not in COMPOSER_NAMES:
                print(
                    f"error: --compose unknown composer {name!r}; "
                    f"valid choices: {', '.join(COMPOSER_NAMES)}",
                    file=sys.stderr,
                )
                return 2
            composers.add(name)
    composition_ctx = CompositionContext.from_repo_root(REPO_ROOT)

    results = [
        _run_scenario(
            s,
            backend=backend,
            dry_run=args.dry_run,
            capture_into=capture_into,
            replay_dir=replay_dir,
            composers=composers,
            composition_ctx=composition_ctx,
        )
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
