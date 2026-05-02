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
# Cache key is `(model, lora_path)` so swapping LoRAs reloads the pipeline
# rather than corrupting a cached pipeline with stale adapter weights.
_PIPELINE_CACHE: dict[tuple[str, str | None], object] = {}

LORA_ENV_VAR = "PERSONA_REFGEN_LORA"
"""Optional path to a trained LoRA adapter directory (with
`pytorch_lora_weights.safetensors`) or single .safetensors file. When
set, `_load_pipeline()` calls `pipe.load_lora_weights(path)` after
offload setup. Used to verify trained Aurora-class identity LoRAs at
inference."""


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


def _resolve_lora_path(lora_path: str | None) -> str | None:
    """Normalise a user-supplied LoRA reference.

    Accepts either a directory holding `pytorch_lora_weights.safetensors`
    (the diffusers training-script output layout), a directory holding a
    single `.safetensors` file, or a path directly to a `.safetensors`
    file. Returns the path that `pipe.load_lora_weights()` will accept,
    or `None` if `lora_path` is falsy.

    Returns `None` if the resolution fails — caller may fall back to
    base-model inference rather than crash. The CLI surface should warn
    the operator when this happens.
    """
    if not lora_path:
        return None
    candidate = Path(lora_path)
    if candidate.is_file() and candidate.suffix == ".safetensors":
        return str(candidate)
    if candidate.is_dir():
        # Diffusers DreamBooth-LoRA writes adapter as
        # pytorch_lora_weights.safetensors at the output dir top level.
        canonical = candidate / "pytorch_lora_weights.safetensors"
        if canonical.exists():
            return str(candidate)
        # Otherwise look for any single .safetensors file.
        safetensors = sorted(candidate.glob("*.safetensors"))
        if len(safetensors) == 1:
            return str(safetensors[0])
        # Diffusers `load_lora_weights(<dir>)` walks the dir itself, so
        # return the dir path even if we can't pinpoint the file. The
        # downstream call may still succeed.
        return str(candidate)
    return None


def _load_pipeline(model: str, lora_path: str | None = None):
    """Return a cached `FluxPipeline` for `model`, loading on first call.

    Pulled out into a helper so tests can monkeypatch this single seam if
    they ever want to exercise the live code path with a fake. Kept import
    of `torch` + `diffusers` lazy — the fal-only runner path must not pay
    a 5-second import tax.

    Offload strategy is chosen by `_pick_offload_strategy()` to keep the
    live path resilient when something else is already holding GPU memory
    (a common state on Don's workstation). On OOM during pipeline setup
    we transparently fall back to the next-tighter strategy.

    When `lora_path` is supplied and resolvable, calls
    `pipe.load_lora_weights(resolved)` after offload setup. Cache key
    includes `lora_path` so swapping adapters between calls reloads the
    pipeline rather than serving stale weights.
    """
    resolved_lora = _resolve_lora_path(lora_path)
    cache_key = (model, resolved_lora)
    if cache_key in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[cache_key]

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

    if resolved_lora is not None:
        # Diffusers' load_lora_weights handles the rank+target-modules
        # detection from the safetensors metadata. No need to specify
        # weight_name when the file follows the canonical layout.
        pipe.load_lora_weights(resolved_lora)

    _PIPELINE_CACHE[cache_key] = pipe
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
    lora_path: str | None = None,
) -> FalResult:
    """Generate one image. Live-FLUX or stub depending on env gate.

    `negative_prompt` is accepted for backend-symmetric calling but ignored
    in live mode — FLUX.1-dev does not expose a negative-prompt branch in
    the stock `FluxPipeline` schema. `reference_image_url` is similarly
    accepted-and-ignored (Phase 1 wires identity conditioning).

    `lora_path` (or the `PERSONA_REFGEN_LORA` env var) loads a trained
    LoRA adapter on top of the base FLUX-dev pipeline before inference.
    Used to verify trained identity LoRAs against the same prompt the
    base run used.
    """
    _ = negative_prompt
    _ = reference_image_url
    if not is_live_mode():
        return _generate_stub(seed=seed, out_path=out_path, model=model)
    effective_lora = lora_path or os.environ.get(LORA_ENV_VAR) or None
    return _generate_live(
        prompt_text=prompt_text,
        seed=seed,
        out_path=out_path,
        model=model,
        aspect_ratio=aspect_ratio,
        lora_path=effective_lora,
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
    lora_path: str | None = None,
) -> FalResult:
    """Live FLUX inference. Loads pipeline lazily, runs once, writes PNG."""
    import gc  # noqa: PLC0415 — lazy with the rest of the heavy imports
    import torch  # noqa: PLC0415

    pipe = _load_pipeline(model, lora_path=lora_path)
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

    backend_id = f"local-flux/{model}"
    if lora_path:
        backend_id = f"{backend_id}+lora:{Path(lora_path).name}"

    return FalResult(
        image_path=out_path,
        backend=backend_id,
        backend_request_id=f"local-{seed}",
        backend_source_url=None,
    )


__all__ = [
    "DEFAULT_ASPECT",
    "DEFAULT_MODEL",
    "LIVE_ENV_VAR",
    "LORA_ENV_VAR",
    "OFFLOAD_ENV_VAR",
    "FalResult",
    "aspect_to_dims",
    "generate",
    "is_live_mode",
]
