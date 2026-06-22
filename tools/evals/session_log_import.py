#!/usr/bin/env python3
"""Import an Aether session log into the Quality-Eval v1.2 capture
directory format so `--replay-from` can re-evaluate expectations
against responses from real conversations.

See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` §6 (roadmap item 6:
"session-log replay importer"). This tool bridges:

  session log  (what actually happened in a conversation)
    ─▶ capture JSON  (the v1.2 schema emitted by ``--capture-into``)
      ─▶ replay mode (``--replay-from``) re-evaluates the scenarios.

Input shape: JSONL, one `TurnMemoryRecord`-like object per line. Every
object must carry `session_id`, `role` (``"user"`` / ``"assistant"`` /
``"system"``), `content`, `sequence` (u64), and `timestamp_ms` (u64).
This matches what `SessionMemoryStore::recent` returns and what the
future ``telemetry_export`` Tauri command will emit. Lines that fail
to parse as JSON, or objects missing required fields, are silently
skipped with a WARN so a single corrupt line doesn't block the
import.

Matching heuristic (deliberately simple):

  For every user→assistant adjacent pair in the session log,
  and every scenario in ``--scenarios-root``:
  - Read the scenario's *last* user turn (via `turns` or `raw["turns"]`).
  - If the session-log user turn's content, stripped and case-folded,
    EQUALS the scenario's last user turn — it's a match.
  - If there's no exact match, fall back to substring: scenario
    prompt is fully contained inside the session-log turn.
  - First match wins; later candidates are ignored.
  - No match → scenario is skipped with a note on stderr.

Output: one capture per matched scenario, using the exact v1.2 schema
`_write_capture_json` produces (scenario_id, domain, backend,
captured_at, prompt, response, metadata). The `backend` field is set
to ``"session-log"`` so replay consumers can tell these captures came
from a real conversation rather than a live Ollama run. The
`metadata` block carries the `session_id` + sequence pair the pair
was drawn from so a later auditor can trace a capture back to the
session log row that produced it.

Usage::

    python tools/evals/session_log_import.py \\
        --session-log logs/2026-05-18.jsonl \\
        --capture-into out/session_replay_2026-05-18/

    python tools/evals/__main__.py \\
        --replay-from out/session_replay_2026-05-18/

Scope notes:
- Stdlib-only; no dependencies beyond Python 3.10+.
- The importer does NOT require an Aether runtime, an Ollama
  endpoint, or a database driver. It reads a JSONL and writes JSON.
- Unknown scenario domains are fine — the importer does not validate
  or filter by domain; that is the replay harness's job.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_FIELDS = ("session_id", "role", "content", "sequence", "timestamp_ms")


@dataclass
class SessionTurn:
    """One row of the session log. Matches `TurnMemoryRecord` in
    `packages/l2-memory/src/session.rs` field-for-field so the JSONL
    shape mirrors what the L2 store serialises."""

    session_id: str
    role: str
    content: str
    sequence: int
    timestamp_ms: int


def _parse_session_log(path: Path) -> list[SessionTurn]:
    """Parse a JSONL session log file. Returns turns in file order.
    Malformed lines and objects missing required fields are skipped
    with a stderr WARN so a single bad row doesn't block an import.
    Rows are NOT re-sorted: the caller is expected to hand us
    turns in the order they happened, matching `SessionMemoryStore`'s
    oldest-first contract."""
    turns: list[SessionTurn] = []
    with path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            raw = line.strip()
            if not raw or raw.startswith("//"):
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(
                    f"warning: {path}:{line_no}: invalid JSON ({exc})",
                    file=sys.stderr,
                )
                continue
            if not isinstance(obj, dict):
                print(
                    f"warning: {path}:{line_no}: expected JSON object, got {type(obj).__name__}",
                    file=sys.stderr,
                )
                continue
            missing = [k for k in REQUIRED_FIELDS if k not in obj]
            if missing:
                print(
                    f"warning: {path}:{line_no}: missing fields {missing}",
                    file=sys.stderr,
                )
                continue
            try:
                turn = SessionTurn(
                    session_id=str(obj["session_id"]),
                    role=str(obj["role"]),
                    content=str(obj["content"]),
                    sequence=int(obj["sequence"]),
                    timestamp_ms=int(obj["timestamp_ms"]),
                )
            except (TypeError, ValueError) as exc:
                print(
                    f"warning: {path}:{line_no}: field type mismatch ({exc})",
                    file=sys.stderr,
                )
                continue
            turns.append(turn)
    return turns


def _pair_user_assistant(turns: list[SessionTurn]) -> list[tuple[SessionTurn, SessionTurn]]:
    """Walk the session log and yield `(user_turn, assistant_turn)`
    pairs where the assistant turn is the first assistant turn that
    follows a user turn within the same session. System turns and
    consecutive-user / consecutive-assistant runs are ignored on the
    matching side but do not break the pairing of surrounding rows —
    a system turn between a user and an assistant is not a barrier."""
    pairs: list[tuple[SessionTurn, SessionTurn]] = []
    pending: dict[str, SessionTurn] = {}
    for t in turns:
        if t.role == "user":
            pending[t.session_id] = t
        elif t.role == "assistant":
            u = pending.pop(t.session_id, None)
            if u is not None:
                pairs.append((u, t))
        # system turns: neither emit nor clear pending user.
    return pairs


def _extract_scenarios(scenarios_root: Path) -> list[dict]:
    """Flatten every `.jsonl` scenario under `scenarios_root` into a
    list of `{id, domain, last_user_turn, raw}` dicts. A scenario
    with no user turn is still included so the importer can report
    it as skipped; `last_user_turn` is None in that case.

    Silently skips lines that don't parse as JSON."""
    out: list[dict] = []
    for path in sorted(scenarios_root.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as fp:
            for line_no, line in enumerate(fp, start=1):
                raw_line = line.strip()
                if not raw_line or raw_line.startswith("//"):
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                turns = obj.get("turns") or []
                last_user: str | None = None
                for t in reversed(turns):
                    if (
                        isinstance(t, dict)
                        and t.get("role") == "user"
                        and isinstance(t.get("content"), str)
                    ):
                        last_user = t["content"]
                        break
                out.append(
                    {
                        "id": obj.get(
                            "id", f"{path.name}:{line_no}"
                        ),
                        "domain": obj.get("domain", "unknown"),
                        "last_user_turn": last_user,
                        "path": str(path),
                    }
                )
    return out


def _norm(s: str) -> str:
    """Whitespace-and-case normalisation used for match decisions.
    Collapses runs of whitespace to single spaces, strips, and
    case-folds. Matches must not be sensitive to a user typing an
    extra newline vs the scenario's single-line form."""
    return " ".join(s.split()).casefold()


def match_scenario(
    session_prompt: str, scenario_prompt: str
) -> str | None:
    """Classify a scenario→session-turn match. Returns ``"exact"`` for
    normalised equality, ``"substring"`` when the scenario's prompt is
    fully contained in the session turn, or ``None`` when no match.
    Exposed for unit testing."""
    a = _norm(session_prompt)
    b = _norm(scenario_prompt)
    if not b:
        return None
    if a == b:
        return "exact"
    if b in a:
        return "substring"
    return None


def _capture_filename(scenario_id: str) -> str:
    """Mirror of ``_capture_filename`` in tools/evals/__main__.py —
    duplicated here so the importer stays standalone and does not
    have to load `__main__.py` (which registers argparse side
    effects)."""
    return scenario_id.replace("/", "_").replace(" ", "_")


def _iso_utc_z(ts_ms: int) -> str:
    """Format a ms-epoch timestamp as the UTC-Z ISO-8601 string the
    v1.2 capture schema uses. A whole-second resolution is sufficient
    — the capture schema already uses `microsecond=0` on its own
    write path."""
    dt = datetime.datetime.fromtimestamp(
        ts_ms / 1000.0, tz=datetime.timezone.utc
    ).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _write_capture(
    out_dir: Path,
    scenario: dict,
    user_turn: SessionTurn,
    assistant_turn: SessionTurn,
    match_kind: str,
) -> Path:
    """Emit one capture JSON. Schema mirrors
    ``_write_capture_json`` in ``tools/evals/__main__.py`` — the
    replay loader ignores unknown top-level fields so the additive
    `source_session_id` + `source_sequence` bits in `metadata` are
    safe."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_capture_filename(scenario['id'])}.json"
    payload = {
        "scenario_id": scenario["id"],
        "domain": scenario["domain"],
        "backend": "session-log",
        "captured_at": _iso_utc_z(assistant_turn.timestamp_ms),
        "prompt": user_turn.content,
        "response": assistant_turn.content,
        "metadata": {
            "source_session_id": user_turn.session_id,
            "source_user_sequence": user_turn.sequence,
            "source_assistant_sequence": assistant_turn.sequence,
            "match_kind": match_kind,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


@dataclass
class ImportReport:
    """Summary of what an import run did, returned to main() for
    stdout rendering and surfaced to callers that import this module
    as a library (e.g. tests)."""

    matched: list[tuple[str, str, str]]  # (scenario_id, match_kind, capture_path)
    skipped_no_match: list[str]          # scenario_id
    unmatched_session_pairs: int

    @property
    def match_count(self) -> int:
        return len(self.matched)


def import_session_log(
    session_log: Path,
    scenarios_root: Path,
    capture_into: Path,
) -> ImportReport:
    """Import entry point for programmatic use (including tests).
    Returns a structured report of what was emitted; side effect is
    the capture JSON files written under ``capture_into``."""
    turns = _parse_session_log(session_log)
    pairs = _pair_user_assistant(turns)
    scenarios = _extract_scenarios(scenarios_root)

    matched: list[tuple[str, str, str]] = []
    matched_scenario_ids: set[str] = set()
    unmatched_pairs = 0
    for u, a in pairs:
        hit = False
        for s in scenarios:
            if s["id"] in matched_scenario_ids:
                # First match wins; a scenario is emitted at most once
                # per import even if the user said the same thing
                # multiple times.
                continue
            prompt = s["last_user_turn"]
            if not isinstance(prompt, str):
                continue
            kind = match_scenario(u.content, prompt)
            if kind is None:
                continue
            out_path = _write_capture(capture_into, s, u, a, kind)
            matched.append((s["id"], kind, str(out_path)))
            matched_scenario_ids.add(s["id"])
            hit = True
            break
        if not hit:
            unmatched_pairs += 1

    skipped_no_match = [
        s["id"] for s in scenarios if s["id"] not in matched_scenario_ids
    ]
    return ImportReport(
        matched=matched,
        skipped_no_match=skipped_no_match,
        unmatched_session_pairs=unmatched_pairs,
    )


def _print_report(report: ImportReport) -> None:
    print(
        f"session-log import: {report.match_count} captures written "
        f"({sum(1 for _, k, _ in report.matched if k == 'exact')} exact, "
        f"{sum(1 for _, k, _ in report.matched if k == 'substring')} substring); "
        f"{len(report.skipped_no_match)} scenarios unmatched; "
        f"{report.unmatched_session_pairs} session pairs had no scenario."
    )
    for sid, kind, path in report.matched:
        print(f"  matched [{kind}] {sid}  ->  {path}")
    if report.skipped_no_match:
        # Keep this quiet on the stdout path — the summary line
        # already says how many were skipped. Dumping every unmatched
        # id for a long scenario tree would drown the report.
        print(
            f"  (note: {len(report.skipped_no_match)} scenarios had no matching "
            "session turn — run with --verbose-skips to list them)",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether-session-log-import")
    parser.add_argument(
        "--session-log",
        required=True,
        help="Path to a JSONL session log (one TurnMemoryRecord per line).",
    )
    parser.add_argument(
        "--scenarios-root",
        default=str(Path(__file__).resolve().parent / "scenarios"),
        help="Root folder of *.jsonl scenario files to match against.",
    )
    parser.add_argument(
        "--capture-into",
        required=True,
        help="Directory that will receive the emitted capture JSON files.",
    )
    parser.add_argument(
        "--verbose-skips",
        action="store_true",
        help="List every scenario that had no matching session turn.",
    )
    args = parser.parse_args(argv)

    session_log = Path(args.session_log)
    scenarios_root = Path(args.scenarios_root)
    capture_into = Path(args.capture_into)

    if not session_log.is_file():
        print(f"error: session log not found: {session_log}", file=sys.stderr)
        return 2
    if not scenarios_root.is_dir():
        print(
            f"error: scenarios root not found: {scenarios_root}", file=sys.stderr
        )
        return 2

    report = import_session_log(session_log, scenarios_root, capture_into)
    _print_report(report)
    if args.verbose_skips:
        for sid in report.skipped_no_match:
            print(f"  unmatched: {sid}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
