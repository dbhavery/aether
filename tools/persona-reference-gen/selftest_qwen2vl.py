"""Local Qwen2-VL multimodal-vision adapter for the Doctrine §8 self-test gate.

Phase 2 of the bare-metal local inference pivot
(file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md).
Replaces `selftest._live_score`'s OpenAI gpt-4o-mini path with a local
Qwen2-VL-Instruct call running on the 3090 Ti — no retail dependency.

Why Qwen2-VL-7B-Instruct: it's the strongest open-weights vision model
under 10B params at the categorical questions we ask (compare two images,
score photorealism, judge framing, judge identity). Florence-2 is great
at OCR/grounding but weaker at comparative aesthetic judgement;
InternVL2.5 is competitive but heavier on the tokenizer side. Qwen2-VL
is the safest starting point.

Live calls are gated behind `PERSONA_REFGEN_SELFTEST_LIVE` (shared with
selftest.py) so the default `pytest` run stays free + offline + 0-VRAM.
The pipeline is loaded lazily and cached process-locally — same pattern
as backend_local_flux.

Backend dispatch: callers reach this module via
`selftest.score_candidate(..., vlm_backend="qwen2vl")` once that flag is
wired. Until then, the openai path stays default; this module is the
opt-in path that proves out the local replacement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_MODEL = "Qwen/Qwen2-VL-7B-Instruct"
"""7B Instruct variant. ~16 GB fp16 / ~6 GB int4. Empirically the
sweet-spot at categorical visual comparison. Tighter VRAM environments
can swap to `Qwen/Qwen2-VL-2B-Instruct` (~4 GB fp16) at moderate
quality cost."""

LIVE_ENV_VAR = "PERSONA_REFGEN_SELFTEST_LIVE"
"""Same gate as selftest.py — whether or not the LIVE path actually
calls a model. Backend selection (openai vs qwen2vl) is a separate flag."""

QUANT_ENV_VAR = "PERSONA_REFGEN_SELFTEST_QUANT"
"""Override quantization: `none` (fp16) | `int4` (bitsandbytes 4-bit) |
`int8`. Default auto-picks based on free VRAM."""

# Process-local pipeline cache. Keyed on (model_id, quant_strategy) so
# swapping models or quant tiers within a run is supported.
_PIPELINE_CACHE: dict[tuple[str, str], object] = {}


_SYSTEM_PROMPT = (
    "You are an image-quality auditor for an AI image generation pipeline. "
    "You will be shown two images: an ANCHOR identity reference and a "
    "CANDIDATE. Score the CANDIDATE on three axes against the ANCHOR's "
    "identity. Be a tough but fair judge — AI defects (smooth skin, glassy "
    "eyes, six fingers, distorted hands, magenta gradient backgrounds, "
    "indigo digital halos, plastic texture) drop the score significantly. "
    "Reply with strict JSON only, no prose, no markdown fences."
)

_USER_PROMPT_TEMPLATE = (
    "Persona slug: {persona_slug}. Generation prompt asked for: "
    "{prompt_text}\n\nScore the CANDIDATE (second image) against the "
    "ANCHOR (first image). Reply as strict JSON with these exact keys:\n"
    "  photoreal_score: integer 0..10\n"
    '  framing_match: "yes" or "no"\n'
    '  identity_match: "yes" | "no" | "maybe"\n'
    "  notes: a short string explaining the strongest signal\n"
    "JSON only. No prose."
)


def is_live_mode() -> bool:
    val = os.environ.get(LIVE_ENV_VAR, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _pick_quant_strategy() -> str:
    """Pick fp16 vs int4 vs int8 based on env override + free VRAM.

    Order:
      1. `PERSONA_REFGEN_SELFTEST_QUANT` env override.
      2. Probe `torch.cuda.mem_get_info()` — ≥18 GB free → fp16,
         ≥10 GB free → int8, otherwise int4. Thresholds match Qwen2-VL-7B's
         empirical footprint with each quant tier plus headroom for KV
         cache during inference.
      3. Fall back to int4 if probe fails (safest / smallest).
    """
    override = os.environ.get(QUANT_ENV_VAR, "").strip().lower()
    if override in {"none", "fp16", "int4", "int8"}:
        return "none" if override == "fp16" else override

    try:
        import torch  # noqa: PLC0415

        if not torch.cuda.is_available():
            return "none"
        free_bytes, _total = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024**3)
    except Exception:  # noqa: BLE001
        return "int4"

    if free_gb >= 18:
        return "none"
    if free_gb >= 10:
        return "int8"
    return "int4"


def _load_pipeline(model: str, quant: str):
    """Load (or fetch from cache) the Qwen2-VL pipeline.

    Lazy imports keep stub-mode pytest fast. Cache key includes quant so
    swapping strategies within a session re-loads cleanly.
    """
    key = (model, quant)
    if key in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[key]

    import torch  # noqa: PLC0415
    from transformers import (  # noqa: PLC0415
        AutoProcessor,
        Qwen2VLForConditionalGeneration,
    )

    model_kwargs: dict[str, object] = {"torch_dtype": torch.float16}
    if quant == "int4":
        from transformers import BitsAndBytesConfig  # noqa: PLC0415

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
        )
    elif quant == "int8":
        from transformers import BitsAndBytesConfig  # noqa: PLC0415

        model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    else:
        # fp16 — let from_pretrained place on GPU directly.
        model_kwargs["device_map"] = "auto"

    mdl = Qwen2VLForConditionalGeneration.from_pretrained(model, **model_kwargs)
    if quant in {"int4", "int8"}:
        # bnb places the model itself; just ensure it's on cuda.
        try:
            mdl.to("cuda")
        except (ValueError, RuntimeError):
            # Some bnb configurations refuse a manual `.to("cuda")` —
            # the device_map handled placement already.
            pass

    processor = AutoProcessor.from_pretrained(model)
    bundle = {"model": mdl, "processor": processor}
    _PIPELINE_CACHE[key] = bundle
    return bundle


def _coerce_response(raw: str) -> tuple[int, str, str, str]:
    """Parse Qwen's JSON response with the same defensive shaping as
    selftest._live_score."""
    # Strip any leading/trailing prose Qwen may emit despite the prompt
    # asking for JSON-only. Find the outermost `{...}` and parse that.
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return 0, "no", "no", f"vlm returned non-JSON: {raw[:200]}"
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        return 0, "no", "no", f"vlm json parse error: {exc}"

    photoreal = int(parsed.get("photoreal_score", 0))
    photoreal = max(0, min(10, photoreal))
    framing = str(parsed.get("framing_match", "no")).strip().lower()
    if framing not in {"yes", "no"}:
        framing = "no"
    identity = str(parsed.get("identity_match", "no")).strip().lower()
    if identity not in {"yes", "no", "maybe"}:
        identity = "no"
    notes = str(parsed.get("notes", "")).strip()
    return photoreal, framing, identity, notes


def score(
    candidate_path: Path,
    anchor_path: Path,
    *,
    prompt_text: str,
    persona_slug: str,
    model: str = DEFAULT_MODEL,
) -> tuple[int, str, str, str]:
    """Live Qwen2-VL call. Lazy-loads the pipeline on first call.

    Returns (photoreal_score, framing_match, identity_match, notes) —
    same shape as `selftest._live_score` so the dispatcher in
    `selftest.score_candidate` can swap implementations transparently.
    """
    from PIL import Image  # noqa: PLC0415

    quant = _pick_quant_strategy()
    bundle = _load_pipeline(model, quant)
    mdl = bundle["model"]
    processor = bundle["processor"]

    anchor_img = Image.open(anchor_path).convert("RGB")
    candidate_img = Image.open(candidate_path).convert("RGB")

    user_text = _USER_PROMPT_TEMPLATE.format(
        persona_slug=persona_slug,
        prompt_text=prompt_text,
    )

    # Qwen2-VL chat template: list[dict] messages, content list with
    # {"type": "image"}/{"type": "text"} blocks. Two image entries =
    # ANCHOR first, then CANDIDATE — matches the OpenAI ordering so
    # prompt semantics are preserved.
    messages = [
        {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "image"},
                {"type": "text", "text": user_text},
            ],
        },
    ]
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(
        text=[text],
        images=[anchor_img, candidate_img],
        padding=True,
        return_tensors="pt",
    ).to("cuda")

    out_ids = mdl.generate(
        **inputs,
        max_new_tokens=256,
        do_sample=False,
    )
    # Trim the prompt prefix off the generated ids.
    trimmed = [o[len(i):] for i, o in zip(inputs.input_ids, out_ids, strict=False)]
    decoded = processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]

    return _coerce_response(decoded)


__all__ = [
    "DEFAULT_MODEL",
    "LIVE_ENV_VAR",
    "QUANT_ENV_VAR",
    "is_live_mode",
    "score",
]
