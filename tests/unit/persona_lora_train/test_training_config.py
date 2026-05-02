"""Tests for training_config.build_plan + accelerate_command."""

from __future__ import annotations

import json
from pathlib import Path

import dataset_builder  # type: ignore[import-not-found]
import training_config  # type: ignore[import-not-found]


def _make_anchors(repo_root: Path, persona_slug: str = "aurora") -> None:
    avatar_dir = repo_root / "personas" / persona_slug / "avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    # Trivially valid PNG bytes (1x1) - the dataset builder copies
    # files but doesn't decode them.
    import struct
    import zlib

    sig = b"\x89PNG\r\n\x1a\n"
    raw = b"\x00\x01"
    chunk = lambda tag, data: (  # noqa: E731 — short lambda for test setup
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    body = sig + ihdr + idat + iend
    for name in ("anchor.png", "portrait.png", "profile_left.png", "profile_right.png"):
        (avatar_dir / name).write_bytes(body)


def test_build_plan_produces_dataset_and_config(tmp_path):
    _make_anchors(tmp_path)
    workdir = tmp_path / "workdir"

    plan = training_config.build_plan(
        "aurora",
        workdir,
        repo_root=tmp_path,
    )

    assert plan.persona_slug == "aurora"
    assert plan.instance_token == "aurora_nash"  # noqa: S105 — token, not password
    assert plan.num_training_images == 4

    # Dataset dir populated
    dataset_dir = workdir / "dataset"
    assert (dataset_dir / "metadata.json").exists()
    assert (dataset_dir / "images" / "00.png").exists()
    assert (dataset_dir / "captions" / "00.txt").exists()

    # Output dir created (training run writes here)
    assert (workdir / "output").is_dir()

    # Config snapshot written
    cfg_path = workdir / "training_config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["persona_slug"] == "aurora"
    assert cfg["num_training_images"] == 4


def test_accelerate_command_shape(tmp_path):
    _make_anchors(tmp_path)
    workdir = tmp_path / "workdir"
    plan = training_config.build_plan("aurora", workdir, repo_root=tmp_path)

    argv = plan.accelerate_command()
    assert argv[0] == "accelerate"
    assert argv[1] == "launch"

    flat = " ".join(argv)
    # Required FLUX LoRA training flags appear in the command.
    assert "--pretrained_model_name_or_path=black-forest-labs/FLUX.1-dev" in flat
    # diffusers DreamBooth wants images-only, so we point at the
    # `images/` subdir of the dataset_dir.
    assert f"--instance_data_dir={plan.dataset_dir}/images" in flat
    assert f"--output_dir={plan.output_dir}" in flat
    assert "--rank=16" in flat
    # Default resolution flipped to 512 in the throughput-tuned config
    # (lessons §10). 1024 is opt-in via --resolution override.
    assert "--resolution=512" in flat
    assert "--mixed_precision=bf16" in flat
    assert "--gradient_checkpointing" in argv  # boolean flag, no value
    assert "--cache_latents" in argv
    assert "--allow_tf32" in argv
    assert "--use_8bit_adam" in argv
    assert "--max_train_steps=1500" in flat
    assert "aurora_nash" in flat


def test_custom_hyperparams_propagate(tmp_path):
    _make_anchors(tmp_path)
    workdir = tmp_path / "workdir"
    hp = training_config.TrainingHyperparams(
        rank=32,
        max_train_steps=2500,
        learning_rate=5e-5,
        gradient_checkpointing=False,
    )
    plan = training_config.build_plan(
        "aurora", workdir, repo_root=tmp_path, hyperparams=hp,
    )
    flat = " ".join(plan.accelerate_command())
    assert "--rank=32" in flat
    assert "--max_train_steps=2500" in flat
    assert "--learning_rate=5e-05" in flat
    assert "--gradient_checkpointing" not in plan.accelerate_command()


def test_throughput_flags_can_be_disabled(tmp_path):
    """When the operator wants the original conservative config (no
    cache_latents / no TF32 / no 8-bit Adam), all three opt-out via
    boolean hyperparam flags."""
    _make_anchors(tmp_path)
    workdir = tmp_path / "workdir"
    hp = training_config.TrainingHyperparams(
        cache_latents=False,
        allow_tf32=False,
        use_8bit_adam=False,
    )
    plan = training_config.build_plan(
        "aurora", workdir, repo_root=tmp_path, hyperparams=hp,
    )
    argv = plan.accelerate_command()
    assert "--cache_latents" not in argv
    assert "--allow_tf32" not in argv
    assert "--use_8bit_adam" not in argv


def test_shell_command_round_trips(tmp_path):
    """shlex.join must produce a parseable shell command — assert no
    crashes and that the joined string is non-empty."""
    _make_anchors(tmp_path)
    workdir = tmp_path / "workdir"
    plan = training_config.build_plan("aurora", workdir, repo_root=tmp_path)
    shell = plan.shell_command()
    assert shell.startswith("accelerate launch ")
    assert "aurora_nash" in shell


def test_per_persona_token_default(tmp_path):
    """Personas without a registered token use the slug verbatim."""
    workdir = tmp_path / "workdir"
    plan = training_config.build_plan(
        "marcus_chen",
        workdir,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert plan.instance_token == "marcus_chen"  # noqa: S105 — token, not password
    flat = " ".join(plan.accelerate_command())
    assert "marcus_chen" in flat


def test_dataset_builder_re_exports_share_default_token():
    """Sanity: training_config and dataset_builder both look up
    aurora_nash for aurora — same source of truth."""
    assert dataset_builder.DEFAULT_INSTANCE_TOKEN_BY_PERSONA["aurora"] == "aurora_nash"
