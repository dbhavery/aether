"""End-to-end smoke: run a batch through the stub backend, verify outputs.

Uses tmp_path-style isolation by monkey-patching `_REPO_ROOT` on the
runner module so we don't write into the real `personas/` tree.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

import runner  # type: ignore[import-not-found]
from output_schema import read_manifest  # type: ignore[import-not-found]
from prompt_matrix import MatrixAxes  # type: ignore[import-not-found]


def _isolate_repo_root(tmp_path: Path, monkeypatch) -> Path:
    """Redirect runner._REPO_ROOT to a tmp dir with a stub persona.yaml."""
    fake_root = tmp_path / "repo"
    persona_dir = fake_root / "personas" / "aurora"
    persona_dir.mkdir(parents=True)
    (persona_dir / "persona.yaml").write_text("id: aurora\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_REPO_ROOT", fake_root)
    return fake_root


def test_run_batch_stub_writes_manifest_and_images(tmp_path, monkeypatch):
    # Force stub mode regardless of dev shell env.
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    fake_root = _isolate_repo_root(tmp_path, monkeypatch)

    # Smaller axes so smoke is fast.
    small = MatrixAxes(
        framings=("full-body shot, head to feet visible, standing, neutral pose",),
        lightings=("soft natural daylight from a north-facing window",),
        seeds=(101, 202),
    )
    manifest = runner.run_batch(
        persona_slug="aurora",
        batch_id="smoke-1",
        axes=small,
        notes="smoke test",
    )

    out_dir = fake_root / "personas" / "aurora" / "_pipeline" / "step1_references" / "smoke-1"
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "images").is_dir()

    # 2 prompts × 1 image_per_prompt = 2 candidates.
    assert len(manifest.prompts) == 2
    assert len(manifest.candidates) == 2

    # Every recorded image actually exists on disk.
    for c in manifest.candidates:
        assert (out_dir / c.image_path).exists()
        assert c.backend == "stub"
        assert c.sha256 and len(c.sha256) == 64

    # Manifest round-trips.
    m2 = read_manifest(out_dir / "manifest.json")
    assert m2.to_dict() == manifest.to_dict()


def test_cli_parses(monkeypatch, tmp_path):
    """The CLI parses required args and runs through stub backend without error."""
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    _isolate_repo_root(tmp_path, monkeypatch)

    # Minimal axes: monkey-patch MatrixAxes.default to a 1x1x1 to keep CLI smoke cheap.
    import prompt_matrix as pm  # type: ignore[import-not-found]

    minimal = MatrixAxes(
        framings=("full-body shot, head to feet visible, standing, neutral pose",),
        lightings=("soft natural daylight from a north-facing window",),
        seeds=(101,),
    )
    monkeypatch.setattr(pm.MatrixAxes, "default", classmethod(lambda cls: minimal))

    rc = runner._main(
        [
            "--persona", "aurora",
            "--batch", "cli-smoke",
            "--notes", "cli-smoke",
        ]
    )
    assert rc == 0
