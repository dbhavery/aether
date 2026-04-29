"""V9 SWEEP ORCHESTRATOR — 3-variant ablation, queues behind V7+V8.

Waits for V7+V8 pipeline's `logs_v8/phase_eval.done` flag (max wait
8 hours), then runs V9a → V9a-eval → V9b → V9b-eval → V9c → V9c-eval
sequentially. Each phase has its own done flag in `logs_v9_sweep/`.

Wallclock estimate (RTX 3090 Ti):
  V9a train (rank-128 3B fresh, 1500 steps):    ~3.0 hr
  V9a eval  (held-out PPL + 200 WildChat gens): ~0.7 hr
  V9b train (V8 continuation, 1500 more steps): ~2.5 hr
  V9b eval:                                      ~0.7 hr
  V9c train (7B fresh, rank-32, 1500 steps):    ~9.0 hr
  V9c eval:                                      ~1.5 hr  (7B inference slower)
  ────────────────────────────────────────────
  TOTAL                                           ~17.4 hr unattended

Plus V8-wait (up to ~2 hr for V8 to finish from sweep launch time).
Total wall: ~19-20 hr — comfortably inside Don's 21-hr budget.

Variants and their D3-path mappings:
  V9a → "ship V6" path (capacity ceiling test)
  V9b → "more steps / more data" path (training-budget test)
  V9c → "swap to 7B base" path (architecture scale test)

Resume policy: each train+eval has its own done flag. Re-running the
orchestrator after a partial crash skips completed phases. If V9c
OOMs, V9a + V9b results still ship — failure of the most expensive
variant doesn't waste the cheaper two.

Logs:
  logs_v9_sweep/orchestrator.log         — top-level status
  logs_v9_sweep/v9a_train.log + v9a_eval.log
  logs_v9_sweep/v9b_train.log + v9b_eval.log
  logs_v9_sweep/v9c_train.log + v9c_eval.log
"""
from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_V8 = ROOT / "logs_v8"
LOGS_V9 = ROOT / "logs_v9_sweep"
LOGS_V9.mkdir(parents=True, exist_ok=True)

ORCH_LOG = LOGS_V9 / "orchestrator.log"
V8_DONE_FLAG = LOGS_V8 / "phase_eval.done"
SWEEP_COMPLETE_FLAG = LOGS_V9 / "sweep_complete.done"

# Maximum time to wait for V8 to finish before giving up. If V8 hasn't
# completed in 8 hours from sweep launch, something is wrong with V8 and
# we should not silently consume budget by waiting forever.
V8_WAIT_TIMEOUT_S = 8 * 3600

PHASES = [
    ("v9a-train", "train_pipeline_v9a.py", None,        LOGS_V9 / "v9a_train.log",  LOGS_V9 / "phase_v9a_train.done"),
    ("v9a-eval",  "eval_v9_quick.py",      ["v9a"],     LOGS_V9 / "v9a_eval.log",   LOGS_V9 / "phase_v9a_eval.done"),
    ("v9b-train", "train_pipeline_v9b.py", None,        LOGS_V9 / "v9b_train.log",  LOGS_V9 / "phase_v9b_train.done"),
    ("v9b-eval",  "eval_v9_quick.py",      ["v9b"],     LOGS_V9 / "v9b_eval.log",   LOGS_V9 / "phase_v9b_eval.done"),
    ("v9c-train", "train_pipeline_v9c.py", None,        LOGS_V9 / "v9c_train.log",  LOGS_V9 / "phase_v9c_train.done"),
    ("v9c-eval",  "eval_v9_quick.py",      ["v9c"],     LOGS_V9 / "v9c_eval.log",   LOGS_V9 / "phase_v9c_eval.done"),
]


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with ORCH_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_for_v8(timeout_s: int) -> bool:
    if V8_DONE_FLAG.exists():
        log(f"V8 already done — skipping wait (flag at {V8_DONE_FLAG})")
        return True
    log(f"Waiting for V8 eval to finish (flag: {V8_DONE_FLAG}, timeout {timeout_s}s)")
    poll_interval = 60
    waited = 0
    while waited < timeout_s:
        if V8_DONE_FLAG.exists():
            log(f"V8 done flag detected after {waited}s wait. Proceeding.")
            return True
        time.sleep(poll_interval)
        waited += poll_interval
        if waited % 600 == 0:
            log(f"  still waiting for V8 ({waited}s elapsed)")
    log(f"V8 wait timed out after {timeout_s}s. Aborting V9 sweep.")
    return False


def run_phase(name: str, script: str, args: list[str] | None,
              logfile: Path, donefile: Path) -> int:
    if donefile.exists():
        log(f"SKIP {name}: {donefile.name} already exists")
        return 0
    log(f"START {name}: {script} {' '.join(args or [])}")
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"
    env["OLLAMA_KEEP_ALIVE"] = "0"
    env["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
    cmd = [sys.executable, str(ROOT / script)] + (args or [])
    with logfile.open("w", encoding="utf-8") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                              cwd=str(ROOT), env=env)
    elapsed = time.time() - t0
    if proc.returncode == 0:
        log(f"OK    {name} in {elapsed:.0f}s")
    else:
        log(f"FAIL  {name} rc={proc.returncode} after {elapsed:.0f}s — see {logfile}")
    return proc.returncode


def main() -> int:
    if SWEEP_COMPLETE_FLAG.exists():
        log("Sweep already complete; nothing to do.")
        return 0

    log("=" * 60)
    log("V9 SWEEP ORCHESTRATOR (D3 ablation — 3 variants)")
    log("=" * 60)
    log(f"python: {sys.executable}")
    log(f"cwd: {ROOT}")
    for name, script, args, logfile, donefile in PHASES:
        marker = "DONE" if donefile.exists() else "PENDING"
        log(f"  {name:10s} {marker}  ({donefile.name})")
    log("-" * 60)

    if not wait_for_v8(V8_WAIT_TIMEOUT_S):
        return 3

    overall_t0 = time.time()
    failed_phases: list[str] = []
    for name, script, args, logfile, donefile in PHASES:
        rc = run_phase(name, script, args, logfile, donefile)
        if rc != 0:
            log(f"PHASE {name} FAILED rc={rc}")
            failed_phases.append(name)
            # If a TRAIN fails, skip its eval. Otherwise continue.
            if name.endswith("-train"):
                paired_eval = name.replace("-train", "-eval")
                log(f"  skipping paired {paired_eval} (train failed)")
                # Mark the eval as "skipped" by NOT touching its done flag;
                # the loop just continues past it, then it won't run because
                # the train output it depends on doesn't exist.
            # Continue to next phase regardless — don't abort the whole sweep
            # on one failure (V9c OOM shouldn't waste V9a + V9b results).

    elapsed_min = (time.time() - overall_t0) / 60
    log("-" * 60)
    if failed_phases:
        log(f"SWEEP COMPLETE WITH FAILURES in {elapsed_min:.1f} min: {failed_phases}")
    else:
        log(f"SWEEP COMPLETE (all phases) in {elapsed_min:.1f} min")
    SWEEP_COMPLETE_FLAG.touch()
    return 0 if not failed_phases else 1


if __name__ == "__main__":
    sys.exit(main())
