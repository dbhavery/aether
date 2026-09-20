"""Print the per-stage latency breakdown from the turn trace log.

Answers "show me the trace, what is the breakdown by stage" from recorded data
rather than from memory of a run. Reads ``<data_dir>/traces.jsonl``, which is
append-only, so any figure can be reproduced later instead of only observed
once.

    py -V:3.13 tools/trace-bench/report.py
    py -V:3.13 tools/trace-bench/report.py --last 5
    py -V:3.13 tools/trace-bench/report.py --turn 4f2ac1b8de90

Set AETHER_DATA_DIR to read a bench run's log instead of the installed app's.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.core.trace import STAGE_ORDER, UNINSTRUMENTED_STAGES, read_traces, traces_path  # noqa: E402


def _fmt_ms(value: object) -> str:
    if value is None:
        return "     n/a"
    return f"{float(value):8.1f}"


def _stage_rows(record: dict) -> list[tuple[str, float]]:
    """Stages in display order, with anything unknown appended alphabetically."""
    stages = dict(record.get("stages_ms") or {})
    stages.pop("turn_total_ms", None)
    known = [(n, stages.pop(n)) for n in STAGE_ORDER if n in stages]
    return known + sorted(stages.items())


def print_turn(record: dict) -> None:
    total = record.get("turn_total_ms") or 0.0
    print(f"turn {record.get('turn_id')}  source={record.get('source')}  {record.get('ts')}")

    meta_all = record.get("meta") or {}
    if meta_all.get("turn_ok") is False:
        print("  *** FAILED TURN. These timings measure an error path, not a response. ***")
        print(f"  *** {meta_all.get('error', 'no error recorded')} ***")
    elif "turn_ok" not in meta_all:
        print("  *** INCOMPLETE TURN: the brain never reached the success path. ***")

    meta = record.get("meta") or {}
    if meta:
        parts = [f"{k}={v}" for k, v in meta.items() if v is not None]
        print("  context: " + ", ".join(parts))

    print(f"  {'stage':<24}{'ms':>9}   share")
    print(f"  {'-' * 24}{'-' * 9}   -----")
    for name, ms in _stage_rows(record):
        share = (ms / total * 100.0) if total else 0.0
        print(f"  {name:<24}{_fmt_ms(ms)}   {share:5.1f}%")

    unaccounted = record.get("unaccounted_ms")
    if unaccounted is not None:
        share = (float(unaccounted) / total * 100.0) if total else 0.0
        label = "unaccounted" if float(unaccounted) > 1.0 else "unaccounted (none)"
        print(f"  {label:<24}{_fmt_ms(unaccounted)}   {share:5.1f}%")

    marks = record.get("marks_ms") or {}
    for name, ms in sorted(marks.items(), key=lambda kv: kv[1]):
        print(f"  {'@ ' + name:<24}{_fmt_ms(ms)}   (offset from turn start)")

    concurrent = record.get("concurrent_stages") or []
    if concurrent:
        print(f"  (excluded from the sum, runs concurrently: {', '.join(concurrent)})")

    first_audio = record.get("first_audio_ms")
    print()
    print(f"  RESPONSE LATENCY (input complete -> first audio out): {_fmt_ms(first_audio)} ms")
    print(f"  turn total (INCLUDES playing the whole reply aloud):  {_fmt_ms(total)} ms")

    uninstrumented = record.get("uninstrumented") or UNINSTRUMENTED_STAGES
    if uninstrumented:
        print()
        print("  not measured:")
        for name, reason in uninstrumented.items():
            print(f"    {name}: {reason}")
    print()


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last", type=int, default=1, help="how many recent turns to print")
    parser.add_argument("--turn", help="print one turn by id")
    parser.add_argument("--json", action="store_true", help="dump raw records instead")
    args = parser.parse_args()

    path = traces_path()
    records = await read_traces(limit=0 if args.turn else args.last)
    if not records:
        print(f"No traces recorded yet at {path.as_posix()}")
        print()
        print("A trace is written per turn, but only when the user opted in to")
        print("usage counters (aether.telemetry.usage_counters in config.yaml).")
        return 1

    if args.turn:
        records = [r for r in records if str(r.get("turn_id")) == args.turn]
        if not records:
            print(f"No turn with id {args.turn} in {path.as_posix()}")
            return 1

    if args.json:
        print(json.dumps(records, indent=2))
        return 0

    print(f"source: {path.as_posix()}")
    print()
    for record in records:
        print_turn(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
