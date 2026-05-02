"""Stub-path + import smoke for the local-flux backend.

Phase 0 of the bare-metal pivot — the live path loads FLUX.1-dev (24GB)
which is not appropriate for unit tests, so we exercise:

  1. module import (catches missing deps / typos in the lazy seam)
  2. stub PNG output shape (mirrors fal stub for caller-symmetry)
  3. aspect-ratio dim mapping (deterministic, no GPU)
  4. runner integration via --backend local-flux in stub mode
"""

from __future__ import annotations

from pathlib import Path

import backend_local_flux  # type: ignore[import-not-found]
import runner  # type: ignore[import-not-found]
from prompt_matrix import MatrixAxes  # type: ignore[import-not-found]


def test_module_imports_cleanly():
    """Import-level smoke: surface API exists and matches fal symmetry."""
    assert hasattr(backend_local_flux, "generate")
    assert hasattr(backend_local_flux, "is_live_mode")
    assert backend_local_flux.LIVE_ENV_VAR == "PERSONA_REFGEN_LIVE"
    assert backend_local_flux.OFFLOAD_ENV_VAR == "PERSONA_REFGEN_OFFLOAD"
    assert backend_local_flux.DEFAULT_MODEL == "black-forest-labs/FLUX.1-dev"


def test_pick_offload_strategy_env_override(monkeypatch):
    monkeypatch.setenv("PERSONA_REFGEN_OFFLOAD", "sequential")
    assert backend_local_flux._pick_offload_strategy() == "sequential"
    monkeypatch.setenv("PERSONA_REFGEN_OFFLOAD", "model")
    assert backend_local_flux._pick_offload_strategy() == "model"
    monkeypatch.setenv("PERSONA_REFGEN_OFFLOAD", "none")
    assert backend_local_flux._pick_offload_strategy() == "none"


def test_pick_offload_strategy_unknown_value_falls_through(monkeypatch):
    """Unknown env value should be ignored (probe path), not crash."""
    monkeypatch.setenv("PERSONA_REFGEN_OFFLOAD", "garbage")
    # We don't assert which branch wins (depends on local CUDA state) — only
    # that it returns one of the valid strategy strings.
    assert backend_local_flux._pick_offload_strategy() in {"model", "sequential"}


def test_aspect_to_dims_known_ratios():
    # "9:16" maps to (1024, 1536) for backward compat with pre-existing
    # batches; technically that's 2:3, but reproducibility > labelling.
    assert backend_local_flux.aspect_to_dims("9:16") == (1024, 1536)
    assert backend_local_flux.aspect_to_dims("9:16-strict") == (864, 1536)
    assert backend_local_flux.aspect_to_dims("16:9") == (1536, 1024)
    assert backend_local_flux.aspect_to_dims("1:1") == (1024, 1024)
    # Extreme vertical for framing-bias escape probes.
    assert backend_local_flux.aspect_to_dims("1:2") == (1024, 2048)
    # Unknown ratios fall through to the 9:16 default rather than raising —
    # keeps the runner backend-agnostic for arbitrary aspect strings.
    assert backend_local_flux.aspect_to_dims("garbage") == (1024, 1536)


