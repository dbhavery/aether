"""End-to-end Phase 3 pipeline: dataset → smoke → full train → verify.

Single-command driver that takes a persona slug + workdir and produces
a verified trained LoRA. Each step is idempotent (skips when output
already exists). Bail-out on any failure exits non-zero with the failed
step name.

Usage (full pipeline):

    python tools/persona-lora-train/phase3_pipeline.py \\
      --persona aurora \\
      --workdir build/lora-train/aurora-v1 \\
      --execute

Usage (skip smoke, go straight to full):

    python tools/persona-lora-train/phase3_pipeline.py \\
      --persona aurora \\
      --workdir build/lora-train/aurora-v1 \\
      --skip-smoke --execute

Usage (dataset-only — just rebuild the training corpus):

    python tools/persona-lora-train/phase3_pipeline.py \\
      --persona aurora \\
      --workdir build/lora-train/aurora-v1 \\
      --dataset-only

Exit codes:
  0 — pipeline completed (LoRA trained + verified)
  1 — smoke-test stalled or failed
  2 — full-train stalled or failed
  3 — dataset build failed
  4 — verify failed (training succeeded but inference broken)
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from monitor_training import run as monitor_run  # noqa: E402
from training_config import TrainingHyperparams, build_plan  # noqa: E402


def _emit(msg: str) -> None:
    print(f"[phase3] {msg}", flush=True)


def _run_cmd(cmd: list[str], *, env: dict | None = None) -> int:
    """Run cmd in foreground, stream stdout/stderr to terminal. Returns rc."""
    _emit(f"$ {shlex.join(cmd)}")
    return subprocess.run(cmd, env=env or os.environ.copy(), check=False).returncode


def build_dataset_step(
    *,
    persona_slug: str,
    workdir: Path,
    repo_root: Path,
    relax_selftest_verdict: bool,
    min_photoreal_score: int,
) -> int:
    """Build the training dataset. Returns 0 on success, 3 on failure."""
    try:
        plan = build_plan(
            persona_slug=persona_slug,
            workdir=workdir,
            repo_root=repo_root,
            relax_selftest_verdict=relax_selftest_verdict,
            min_photoreal_score=min_photoreal_score,
        )
    except Exception as exc:  # noqa: BLE001 — operator wants the trace
        _emit(f"dataset build failed: {exc!r}")
        return 3

    _emit(f"dataset built: {plan.num_training_images} images at {plan.dataset_dir}")
    if plan.num_training_images < 8:
        _emit(
            f"WARNING: only {plan.num_training_images} images in corpus — "
            "LoRA may underfit. Recommended minimum 15."
        )
    return 0


def smoke_step(workdir: Path, *, base_argv: list[str]) -> int:
    """Run a 50-step smoke + monitor it."""
    smoke_workdir = workdir.with_name(workdir.name + "-smoke")
    cmd = [
        "python",
        str(_THIS_DIR / "launch.py"),
        *base_argv,
        "--workdir",
        str(smoke_workdir),
        "--smoke-test",
        "--execute",
    ]
    rc = _run_cmd(cmd)
    if rc != 0:
        _emit(f"smoke launch returned {rc}")
        return 1
    smoke_output = smoke_workdir / "output"
    # 50-step smoke at 512 res w/ throughput flags should checkpoint
    # within 20 min on a 3090 Ti. Stall threshold tighter than full run.
    monitor_rc = monitor_run(
        smoke_output,
        max_train_steps=50,
        poll_seconds=30,
        stall_minutes=25,
    )
    if monitor_rc != 0:
        _emit(f"smoke monitor returned {monitor_rc}")
        return 1
    _emit("smoke step completed cleanly")
    return 0


def full_train_step(
    workdir: Path,
    *,
    base_argv: list[str],
    max_train_steps: int,
    stall_minutes: int,
) -> int:
    """Run the full training in foreground + monitor in same process."""
    cmd = [
        "python",
        str(_THIS_DIR / "launch.py"),
        *base_argv,
        "--workdir",
        str(workdir),
        "--execute",
    ]
    rc = _run_cmd(cmd)
    if rc != 0:
        _emit(f"full train launch returned {rc}")
        return 2
    output_dir = workdir / "output"
    monitor_rc = monitor_run(
        output_dir,
        max_train_steps=max_train_steps,
        poll_seconds=120,
        stall_minutes=stall_minutes,
    )
    if monitor_rc != 0:
        _emit(f"full train monitor returned {monitor_rc}")
        return 2
    _emit("full train completed cleanly")
    return 0


def verify_step(
    *,
    persona_slug: str,
    workdir: Path,
    repo_root: Path,
    aspect_ratio: str,
    seed: int,
) -> int:
    """Run verify_lora --compare against the trained adapter."""
    refgen_dir = repo_root / "tools" / "persona-reference-gen"
    output_dir = workdir / "output"
    verify_dir = (
        repo_root / "personas" / persona_slug / "_pipeline" / "step3_lora_verify"
    )
    cmd = [
        "python",
        str(refgen_dir / "verify_lora.py"),
        "--persona",
        persona_slug,
        "--lora",
        str(output_dir),
        "--batch-id",
        f"verify-{persona_slug}-{workdir.name}",
        "--out-dir",
        str(verify_dir),
        "--aspect-ratio",
        aspect_ratio,
        "--seed",
        str(seed),
        "--compare",
    ]
    rc = _run_cmd(cmd)
    if rc != 0:
        _emit(f"verify returned {rc}")
        return 4
    _emit("verify step completed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phase3-pipeline")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--rank", type=int, default=None)
    parser.add_argument("--max-train-steps", type=int, default=1500)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--resolution", type=int, default=None)
    parser.add_argument("--base-model", default=None)
    parser.add_argument(
        "--no-cache-latents",
        action="store_true",
    )
    parser.add_argument(
        "--no-allow-tf32",
        action="store_true",
    )
    parser.add_argument(
        "--no-8bit-adam",
        action="store_true",
    )
    parser.add_argument(
        "--no-gradient-checkpointing",
        action="store_true",
    )
    parser.add_argument(
        "--no-relax-selftest",
        action="store_true",
        help=(
            "by default --relax-selftest-verdict is passed to launch.py "
            "(needed when 1:2 candidates have selftest=flag); use this "
            "flag to require pass-only candidates"
        ),
    )
    parser.add_argument("--min-photoreal-score", type=int, default=6)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--dataset-only", action="store_true")
    parser.add_argument("--verify-aspect-ratio", default="1:2")
    parser.add_argument("--verify-seed", type=int, default=8888)
    parser.add_argument(
        "--full-stall-minutes",
        type=int,
        default=60,
        help="stall threshold for full-train monitor (minutes)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run smoke+full+verify; otherwise dataset-build-only",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    workdir = args.workdir.resolve()

    # --- Step 1: dataset build ---
    rc = build_dataset_step(
        persona_slug=args.persona,
        workdir=workdir,
        repo_root=repo_root,
        relax_selftest_verdict=not args.no_relax_selftest,
        min_photoreal_score=args.min_photoreal_score,
    )
    if rc != 0:
        return rc

    if args.dataset_only or not args.execute:
        _emit("stopping after dataset build (no --execute)")
        return 0

    # Build the launch.py argv carry-through (excluding --workdir).
    base_argv = ["--persona", args.persona]
    if not args.no_relax_selftest:
        base_argv.append("--relax-selftest-verdict")
    if args.rank is not None:
        base_argv.extend(["--rank", str(args.rank)])
    if args.max_train_steps is not None:
        base_argv.extend(["--max-train-steps", str(args.max_train_steps)])
    if args.learning_rate is not None:
        base_argv.extend(["--learning-rate", str(args.learning_rate)])
    if args.resolution is not None:
        base_argv.extend(["--resolution", str(args.resolution)])
    if args.base_model is not None:
        base_argv.extend(["--base-model", args.base_model])
    if args.no_cache_latents:
        base_argv.append("--no-cache-latents")
    if args.no_allow_tf32:
        base_argv.append("--no-allow-tf32")
    if args.no_8bit_adam:
        base_argv.append("--no-8bit-adam")
    if args.no_gradient_checkpointing:
        base_argv.append("--no-gradient-checkpointing")
    base_argv.extend(["--min-photoreal-score", str(args.min_photoreal_score)])

    # --- Step 2: smoke (optional) ---
    if not args.skip_smoke:
        rc = smoke_step(workdir, base_argv=base_argv)
        if rc != 0:
            return rc

    # --- Step 3: full train ---
    rc = full_train_step(
        workdir,
        base_argv=base_argv,
        max_train_steps=args.max_train_steps,
        stall_minutes=args.full_stall_minutes,
    )
    if rc != 0:
        return rc

    # --- Step 4: verify ---
    rc = verify_step(
        persona_slug=args.persona,
        workdir=workdir,
        repo_root=repo_root,
        aspect_ratio=args.verify_aspect_ratio,
        seed=args.verify_seed,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
