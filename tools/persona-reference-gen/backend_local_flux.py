"""Local FLUX.1-dev adapter for the reference-image batch runner.

Phase 0 of the bare-metal local inference pivot
(file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md).
Mirrors the surface of `backend_fal.py` so the runner can swap backends
via `--backend local-flux` without behavioural drift.

Live calls are gated behind the same `PERSONA_REFGEN_LIVE` env var the fal
backend uses — `False` returns a deterministic stub PNG so the default
`pytest` run stays free + offline + 0-VRAM. `True` loads
`black-forest-labs/FLUX.1-dev` via `diffusers.FluxPipeline`, runs inference
on the RTX 3090 Ti, and writes a real PNG.

Phase 0 has no identity locking. `reference_image_url` is accepted (so the
runner stays backend-agnostic) but ignored. Phase 1 will introduce a
sibling `IdentityConditioner` wrapping local PuLID weights.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Reuse the fal backend's stub PNG writer + env gate so the two backends
# behave identically in stub mode (same bytes for the same seed) and the
# runner doesn't have to special-case anything.
from backend_fal import (
    LIVE_ENV_VAR,
    _write_stub_png,
    is_live_mode,
)

DEFAULT_MODEL = "black-forest-labs/FLUX.1-dev"
"""Unquantized FLUX.1-dev. ~24GB VRAM with `enable_model_cpu_offload`.
If OOM, swap to `XLabs-AI/flux-dev-fp8` (cached locally) — same pipeline,
tighter footprint. The handoff calls out this fallback explicitly."""

DEFAULT_ASPECT = "9:16"
"""Vertical full-body framing per doctrine §5. Mapped to (1024, 1536)."""

# Inference defaults — mirrored from
# `.claude/worktrees/agent-a209cefbe70d0ee83/scripts/generate_showcase_scenes.py`
# which already runs FLUX.1-dev cleanly on Don's hardware.
_DEFAULT_STEPS = 28
_DEFAULT_GUIDANCE = 3.5

OFFLOAD_ENV_VAR = "PERSONA_REFGEN_OFFLOAD"
"""Override the offload strategy when GPU headroom is tight:

  - `model`      → `pipe.enable_model_cpu_offload()`     (~12 GB peak GPU)
  - `sequential` → `pipe.enable_sequential_cpu_offload()` (~3-4 GB peak GPU, slower)
  - `none`       → fully resident on GPU                  (~24 GB peak GPU)

