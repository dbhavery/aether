"""Tests for promote_lora — atomic copy + metadata sidecar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import promote_lora  # type: ignore[import-not-found]


def _make_workdir(tmp_path: Path, *, with_adapter: bool = True) -> Path:
    workdir = tmp_path / "wd"
    output = workdir / "output"
    output.mkdir(parents=True)
    if with_adapter:
        (output / "pytorch_lora_weights.safetensors").write_bytes(b"hello world" * 10)
    config = {
        "persona_slug": "aurora",
        "instance_token": "aurora_nash",  # noqa: S105 — token, not password
        "num_training_images": 27,
        "hyperparams": {
            "rank": 16,
            "max_train_steps": 1500,
            "learning_rate": 1e-4,
            "resolution": 512,
            "base_model": "black-forest-labs/FLUX.1-dev",
        },
    }
    (workdir / "training_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    return workdir


def test_module_surface():
    assert hasattr(promote_lora, "promote")
    assert hasattr(promote_lora, "main")


def test_promote_copies_with_metadata(tmp_path):
    workdir = _make_workdir(tmp_path)
    repo_root = tmp_path / "repo"

    dest = promote_lora.promote(
        persona_slug="aurora",
        workdir=workdir,
        version="v1",
        repo_root=repo_root,
    )

    assert dest == repo_root / "personas" / "aurora" / "loras" / "aurora_v1.safetensors"
    assert dest.exists()
    # Byte-for-byte equal to source.
    src_bytes = (workdir / "output" / "pytorch_lora_weights.safetensors").read_bytes()
    assert dest.read_bytes() == src_bytes

    meta = json.loads(dest.with_suffix(".safetensors.meta.json").read_text())
    assert meta["persona_slug"] == "aurora"
    assert meta["version"] == "v1"
    assert meta["base_model"] == "black-forest-labs/FLUX.1-dev"
    assert meta["rank"] == 16
    assert meta["max_train_steps"] == 1500
    assert meta["resolution"] == 512
    assert meta["instance_token"] == "aurora_nash"  # noqa: S105 — token, not password
    assert meta["num_training_images"] == 27
    assert meta["sha256"] == hashlib.sha256(src_bytes).hexdigest()


def test_promote_idempotent_when_dest_matches(tmp_path):
    """Re-running with the same source + version should not re-copy."""
    workdir = _make_workdir(tmp_path)
    repo_root = tmp_path / "repo"

    dest = promote_lora.promote(
        persona_slug="aurora",
        workdir=workdir,
        version="v1",
        repo_root=repo_root,
    )
    mtime_first = dest.stat().st_mtime_ns

    dest2 = promote_lora.promote(
        persona_slug="aurora",
        workdir=workdir,
        version="v1",
        repo_root=repo_root,
    )
    assert dest2 == dest
    # mtime unchanged — second call short-circuited.
    assert dest.stat().st_mtime_ns == mtime_first


def test_promote_refuses_overwrite_with_different_content(tmp_path):
    workdir = _make_workdir(tmp_path)
    repo_root = tmp_path / "repo"

    promote_lora.promote(
        persona_slug="aurora",
        workdir=workdir,
        version="v1",
        repo_root=repo_root,
    )
    # Now mutate the source — second promote should refuse to overwrite.
    (workdir / "output" / "pytorch_lora_weights.safetensors").write_bytes(b"different")

    raised = False
    try:
        promote_lora.promote(
            persona_slug="aurora",
            workdir=workdir,
            version="v1",
            repo_root=repo_root,
        )
    except ValueError as exc:
        assert "refuse to overwrite" in str(exc)
        raised = True
    assert raised


def test_promote_finds_alternative_safetensors(tmp_path):
    """When pytorch_lora_weights.safetensors doesn't exist but exactly one
    other .safetensors does, promote uses it."""
    workdir = tmp_path / "wd"
    output = workdir / "output"
    output.mkdir(parents=True)
    (output / "alternate_name.safetensors").write_bytes(b"alt content")
    (workdir / "training_config.json").write_text("{}", encoding="utf-8")

    repo_root = tmp_path / "repo"
    dest = promote_lora.promote(
        persona_slug="aurora",
        workdir=workdir,
        version="v1",
        repo_root=repo_root,
    )
    assert dest.read_bytes() == b"alt content"


def test_promote_raises_when_no_adapter(tmp_path):
    workdir = _make_workdir(tmp_path, with_adapter=False)
    # Ensure the empty output dir actually has no .safetensors files.
    (workdir / "output" / "pytorch_lora_weights.safetensors").unlink(missing_ok=True)
    repo_root = tmp_path / "repo"

    raised = False
    try:
        promote_lora.promote(
            persona_slug="aurora",
            workdir=workdir,
            version="v1",
            repo_root=repo_root,
        )
    except FileNotFoundError as exc:
        assert "no adapter found" in str(exc)
        raised = True
    assert raised


def test_main_cli_smoke(tmp_path, capsys):
    workdir = _make_workdir(tmp_path)
    repo_root = tmp_path / "repo"
    rc = promote_lora.main([
        "--persona", "aurora",
        "--workdir", str(workdir),
        "--version", "v1",
        "--repo-root", str(repo_root),
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "[promote] aurora/v1" in captured
    assert (repo_root / "personas" / "aurora" / "loras" / "aurora_v1.safetensors").exists()


def test_main_cli_handles_missing_adapter(tmp_path, capsys):
    workdir = tmp_path / "wd"
    (workdir / "output").mkdir(parents=True)
    rc = promote_lora.main([
        "--persona", "aurora",
        "--workdir", str(workdir),
        "--version", "v1",
        "--repo-root", str(tmp_path / "repo"),
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no adapter found" in err
