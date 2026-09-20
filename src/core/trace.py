"""Per-stage latency tracing for one conversational turn.

Before this module the repo contained no timing instrument at all:
``time.perf_counter`` appeared zero times in the tree, so every latency figure
that had ever been published about Aether was unreproducible. This module is
the instrument. It measures, it does not estimate.

What it measures
----------------
A turn is traced from the moment the user's input is complete (push-to-talk
release for voice, message submit for text) through to the end of the
response. Stages are recorded with ``time.perf_counter``, the monotonic clock,
so a system clock adjustment mid-turn cannot corrupt a duration.

Two different numbers come out of a voice turn and they must not be confused:

``first_audio_ms``
    Input complete -> first PCM chunk of the reply published. This is the
    perceived response latency and it is the only number that should ever be
    quoted as "end to end latency".

``turn_total_ms``
    Input complete -> the whole turn finished. ``src.voice.tts_handler`` awaits
    ``play_audio`` alongside chunk publication, so this figure INCLUDES the
    full duration of the spoken reply. A long answer produces a large number
    here and that is not latency. Quoting it as latency would be wrong.

How the trace follows the turn
------------------------------
Aether's modules are decoupled through ``src.core.events.EventBus``, which
dispatches each handler in a fresh ``asyncio.create_task``. Tasks inherit a
copy of the creating context, so a :class:`contextvars.ContextVar` propagates
down the causal chain: voice pipeline -> brain -> TTS -> avatar. That is why
the current trace is held in a ContextVar and not in a module global. Two
concurrent turns cannot see each other's trace, and nothing needs to thread a
trace object through function signatures that would otherwise not want one.

``EventBus.publish`` awaits ``asyncio.gather`` over those tasks, so when the
voice pipeline's ``publish(USER_MESSAGE)`` returns, every downstream stage has
already recorded itself.

Stages that are NOT instrumented, and why
-----------------------------------------
``wake_word``
    Does not exist in v1.0. Per docs/PRODUCT-PLAN.md §1 decision 10, push to
    talk replaced wake word and the wake-word modules were removed during the
    port. There is no code on this path to time.

``vad``
    ``src/voice/vad.py`` exists but nothing imports it. The push-to-talk
    pipeline captures between USER_SPEECH_START and USER_SPEECH_END and hands
    the buffer straight to STT; no voice-activity detection runs on the live
    path.

Both are listed in :data:`UNINSTRUMENTED_STAGES` with their reason, and they
are reported as uninstrumented rather than as zero. A zero would read as
"instant" and would be a fabricated measurement.

Consent
-------
Traces are data about how the user used the app, so nothing is recorded or
exposed unless :func:`src.shared.config.usage_counters_enabled` returns True.
When consent is absent the timings are measured, discarded, and never written
to disk, and the health endpoint reports the gate as closed rather than
reporting zeroes that could be mistaken for fast responses.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

from loguru import logger

from src.shared.config import usage_counters_enabled

# ---------------------------------------------------------------------------
# Stage vocabulary
# ---------------------------------------------------------------------------

# Ordered for display. A turn records the subset that actually ran: a text-mode
# turn has no stt and no tts, a voice turn has all of them.
STAGE_ORDER: Final[tuple[str, ...]] = (
    "stt",
    "tier_routing",
    "context_build",
    "llm_complete",
    "response_format",
    "tts_synth",
    "tts_publish_and_play",
    "avatar_speaking",
    "meter",
    "memory_persist",
)

# Stages that run concurrently with another stage rather than after it, so
# adding them into a total would double-count wall-clock time. EventBus
# dispatches every handler of one event as parallel tasks, so the avatar's
# set_speaking call overlaps TTS synthesis: both handle RESPONSE_TEXT_READY.
CONCURRENT_STAGES: Final[frozenset[str]] = frozenset({"avatar_speaking"})

# Stage name -> why it carries no measurement. Reported explicitly so a missing
# stage is never read as a zero-cost stage.
UNINSTRUMENTED_STAGES: Final[dict[str, str]] = {
    "wake_word": (
        "not present in v1.0 - push-to-talk replaced wake word "
        "(docs/PRODUCT-PLAN.md section 1 decision 10) and the modules were removed"
    ),
    "vad": (
        "src/voice/vad.py is imported by nothing - the push-to-talk pipeline "
        "hands the captured buffer straight to STT, so no VAD runs on the live path"
    ),
}

# How many finished traces to keep in memory for the /health rolling summary.
_RING_SIZE: Final[int] = 100

TurnSource = Literal["voice", "text", "unknown"]


# ---------------------------------------------------------------------------
# Trace object
# ---------------------------------------------------------------------------


@dataclass
class TurnTrace:
    """Timings for one turn. Durations are milliseconds off a monotonic clock."""

    turn_id: str
    source: TurnSource
    started_wall: float
    _t0: float
    stages: dict[str, float] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    finished: bool = False

    # -- recording ----------------------------------------------------------

    def elapsed_ms(self) -> float:
        """Milliseconds since the turn started."""
        return (time.perf_counter() - self._t0) * 1000.0

    def record_stage(self, name: str, duration_ms: float) -> None:
        """Record how long ``name`` took. Repeat calls for one stage accumulate.

        Accumulating matters for stages that can run more than once in a turn,
        such as a TTS synth per sentence.
        """
        self.stages[name] = self.stages.get(name, 0.0) + max(0.0, duration_ms)

    def mark(self, name: str) -> None:
        """Record the offset from turn start at which ``name`` first happened.

        First write wins. ``first_audio_ms`` must be the FIRST chunk out, so a
        later chunk must not overwrite it.
        """
        if name not in self.marks:
            self.marks[name] = self.elapsed_ms()

    def set_meta(self, **values: Any) -> None:
        """Attach context to the trace: model, tier, provider, transcript length."""
        self.meta.update(values)

    # -- serialisation ------------------------------------------------------

    def accounted_ms(self) -> float:
        """Sum of the sequential stages, excluding concurrent ones.

        Compared against the turn total this exposes unmeasured time. A
        breakdown that accounts for a third of its own turn is not a breakdown,
        so the gap is published rather than left for the reader to notice.
        """
        return sum(
            ms
            for name, ms in self.stages.items()
            if name != "turn_total_ms" and name not in CONCURRENT_STAGES
        )

    def to_record(self) -> dict[str, Any]:
        """Flat JSON-serialisable record, one per finished turn."""
        total = self.stages.get("turn_total_ms", self.elapsed_ms())
        accounted = self.accounted_ms()
        return {
            "ts": datetime.fromtimestamp(self.started_wall, tz=UTC).isoformat(timespec="milliseconds"),
            "epoch": self.started_wall,
            "turn_id": self.turn_id,
            "source": self.source,
            "stages_ms": {k: round(v, 2) for k, v in self.stages.items()},
            "marks_ms": {k: round(v, 2) for k, v in self.marks.items()},
            "first_audio_ms": (round(self.marks["first_audio_ms"], 2) if "first_audio_ms" in self.marks else None),
            "turn_total_ms": round(total, 2),
            "accounted_ms": round(accounted, 2),
            "unaccounted_ms": round(max(0.0, total - accounted), 2),
            "concurrent_stages": sorted(CONCURRENT_STAGES),
            "uninstrumented": dict(UNINSTRUMENTED_STAGES),
            "meta": dict(self.meta),
        }

    # -- completion ---------------------------------------------------------

    async def finish(self) -> dict[str, Any] | None:
        """Close the turn, persist it, and return the record.

        Returns ``None`` when the user has not opted in to usage counters, in
        which case nothing is written and nothing is kept in memory.
        """
        if self.finished:
            logger.debug(f"trace: turn {self.turn_id} already finished; ignoring second finish()")
            return None
        self.finished = True
        self.record_stage("turn_total_ms", self.elapsed_ms())
        record = self.to_record()

        if not usage_counters_enabled():
            logger.debug("trace: usage counters declined; turn timings discarded")
            return None

        _ring.append(record)
        await _append_record(record)
        logger.info(
            f"trace: turn {self.turn_id} ({self.source}) "
            f"first_audio={record['first_audio_ms']}ms "
            f"total={record['turn_total_ms']}ms "
            f"stages={record['stages_ms']}"
        )
        return record


# ---------------------------------------------------------------------------
# Current-turn plumbing
# ---------------------------------------------------------------------------

_current: ContextVar[TurnTrace | None] = ContextVar("aether_current_turn_trace", default=None)

# Finished traces, newest last. In-memory only, cleared on restart.
_ring: deque[dict[str, Any]] = deque(maxlen=_RING_SIZE)


def start_turn(source: TurnSource = "unknown", **meta: Any) -> TurnTrace:
    """Open a trace for a new turn and make it current for this context."""
    trace = TurnTrace(
        turn_id=uuid.uuid4().hex[:12],
        source=source,
        started_wall=time.time(),
        _t0=time.perf_counter(),
    )
    if meta:
        trace.set_meta(**meta)
    _current.set(trace)
    return trace


def current_turn() -> TurnTrace | None:
    """Return the trace for the turn being handled in this context, if any."""
    return _current.get()


@contextlib.contextmanager
def stage(name: str):
    """Time a block and record it against the current turn.

    A no-op when no turn is being traced, so call sites need no guard::

        with stage("stt"):
            text = await transcribe(audio, rate)
    """
    trace = _current.get()
    if trace is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        trace.record_stage(name, (time.perf_counter() - t0) * 1000.0)


def mark(name: str) -> None:
    """Record an instant against the current turn. No-op when untraced."""
    trace = _current.get()
    if trace is not None:
        trace.mark(name)


def set_meta(**values: Any) -> None:
    """Attach metadata to the current turn. No-op when untraced."""
    trace = _current.get()
    if trace is not None:
        trace.set_meta(**values)


async def finish_turn() -> dict[str, Any] | None:
    """Close the current turn if there is one. Returns the record or None."""
    trace = _current.get()
    if trace is None:
        return None
    return await trace.finish()


# ---------------------------------------------------------------------------
# Persistence - append-only JSONL beside usage.jsonl
# ---------------------------------------------------------------------------


def traces_path() -> Path:
    """Path to the append-only trace log in the user's data directory."""
    from src.shared.paths import get_data_dir

    return get_data_dir() / "traces.jsonl"