If unset, the loader probes free VRAM via `torch.cuda.mem_get_info()` and
picks `model` when ≥14 GB free, `sequential` otherwise. The default keeps
inference fast on a clean 3090 Ti and reliable when something else is
already using VRAM."""

# Live-mode pipeline cache. Loading FLUX takes 30–60s + 24GB so we keep it
# resident across calls within a single batch run. The runner instantiates
# the backend once per process, so this dict is effectively process-local.
_PIPELINE_CACHE: dict[str, object] = {}


@dataclass
class FalResult:
    """Backend-agnostic generation result.

    Field name retained as `FalResult` (rather than e.g. `LocalFluxResult`)
    so the runner's `Candidate` mapping stays uniform across backends.
    `backend` is the discriminator string; readers should branch on that.
    """

    image_path: Path
    backend: str
    backend_request_id: str | None
    backend_source_url: str | None


def aspect_to_dims(aspect_ratio: str) -> tuple[int, int]:
    """Map an `H:V` aspect-ratio string to FLUX-compatible (width, height).

    FLUX.1-dev requires dims that are multiples of 16. The defaults here
    target ~1.5MP — high enough to read photoreal at full-body, low enough
    to fit on a 3090 Ti without offload thrash. Unrecognised ratios fall
    back to the 9:16 default rather than raising, so the runner can pass
    through fal-style strings without translation.
    """
    # Note: "9:16" maps to (1024, 1536) for backward compatibility with
    # batches generated before this table was extended. (1024, 1536) is
    # actually 2:3, but the original `prompt_matrix.DEFAULT_ASPECT="9:16"`
    # used it as the canonical vertical default, so existing batch
    # manifests carry "9:16" + 1024x1536 bytes. Reproducibility wins
    # over labelling correctness here. Use "9:16-strict" if you want
    # the actually-9:16 dims.
    table = {
        "9:16": (1024, 1536),
        "9:16-strict": (864, 1536),
        "16:9": (1536, 1024),
        "1:1": (1024, 1024),
        "3:4": (1024, 1360),
        "4:3": (1360, 1024),
        "2:3": (1024, 1536),
        "3:2": (1536, 1024),
        "1:2": (1024, 2048),     # extreme vertical — forces more body area
        "2:1": (2048, 1024),     # extreme horizontal
        "1:3": (768, 2304),      # ultra-vertical, untested
        "3:8": (768, 2048),      # 3:8 vertical, untested
    }
    return table.get(aspect_ratio, (1024, 1536))


def _pick_offload_strategy() -> str:
    """Choose `model` vs `sequential` vs `none` offload based on env + free VRAM.

    Order:
      1. Honour `PERSONA_REFGEN_OFFLOAD` if set to a known value.
      2. Probe `torch.cuda.mem_get_info()` and pick `model` when ≥14 GB
         free, `sequential` otherwise. 14 GB is the empirical threshold
         for FLUX.1-dev fp16 transformer peak under model-offload.
      3. Default to `model` if no CUDA device is available (test paths).
    """
    override = os.environ.get(OFFLOAD_ENV_VAR, "").strip().lower()
    if override in {"model", "sequential", "none"}:
        return override

    try:
        import torch  # noqa: PLC0415

        if not torch.cuda.is_available():
            return "model"
        free_bytes, _total = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024**3)
    except Exception:  # noqa: BLE001 — probe failures fall back conservatively
        return "sequential"

    return "model" if free_gb >= 14 else "sequential"


def _load_pipeline(model: str):
    """Return a cached `FluxPipeline` for `model`, loading on first call.

    Pulled out into a helper so tests can monkeypatch this single seam if
    they ever want to exercise the live code path with a fake. Kept import
    of `torch` + `diffusers` lazy — the fal-only runner path must not pay
    a 5-second import tax.

    Offload strategy is chosen by `_pick_offload_strategy()` to keep the
    live path resilient when something else is already holding GPU memory
    (a common state on Don's workstation). On OOM during pipeline setup
    we transparently fall back to the next-tighter strategy.
    """
    if model in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[model]

    import torch  # noqa: PLC0415 — lazy by design
    from diffusers import FluxPipeline  # noqa: PLC0415

    pipe = FluxPipeline.from_pretrained(model, torch_dtype=torch.float16)

    strategy = _pick_offload_strategy()
    try:
        if strategy == "none":
            pipe.to("cuda")
        elif strategy == "sequential":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.enable_model_cpu_offload()
    except torch.cuda.OutOfMemoryError:
        # Fall back to the strictest strategy — sequential offload runs
        # FLUX in <8 GB peak GPU. Slower but the only path when headroom
        # is gone.
        torch.cuda.empty_cache()
        pipe.enable_sequential_cpu_offload()

    _PIPELINE_CACHE[model] = pipe
    return pipe


def generate(
    *,
    prompt_text: str,
    negative_prompt: str,
    seed: int,
    out_path: Path,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT,
    reference_image_url: str | None = None,
) -> FalResult:
    """Generate one image. Live-FLUX or stub depending on env gate.

    `negative_prompt` is accepted for backend-symmetric calling but ignored
    in live mode — FLUX.1-dev does not expose a negative-prompt branch in
    the stock `FluxPipeline` schema. `reference_image_url` is similarly
    accepted-and-ignored (Phase 1 wires identity conditioning).
    """
    _ = negative_prompt
    _ = reference_image_url
    if not is_live_mode():
        return _generate_stub(seed=seed, out_path=out_path, model=model)
    return _generate_live(
        prompt_text=prompt_text,
        seed=seed,
        out_path=out_path,
        model=model,
        aspect_ratio=aspect_ratio,
    )


def _generate_stub(
    *,
    seed: int,
    out_path: Path,
    model: str,
) -> FalResult:
    _write_stub_png(out_path, seed=seed)
    return FalResult(
        image_path=out_path,
        backend="stub",
        backend_request_id=f"stub-{seed}",
        backend_source_url=None,
    )


def _generate_live(
    *,
    prompt_text: str,
    seed: int,
    out_path: Path,
    model: str,
    aspect_ratio: str,
) -> FalResult:
    """Live FLUX inference. Loads pipeline lazily, runs once, writes PNG."""
    import gc  # noqa: PLC0415 — lazy with the rest of the heavy imports
    import torch  # noqa: PLC0415

    pipe = _load_pipeline(model)
    width, height = aspect_to_dims(aspect_ratio)

    generator = torch.Generator(device="cuda").manual_seed(seed)
    image = pipe(
        prompt=prompt_text,
        num_inference_steps=_DEFAULT_STEPS,
        guidance_scale=_DEFAULT_GUIDANCE,
        width=width,
        height=height,
        generator=generator,
    ).images[0]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)

    # Free per-call scratch tensors. Pipeline weights stay resident in the
    # cache; only intermediates get reclaimed.
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return FalResult(
        image_path=out_path,
        backend=f"local-flux/{model}",
        backend_request_id=f"local-{seed}",
        backend_source_url=None,
    )


__all__ = [
    "DEFAULT_ASPECT",
    "DEFAULT_MODEL",
    "LIVE_ENV_VAR",
    "OFFLOAD_ENV_VAR",
    "FalResult",
    "aspect_to_dims",
    "generate",
    "is_live_mode",
]
