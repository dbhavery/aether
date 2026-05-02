"""Out-of-band training-progress monitor.

Lessons learned 2026-05-02 §8: tee + tqdm hides progress in log files
(tqdm uses \\r for in-place updates; tee buffers on \\n). Result: a
training run that's progressing fine looks frozen in the log.

This monitor watches the *filesystem* instead — checkpoints, tqdm
state files, output dir mtimes — and prints a summary every poll
interval. It does NOT parse the log file.

Usage (foreground, blocking until run completes or stalls):

    python tools/persona-lora-train/monitor_training.py \\
        --output-dir build/lora-train/aurora-v1/output \\
        --max-train-steps 1500 \\
        [--poll-seconds 60] [--stall-minutes 30]

Exit codes:
  0  — training completed (final adapter exists)
  1  — training stalled (no progress within `--stall-minutes`)
  2  — operator killed via Ctrl-C
  3  — output dir disappeared (training crashed)

Designed to run alongside an `accelerate launch` in another terminal.
Pure CPU/disk; no GPU touch.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path


@dataclasses.dataclass
class MonitorState:
    last_checkpoint_step: int = 0
    last_progress_time: float = 0.0
    final_adapter_seen: bool = False


_FINAL_ADAPTER_BASENAMES = (
    "pytorch_lora_weights.safetensors",
    "diffusion_pytorch_model.safetensors",
)


def _scan_checkpoints(output_dir: Path) -> list[int]:
    """Return sorted list of checkpoint step numbers found in `output_dir`."""
    if not output_dir.exists():
        return []
    steps: list[int] = []
    for child in output_dir.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        # diffusers convention: checkpoint-<step>
        if name.startswith("checkpoint-"):
            try:
                steps.append(int(name.split("-", 1)[1]))
            except ValueError:
                continue
    return sorted(steps)


def _detect_final_adapter(output_dir: Path) -> Path | None:
    """Return Path of the final LoRA adapter if it exists, else None."""
    if not output_dir.exists():
        return None
    for basename in _FINAL_ADAPTER_BASENAMES:
        candidate = output_dir / basename
        if candidate.exists():
            return candidate
    return None


def poll_once(output_dir: Path, state: MonitorState) -> tuple[str, MonitorState]:
    """One poll cycle. Returns (event_kind, updated_state).

    Event kinds:
      - "missing-output-dir"
      - "no-checkpoint-yet"
      - "checkpoint-progress"  (state updated)
      - "stall"                (no new checkpoint since last)
      - "final-adapter"
    """
    if not output_dir.exists():
        return ("missing-output-dir", state)

    final = _detect_final_adapter(output_dir)
    if final is not None:
        state = dataclasses.replace(state, final_adapter_seen=True)
        return ("final-adapter", state)

    steps = _scan_checkpoints(output_dir)
    now = time.time()
    if not steps:
        # No checkpoint yet. Update last_progress_time on first call only.
        if state.last_progress_time == 0.0:
            state = dataclasses.replace(state, last_progress_time=now)
        return ("no-checkpoint-yet", state)

    latest = steps[-1]
    if latest > state.last_checkpoint_step:
        state = dataclasses.replace(
            state,
            last_checkpoint_step=latest,
            last_progress_time=now,
        )
        return ("checkpoint-progress", state)

    return ("stall", state)


def run(
    output_dir: Path,
    *,
    max_train_steps: int | None = None,
    poll_seconds: int = 60,
    stall_minutes: int = 30,
    out_stream=None,
) -> int:
    """Block on `output_dir` until training completes or stalls.

    Returns exit code per module docstring.
    """
    out_stream = out_stream or sys.stderr
    state = MonitorState()
    stall_seconds = stall_minutes * 60

    print(
        f"[monitor] watching {output_dir} "
        f"(poll={poll_seconds}s, stall_threshold={stall_minutes}min, "
        f"max_steps={max_train_steps})",
        file=out_stream,
        flush=True,
    )

    try:
        while True:
            event, state = poll_once(output_dir, state)
            if event == "final-adapter":
                print(
                    f"[monitor] final adapter detected at "
                    f"{_detect_final_adapter(output_dir)} — training complete.",
                    file=out_stream,
                    flush=True,
                )
                return 0
            if event == "missing-output-dir":
                print(
                    f"[monitor] output dir {output_dir} disappeared — "
                    "training likely crashed.",
                    file=out_stream,
                    flush=True,
                )
                return 3
            if event == "checkpoint-progress":
                pct = (
                    f" ({100 * state.last_checkpoint_step / max_train_steps:.0f}%)"
                    if max_train_steps
                    else ""
                )
                print(
                    f"[monitor] step {state.last_checkpoint_step}{pct} "
                    f"checkpoint detected.",
                    file=out_stream,
                    flush=True,
                )
            elif event == "stall" or event == "no-checkpoint-yet":
                idle = time.time() - state.last_progress_time
                if idle > stall_seconds:
                    print(
                        f"[monitor] STALL — no checkpoint progress for "
                        f"{idle/60:.1f} min (threshold {stall_minutes}). "
                        "Last seen step "
                        f"{state.last_checkpoint_step}.",
                        file=out_stream,
                        flush=True,
                    )
                    return 1
                # Print a heartbeat occasionally so the operator knows
                # the monitor itself is alive.
                if int(idle) % 600 < poll_seconds:
                    print(
                        f"[monitor] idle {idle/60:.1f} min "
                        f"(last step {state.last_checkpoint_step}, "
                        f"stall in {stall_minutes - idle/60:.1f} min)",
                        file=out_stream,
                        flush=True,
                    )
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("[monitor] killed by operator (Ctrl-C).", file=out_stream, flush=True)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="monitor-training")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-train-steps", type=int, default=None)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--stall-minutes", type=int, default=30)
    args = parser.parse_args(argv)
    return run(
        args.output_dir,
        max_train_steps=args.max_train_steps,
        poll_seconds=args.poll_seconds,
        stall_minutes=args.stall_minutes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