async def _append_record(record: dict[str, Any]) -> None:
    """Append one trace as a JSON line. Never raises on I/O failure.

    Same shape and failure policy as ``src.brain.cost.track_usage``: a turn is
    not worth failing over a log write, but the failure is reported.
    """
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    path = traces_path()

    def _append() -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)

    try:
        await asyncio.to_thread(_append)
    except OSError as exc:
        logger.error(f"trace: failed to append turn trace to {path}: {exc}")


async def read_traces(limit: int = 20) -> list[dict[str, Any]]:
    """Read the most recent ``limit`` traces off disk, oldest first.

    Reads the file rather than the in-memory ring so a figure survives a
    restart and can be reproduced later instead of only observed once.
    """
    path = traces_path()
    if not path.exists():
        return []

    def _scan() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        out.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.error(f"trace: failed to read {path}: {exc}")
            return []
        return out[-limit:] if limit > 0 else out

    return await asyncio.to_thread(_scan)


# ---------------------------------------------------------------------------
# Rolling summary for /health
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Empty input returns 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil((pct / 100.0) * len(ordered))
    idx = min(len(ordered) - 1, max(0, rank - 1))
    return round(ordered[idx], 2)


def get_latency_summary() -> dict[str, Any]:
    """Per-stage latency summary over the traces held in memory.

    Reports the consent state explicitly. When counters are declined the block
    is empty rather than zeroed, because a zero would read as "instant".
    """
    if not usage_counters_enabled():
        return {
            "usage_counters_enabled": False,
            "note": "per-stage latency is not recorded because usage counters were declined",
            "uninstrumented": dict(UNINSTRUMENTED_STAGES),
        }

    by_stage: dict[str, list[float]] = {}
    first_audio: list[float] = []
    for rec in _ring:
        for name, ms in (rec.get("stages_ms") or {}).items():
            by_stage.setdefault(name, []).append(float(ms))
        for name, ms in (rec.get("marks_ms") or {}).items():
            by_stage.setdefault(name, []).append(float(ms))
        fa = rec.get("first_audio_ms")
        if fa is not None:
            first_audio.append(float(fa))

    stages_summary = {
        name: {
            "count": len(vals),
            "p50_ms": _percentile(vals, 50),
            "p95_ms": _percentile(vals, 95),
            "min_ms": round(min(vals), 2),
            "max_ms": round(max(vals), 2),
        }
        for name, vals in sorted(by_stage.items(), key=lambda kv: _stage_sort_key(kv[0]))
    }

    return {
        "usage_counters_enabled": True,
        "turns_in_window": len(_ring),
        "first_audio_ms": {
            "count": len(first_audio),
            "p50": _percentile(first_audio, 50),
            "p95": _percentile(first_audio, 95),
        },
        "stages": stages_summary,
        "last_turn": _ring[-1] if _ring else None,
        "uninstrumented": dict(UNINSTRUMENTED_STAGES),
    }


def _stage_sort_key(name: str) -> tuple[int, str]:
    try:
        return (STAGE_ORDER.index(name), name)
    except ValueError:
        return (len(STAGE_ORDER), name)


def reset_for_tests() -> None:
    """Clear the in-memory ring and the current trace. Test-support only."""
    _ring.clear()
    _current.set(None)
