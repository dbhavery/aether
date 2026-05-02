"""Build a runnable training config + accelerate command for FLUX LoRA.

GPU-free planning step. Wraps `dataset_builder.build_dataset()` and
emits:

  - a flat training dataset under `<workdir>/dataset/`
  - a JSON config snapshot at `<workdir>/training_config.json`
  - the accelerate command that would launch
    `train_dreambooth_lora_flux.py` against it

Doesn't execute the training run. Don approves the snapshot, then
pulls the trigger via the documented command. Keeps the heavyweight
GPU step explicit and approval-gated rather than implicit in this
script.

Defaults are tuned for an RTX 3090 Ti (24 GB) running an Aurora-class
LoRA — rank 16, ~1500 steps, bf16 mixed precision, gradient
checkpointing on. They produce a ~50-100 MB adapter that loads on top
of black-forest-labs/FLUX.1-dev at inference time.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dataset_builder import DEFAULT_INSTANCE_TOKEN_BY_PERSONA, build_dataset

# Diffusers training script — the canonical FLUX LoRA trainer. Don
# clones diffusers somewhere accessible; the launcher walks a small
# search list to find it. If nothing matches, the printed command
# leaves it as `train_dreambooth_lora_flux.py` and the operator
# resolves manually.
_DIFFUSERS_SCRIPT_CANDIDATES = (
    Path("examples/dreambooth/train_dreambooth_lora_flux.py"),
    Path("../diffusers/examples/dreambooth/train_dreambooth_lora_flux.py"),
    Path("../../diffusers/examples/dreambooth/train_dreambooth_lora_flux.py"),
)


@dataclass
class TrainingHyperparams:
    """LoRA training hyperparams. Defaults tuned for Aurora-class
    identity LoRAs on a 3090 Ti."""

    rank: int = 16
    """LoRA rank. 16 is the sweet spot for single-subject identity
    locking on FLUX — higher overfits to training poses, lower under-
    fits the identity. 32 is reasonable for richer datasets (≥40 imgs)."""

    max_train_steps: int = 1500
    """Total training steps. 1000-2000 is the empirical range for
    24-image training sets at rank 16. ~6-8 hours on a 3090 Ti."""

    learning_rate: float = 1e-4
    """LoRA training LR — 1e-4 with cosine schedule is standard."""

    lr_scheduler: str = "cosine"
    lr_warmup_steps: int = 100

    train_batch_size: int = 1
    """Per-device batch size. 1 is required at FLUX's resolution on
    24 GB with gradient checkpointing on; raising this OOMs."""

    gradient_accumulation_steps: int = 4
    """Effective batch = train_batch_size * gradient_accumulation_steps
    = 4. Higher smooths LoRA training without VRAM cost."""

    mixed_precision: str = "bf16"
    """bf16 is the FLUX default; fp16 works but is slower on Ampere."""

    resolution: int = 1024
    """Training resolution. Matches inference target (1024×1536 for
    9:16). Rectangular bucketing is handled by the diffusers script
    when --random_flip is on."""

    gradient_checkpointing: bool = True
    """Required at 24 GB to fit FLUX-LoRA. Trades ~30% slower training
    for ~40% lower peak VRAM."""

    seed: int = 42

    # Saving cadence.
    checkpointing_steps: int = 500
    validation_epochs: int = 0  # 0 disables validation runs.

    base_model: str = "black-forest-labs/FLUX.1-dev"


@dataclass
class TrainingPlan:
    """Concrete plan produced by `build_plan()` — everything an operator
    needs to inspect or run the training step."""

    persona_slug: str
    instance_token: str
    workdir: str
    dataset_dir: str
    output_dir: str
    num_training_images: int
    hyperparams: TrainingHyperparams = field(default_factory=TrainingHyperparams)
    diffusers_script: str = "train_dreambooth_lora_flux.py"

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2, sort_keys=False)

    def accelerate_command(self) -> list[str]:
        """Return the argv list for `accelerate launch <script> ...`.

        Use `shlex.join(plan.accelerate_command())` for a copy-pasteable
        shell line.
        """
        h = self.hyperparams
        argv = [
            "accelerate",
            "launch",
            self.diffusers_script,
            f"--pretrained_model_name_or_path={h.base_model}",
            # dataset_builder writes images to <dataset_dir>/images/ so
            # diffusers' DreamBooth doesn't choke on the sibling captions.
            f"--instance_data_dir={self.dataset_dir}/images",
            f"--output_dir={self.output_dir}",
            f"--instance_prompt={self.instance_token}, photorealistic",
            f"--rank={h.rank}",
            f"--resolution={h.resolution}",
            f"--train_batch_size={h.train_batch_size}",
            f"--gradient_accumulation_steps={h.gradient_accumulation_steps}",
            f"--learning_rate={h.learning_rate}",
            f"--lr_scheduler={h.lr_scheduler}",
            f"--lr_warmup_steps={h.lr_warmup_steps}",
            f"--max_train_steps={h.max_train_steps}",
            f"--mixed_precision={h.mixed_precision}",
            f"--checkpointing_steps={h.checkpointing_steps}",
            f"--seed={h.seed}",
        ]
        if h.gradient_checkpointing:
            argv.append("--gradient_checkpointing")
        return argv

    def shell_command(self) -> str:
        return shlex.join(self.accelerate_command())


def _resolve_diffusers_script(repo_root: Path) -> str:
    """Walk a small search list looking for the canonical training
    script. Falls back to bare filename if nothing matches — the
    operator will resolve at run time."""
    for rel in _DIFFUSERS_SCRIPT_CANDIDATES:
        absolute = (repo_root / rel).resolve()
        if absolute.exists():
            return str(absolute.as_posix())
    return "train_dreambooth_lora_flux.py"


def build_plan(
    persona_slug: str,
    workdir: Path,
    *,
    repo_root: Path | None = None,
    hyperparams: TrainingHyperparams | None = None,
    batch_ids: list[str] | None = None,
    include_anchor_set: bool = True,
    instance_token: str | None = None,
    min_photoreal_score: int = 6,
    relax_selftest_verdict: bool = False,
) -> TrainingPlan:
    """Assemble a complete training plan for `persona_slug`.

    Side effects:
      - Creates `<workdir>/dataset/` populated with curated training
        images via `dataset_builder.build_dataset`.
      - Writes `<workdir>/training_config.json` with the full plan.

    Returns the TrainingPlan so the caller can print/inspect.
    """
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    dataset_dir = workdir / "dataset"
    output_dir = workdir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    instance_token = instance_token or DEFAULT_INSTANCE_TOKEN_BY_PERSONA.get(
        persona_slug, persona_slug
    )

    report = build_dataset(
        persona_slug=persona_slug,
        output_dir=dataset_dir,
        repo_root=repo_root,
        batch_ids=batch_ids,
        include_anchor_set=include_anchor_set,
        instance_token=instance_token,
        min_photoreal_score=min_photoreal_score,
        relax_selftest_verdict=relax_selftest_verdict,
    )

    plan = TrainingPlan(
        persona_slug=persona_slug,
        instance_token=instance_token,
        workdir=str(workdir.as_posix()),
        dataset_dir=str(dataset_dir.as_posix()),
        output_dir=str(output_dir.as_posix()),
        num_training_images=report.num_images,
        hyperparams=hyperparams or TrainingHyperparams(),
        diffusers_script=_resolve_diffusers_script(repo_root),
    )

    (workdir / "training_config.json").write_text(plan.to_json(), encoding="utf-8")
    return plan


__all__ = [
    "TrainingHyperparams",
    "TrainingPlan",
    "build_plan",
]
