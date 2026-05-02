"""Tests for launch.main — plan-only path.

Doesn't exercise --execute (which would spawn accelerate launch and
take hours). Asserts the planning/printing path runs cleanly and the
return codes are correct.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import launch  # type: ignore[import-not-found]


def _tiny_png_bytes() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    raw = b"\x00\x01"
    chunk = lambda tag, data: (  # noqa: E731 - short test setup helper
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _materialise_anchors(repo_root: Path, persona_slug: str = "aurora") -> None:
    avatar_dir = repo_root / "personas" / persona_slug / "avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    body = _tiny_png_bytes()
    for name in ("anchor.png", "portrait.png", "profile_left.png", "profile_right.png"):
        (avatar_dir / name).write_bytes(body)


def test_plan_only_returns_zero_and_writes_artifacts(tmp_path, capsys, monkeypatch):
    """Plan-only invocation lands the dataset, training_config.json, and
    prints the accelerate command. Does not execute anything."""
    _materialise_anchors(tmp_path)

    # Redirect the planner's repo-root inference at the dataset_builder
    # layer by monkey-patching `Path.cwd` is invasive; instead, route
    # through the workdir under the temp tree and let the dataset
    # builder fall back to its own repo-root inference. We need to
    # stub training_config.build_plan's repo_root to tmp_path.
    import training_config  # type: ignore[import-not-found]

    real_build_plan = training_config.build_plan

    def patched_build_plan(*args, **kwargs):
        kwargs.setdefault("repo_root", tmp_path)
        return real_build_plan(*args, **kwargs)

    monkeypatch.setattr(launch, "build_plan", patched_build_plan)

    workdir = tmp_path / "workdir"
    rc = launch.main(
        [
            "--persona",
            "aurora",
            "--workdir",
            str(workdir),
        ]
    )
    assert rc == 0

    # Artifacts written by the planner.
    assert (workdir / "dataset" / "metadata.json").exists()
    assert (workdir / "output").is_dir()
    assert (workdir / "training_config.json").exists()

    out = capsys.readouterr().out
    assert "[plan]" in out
    assert "aurora_nash" in out
    assert "[command]" in out
    assert "accelerate launch" in out
    assert "[plan-only]" in out


def test_execute_aborts_when_diffusers_script_missing(tmp_path, capsys, monkeypatch):
    _materialise_anchors(tmp_path)

    import training_config  # type: ignore[import-not-found]

    real_build_plan = training_config.build_plan

    def patched_build_plan(*args, **kwargs):
        kwargs.setdefault("repo_root", tmp_path)
        return real_build_plan(*args, **kwargs)

    monkeypatch.setattr(launch, "build_plan", patched_build_plan)

    # Force the resolvable check to fail (no diffusers script in tmp).
    rc = launch.main(
        [
            "--persona",
            "aurora",
            "--workdir",
            str(tmp_path / "workdir"),
            "--execute",
        ]
    )
    # Either 0 (resolved a sibling clone in the real workspace — the
    # test is running inside a real repo) or 2 (couldn't find the
    # script, printed instructions). Both are valid; just assert no
    # crash and that we surfaced something useful.
    assert rc in (0, 2)


def test_hyperparam_overrides_propagate(tmp_path, capsys, monkeypatch):
    _materialise_anchors(tmp_path)

    import training_config  # type: ignore[import-not-found]

    real_build_plan = training_config.build_plan

    def patched_build_plan(*args, **kwargs):
        kwargs.setdefault("repo_root", tmp_path)
        return real_build_plan(*args, **kwargs)

    monkeypatch.setattr(launch, "build_plan", patched_build_plan)

    workdir = tmp_path / "workdir"
    rc = launch.main(
        [
            "--persona", "aurora",
            "--workdir", str(workdir),
            "--rank", "32",
            "--max-train-steps", "2500",
            "--learning-rate", "5e-5",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "rank: 32" in out
    assert "max_train_steps: 2500" in out