def test_generate_stub_writes_png_and_result_shape(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    out = tmp_path / "out.png"
    result = backend_local_flux.generate(
        prompt_text="full body portrait, photoreal",
        negative_prompt="",
        seed=1234,
        out_path=out,
        model=backend_local_flux.DEFAULT_MODEL,
        aspect_ratio="9:16",
        reference_image_url=None,
    )

    # PNG signature — confirms _write_stub_png was reused from backend_fal.
    assert out.exists()
    head = out.read_bytes()[:8]
    assert head == b"\x89PNG\r\n\x1a\n"

    # FalResult shape mirrors backend_fal exactly so the runner can map
    # uniformly into Candidate.
    assert result.image_path == out
    assert result.backend == "stub"
    assert result.backend_request_id == "stub-1234"
    assert result.backend_source_url is None


def test_generate_stub_ignores_reference_image_url(tmp_path, monkeypatch):
    """Phase 0 has no identity locking — `reference_image_url` must be a
    no-op so the runner can pass it through unchanged."""
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    out_a = tmp_path / "a.png"
    out_b = tmp_path / "b.png"
    backend_local_flux.generate(
        prompt_text="x", negative_prompt="", seed=99,
        out_path=out_a, reference_image_url=None,
    )
    backend_local_flux.generate(
        prompt_text="x", negative_prompt="", seed=99,
        out_path=out_b, reference_image_url="stub://anchor/aurora",
    )
    # Same seed -> same bytes regardless of reference_image_url.
    assert out_a.read_bytes() == out_b.read_bytes()


def _isolate_repo_root(tmp_path: Path, monkeypatch) -> Path:
    fake_root = tmp_path / "repo"
    persona_dir = fake_root / "personas" / "aurora"
    persona_dir.mkdir(parents=True)
    (persona_dir / "persona.yaml").write_text("id: aurora\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_REPO_ROOT", fake_root)
    return fake_root


def test_runner_dispatches_to_local_flux_in_stub(tmp_path, monkeypatch):
    """The runner's --backend flag picks the right adapter, and stub mode
    still writes a manifest + image. Confirms no live torch import path
    is taken (test would crash on a CPU-only CI box otherwise)."""
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    fake_root = _isolate_repo_root(tmp_path, monkeypatch)

    small = MatrixAxes(
        framings=("full-body shot, head to feet visible, standing, neutral pose",),
        lightings=("soft natural daylight from a north-facing window",),
        seeds=(101,),
    )
    manifest = runner.run_batch(
        persona_slug="aurora",
        batch_id="local-flux-smoke",
        axes=small,
        backend="local-flux",
        model=backend_local_flux.DEFAULT_MODEL,
        notes="local-flux smoke",
    )

    out_dir = (
        fake_root / "personas" / "aurora" / "_pipeline"
        / "step1_references" / "local-flux-smoke"
    )
    assert (out_dir / "manifest.json").exists()
    assert manifest.backend == "stub"  # gate-off label
    assert manifest.backend_model_id == backend_local_flux.DEFAULT_MODEL
    assert len(manifest.candidates) == 1
    assert manifest.candidates[0].backend == "stub"


def test_runner_auto_resolves_local_flux_model_when_default(tmp_path, monkeypatch):
    """When backend=local-flux is chosen and `model` is left at the
    function-default, `run_batch` must swap to the local-flux model id —
    otherwise FluxPipeline tries to load fal's repo id and fails."""
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    fake_root = _isolate_repo_root(tmp_path, monkeypatch)

    small = MatrixAxes(
        framings=("full-body shot, head to feet visible, standing, neutral pose",),
        lightings=("soft natural daylight from a north-facing window",),
        seeds=(101,),
    )
    # Note: NOT passing `model=` — this is the path the bug-fix targets.
    manifest = runner.run_batch(
        persona_slug="aurora",
        batch_id="auto-model-resolve",
        axes=small,
        backend="local-flux",
        notes="auto-model-resolve regression",
    )
    out_dir = (
        fake_root / "personas" / "aurora" / "_pipeline"
        / "step1_references" / "auto-model-resolve"
    )
    assert (out_dir / "manifest.json").exists()
    # The recorded model id must be the local-flux repo, NOT the fal fallback.
    assert manifest.backend_model_id == backend_local_flux.DEFAULT_MODEL


def test_runner_rejects_unknown_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    _isolate_repo_root(tmp_path, monkeypatch)
    small = MatrixAxes(
        framings=("full-body shot, head to feet visible, standing, neutral pose",),
        lightings=("soft natural daylight from a north-facing window",),
        seeds=(101,),
    )
    try:
        runner.run_batch(
            persona_slug="aurora",
            batch_id="bad-backend",
            axes=small,
            backend="does-not-exist",
        )
    except ValueError as exc:
        assert "does-not-exist" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown backend")
