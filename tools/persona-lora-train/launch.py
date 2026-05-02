"""Launcher for persona LoRA training runs.

Wraps `training_config.build_plan` + the accelerate command into one
flow:

  1. Materialise the training dataset under the workdir.
  2. Print the planned hyperparams + accelerate command.
  3. If `--execute` is passed AND the diffusers training script is
     resolvable, exec it. Otherwise print copy-paste instructions and
     exit cleanly.

Approval-gated by default (`--execute` opt-in). Don sees the plan
before any GPU work begins.

Usage (plan-only):

    python tools/persona-lora-train/launch.py \\
        --persona aurora \\
        --workdir build/lora-train/aurora-v1

Usage (plan + execute):

    python tools/persona-lora-train/launch.py \\
        --persona aurora \\
        --workdir build/lora-train/aurora-v1 \\
        --execute
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from training_config import (  # noqa: E402  — sys.path mutation above
    TrainingHyperparams,
    build_plan,
)


def _diffusers_script_resolvable(plan_script: str) -> bool:
    """True when the planner found a real path (absolute or relative
    that exists). False when it fell back to the bare filename."""
    if plan_script == "train_dreambooth_lora_flux.py":
        return False
    return Path(plan_script).exists()


def _check_runtime_prereqs() -> list[str]:
    """Return a list of human-readable warning strings for any
    runtime prereqs that look missing. Empty list = green light."""
    warnings: list[str] = []
    if shutil.which("accelerate") is None:
        warnings.append("`accelerate` not found on PATH — pip install accelerate")
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="persona-lora-train-launch",
        description=(
            "Plan and (optionally) launch a persona identity LoRA "
            "training run. Phase 3 of the bare-metal local inference "
            "pivot per HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md."
        ),
    )
    parser.add_argument("--persona", required=True)
    parser.add_argument(
        "--workdir",
        required=True,
        type=Path,
        help="working directory; dataset/, output/, and training_config.json land here.",
    )
    parser.add_argument(
        "--batch-ids",
        nargs="*",
        default=None,
        help="restrict to specific Step 1 batch ids; default = all batches",
    )
    parser.add_argument(
        "--no-anchor-set",
        action="store_true",
        help="exclude the persona's 4 v0 avatar anchor images from training",
    )
    parser.add_argument(
        "--instance-token",
        default=None,
        help="override per-persona instance token (default uses dataset_builder map)",
    )
    parser.add_argument("--rank", type=int, default=None)
    parser.add_argument("--max-train-steps", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--min-photoreal-score", type=int, default=6)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually run accelerate launch; otherwise print + exit",
    )
    args = parser.parse_args(argv)

    hyperparam_overrides: dict[str, object] = {}
    if args.rank is not None:
        hyperparam_overrides["rank"] = args.rank
    if args.max_train_steps is not None:
        hyperparam_overrides["max_train_steps"] = args.max_train_steps
    if args.learning_rate is not None:
        hyperparam_overrides["learning_rate"] = args.learning_rate
    hp = TrainingHyperparams(**hyperparam_overrides) if hyperparam_overrides else None

    plan = build_plan(
        persona_slug=args.persona,
        workdir=args.workdir,
        hyperparams=hp,
        batch_ids=args.batch_ids,
        include_anchor_set=not args.no_anchor_set,
        instance_token=args.instance_token,
        min_photoreal_score=args.min_photoreal_score,
    )

    print(f"[plan] persona={plan.persona_slug} token={plan.instance_token}")
    print(f"[plan] training images: {plan.num_training_images}")
    print(f"[plan] dataset_dir   : {plan.dataset_dir}")
    print(f"[plan] output_dir    : {plan.output_dir}")
    print(f"[plan] config snapshot: {Path(plan.workdir) / 'training_config.json'}")
    print(f"[plan] diffusers script: {plan.diffusers_script}")
    print()
    print("[plan] hyperparams:")
    for k, v in vars(plan.hyperparams).items():
        print(f"         {k}: {v}")
    print()

    warnings = _check_runtime_prereqs()
    for w in warnings:
        print(f"[warn] {w}")
    if warnings:
        print()

    print("[command] copy-paste to run manually:")
    print(f"  {plan.shell_command()}")
    print()

    if not args.execute:
        print("[plan-only] re-invoke with --execute to launch GPU training.")
        return 0

    if not _diffusers_script_resolvable(plan.diffusers_script):
        print(
            "[execute] diffusers train_dreambooth_lora_flux.py is not on disk. "
            "Clone https://github.com/huggingface/diffusers and ensure the "
            "script path is one of:"
        )
        from training_config import _DIFFUSERS_SCRIPT_CANDIDATES

        for c in _DIFFUSERS_SCRIPT_CANDIDATES:
            print(f"    {c}")
        return 2

    cmd = plan.accelerate_command()
    print(f"[execute] launching: {shlex.join(cmd)}")
    print(
        "[execute] this is a multi-hour run. Ctrl-C to abort. "
        "Output streams below.\n"
    )
    completed = subprocess.run(cmd, env=os.environ.copy(), check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
