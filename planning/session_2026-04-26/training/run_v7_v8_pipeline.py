"""Orchestrator: run V7 train → V7 eval → V8 train → V8 eval, sequentially.

Each phase runs in a fresh Python subprocess so transformers/torch state
is fully released between phases. Each phase writes a `phase_*.done`
flag file so re-running the orchestrator after a crash skips completed
phases.

Wallclock estimate (RTX 3090 Ti, observed V6 pace 0.307 steps/s):
  V7 train  (1500 steps continuation):  ~85 min
  V7 eval   (200 + 200 + 25*8 gen):     ~50 min
  V8 train  (2200 steps rank-128 from base): ~135 min  (rank 128 ~10% slower per step)
  V8 eval   (200 + 200 + 25*8 gen):     ~50 min
  ────────────────────────────────────
  TOTAL                                  ~5h 20min unattended

Logs:
  logs_v7/orchestrator.log          — top-level status
  logs_v7/v7_train.log              — V7 training stdout/stderr
  logs_v7/v7_eval.log               — V7 eval stdout/stderr
  logs_v8/v8_train.log              — V8 training stdout/stderr
  logs_v8/v8_eval.log               — V8 eval stdout/stderr

Resume policy: each train/eval script checks its phase_*.done flag and
exits early if set. Re-running this orchestrator after a partial crash
is safe — it skips completed phases and continues from the failure point.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_V7 = ROOT / "logs_v7"
LOGS_V8 = ROOT / "logs_v8"
LOGS_V7.mkdir(parents=True, exist_ok=True)
LOGS_V8.mkdir(parents=True, exist_ok=True)

ORCH_LOG = LOGS_V7 / "orchestrator.log"

PHASES = [
    ("v7-train", "train_pipeline_v7.py", LOGS_V7 / "v7_train.log",   LOGS_V7 / "phase_train.done"),
    ("v7-eval",  "eval_v7.py",            LOGS_V7 / "v7_eval.log",   LOGS_V7 / "phase_eval.done"),
    ("v8-train", "train_pipeline_v8.py",  LOGS_V8 / "v8_train.log",  LOGS_V8 / "phase_train.done"),
    ("v8-eval",  "eval_v8.py",            LOGS_V8 / "v8_eval.log",   LOGS_V8 / "phase_eval.done"),
]


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with ORCH_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_phase(name: str, script: str, logfile: Path, donefile: Path) -> int:
    if donefile.exists():
        log(f"SKIP {name}: {donefile.name} already exists")
        return 0
    log(f"START {name}: {script}")
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"
    env["OLLAMA_KEEP_ALIVE"] = "0"
    env["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
    with logfile.open("w", encoding="utf-8") as lf:
        proc = subprocess.run(
            [sys.executable, str(ROOT / script)],
            stdout=lf, stderr=subprocess.STDOUT,
            cwd=str(ROOT), env=env,
        )
    elapsed = time.time() - t0
    if proc.returncode == 0:
        log(f"OK    {name} in {elapsed:.0f}s")
    else:
        log(f"FAIL  {name} rc={proc.returncode} after {elapsed:.0f}s — see {logfile}")
    return proc.returncode


def main() -> int:
    log("=" * 60)
    log("V7+V8 PIPELINE ORCHESTRATOR")
    log("=" * 60)
    log(f"python: {sys.executable}")
    log(f"cwd: {ROOT}")
    for name, script, logfile, donefile in PHASES:
        marker = "DONE" if donefile.exists() else "PENDING"
        log(f"  {name:10s} {marker}  ({donefile.name})")
    log("-" * 60)

    overall_t0 = time.time()
    for name, script, logfile, donefile in PHASES:
        rc = run_phase(name, script, logfile, donefile)
        if rc != 0:
            log(f"ABORT pipeline at phase {name} (rc={rc})")
            return rc
    log("-" * 60)
    log(f"ALL PHASES COMPLETE in {(time.time()-overall_t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
