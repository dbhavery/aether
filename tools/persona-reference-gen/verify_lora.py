"""Post-training LoRA verification driver.

Runs `backend_local_flux.generate` with a trained LoRA adapter applied
on top of `FLUX.1-dev`. Covers a small fixed prompt grid (anchor pose
× lighting × seed) so the operator can inspect identity preservation,
photoreal preservation, and pose generalization in one batch.

Designed to run in <30 min on a 3090 Ti at 1:2 aspect (4 prompts × 1
seed). Output is a self-contained directory with the same manifest +
selftest contract as Phase 0 batches, so all downstream curation /
analysis tools work unchanged.

Usage (live with trained adapter):

    PERSONA_REFGEN_LIVE=1 PERSONA_REFGEN_OFFLOAD=sequential \
      python tools/persona-reference-gen/verify_lora.py \
        --persona aurora \
        --lora build/lora-train/aurora-v1/output \
        --batch-id verify-aurora-v1 \
        [--aspect-ratio 1:2] [--seed 8888]

Stub mode (default — no `PERSONA_REFGEN_LIVE`) writes deterministic
placeholder PNGs so the CI harness exercises the orchestration code
without GPU.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import backend_local_flux  # noqa: E402

# Fixed verification prompts. Spec lock — every trained LoRA gets
# evaluated on the same surface so version-over-version comparisons
# are apples-to-apples. Aurora-tuned at v0; expand to per-persona
# packs once cast >1.
_AURORA_VERIFY_PROMPTS: tuple[dict, ...] = (
    {
        "id": "verify_neutral_smile",
        "framing": "full-body shot, head to feet visible, standing, neutral pose",
        "lighting": "soft natural daylight from a north-facing window",
        "prompt_text": (
            "{token}, photorealistic, full-body shot, head to feet visible, "
            "standing, neutral pose, cream sweater, dark slim jeans, "
            "soft natural daylight from a north-facing window, "
            "85mm lens, natural skin texture, no airbrushing"
        ),
    },
    {
        "id": "verify_hands_in_pockets",
        "framing": "standing, hands in pockets, calm expression",
        "lighting": "soft overcast daylight",
        "prompt_text": (
            "{token}, photorealistic, standing in a casual pose with hands "
            "in pockets, calm steady expression, cream sweater, dark slim "
            "jeans, soft overcast daylight, 85mm lens, natural skin texture"
        ),
    },
    {
        "id": "verify_seated_window",
        "framing": "seated by a window, hands clasped in lap",
        "lighting": "warm late-afternoon side light",
        "prompt_text": (
            "{token}, photorealistic, seated by a window with hands clasped "
            "in lap, cream sweater, dark slim jeans, warm late-afternoon "
            "side light, 85mm lens, natural skin texture, no airbrushing"
        ),
    },
    {
        "id": "verify_outdoor",
        "framing": "outdoor full body, walking on a city sidewalk",
        "lighting": "diffuse daylight, soft shadows",
        "prompt_text": (
            "{token}, photorealistic, full body outdoor portrait walking on "
            "a city sidewalk, cream sweater, dark slim jeans, diffuse "
            "daylight with soft shadows, 85mm lens, natural skin texture, "
            "no airbrushing"
        ),
    },
)
"""Verify-set is small (4) but covers the four scenarios where identity
LoRAs commonly break: (1) standard pose, (2) hand-articulation, (3)
seated frame, (4) outdoor (training corpus is interior-only)."""

_DEFAULT_NEGATIVE_PROMPT = (
    "headshot, bust crop, cartoon, anime, 3d render, plastic skin, "
    "magenta gradient background, deformed, extra fingers, low resolution"
)


@dataclass
class VerifyResult:
    persona_slug: str
    instance_token: str
    lora_path: str | None
    aspect_ratio: str
    out_dir: str
    candidates: list[dict]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_instance_token(persona_slug: str) -> str:
    # Avoid pulling in the lora-train module for one constant — keep a
    # private mirror that mirrors `dataset_builder.DEFAULT_INSTANCE_TOKEN_BY_PERSONA`.
    table = {"aurora": "aurora_nash"}
    return table.get(persona_slug, persona_slug)


def run_verify(
    *,
    persona_slug: str,
    lora_path: str | None,
    out_dir: Path,
    batch_id: str,
    aspect_ratio: str = "1:2",
    seed: int = 8888,
    instance_token: str | None = None,
) -> VerifyResult:
    """Run the verification grid and write a manifest-shaped output dir.

    Layout:

        <out_dir>/<batch_id>/
            manifest.json
            images/<prompt_id>__<seed>.png
            metadata.json

    The manifest is intentionally simpler than Phase 0's because verify
    runs are single-seed and do not feed downstream curation. Selftest
    happens via Claude-opus / Qwen2-VL after generation.
    """
    instance_token = instance_token or _resolve_instance_token(persona_slug)

    batch_dir = out_dir / batch_id
    images_dir = batch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[dict] = []
    for spec in _AURORA_VERIFY_PROMPTS:
        prompt_text = spec["prompt_text"].format(token=instance_token)
        out_png = images_dir / f"{spec['id']}__{seed}.png"
        result = backend_local_flux.generate(
            prompt_text=prompt_text,
            negative_prompt=_DEFAULT_NEGATIVE_PROMPT,
            seed=seed,
            out_path=out_png,
            model=backend_local_flux.DEFAULT_MODEL,
            aspect_ratio=aspect_ratio,
            lora_path=lora_path,
        )
        candidates.append(
            {
                "prompt_id": spec["id"],
                "framing": spec["framing"],
                "lighting": spec["lighting"],
                "prompt_text": prompt_text,
                "seed": seed,
                "image_path": f"images/{out_png.name}",
                "backend": result.backend,
                "sha256": _hash_file(out_png),
            }
        )

    manifest = {
        "schema_version": 1,
        "batch_id": batch_id,
        "persona_slug": persona_slug,
        "kind": "verify",
        "lora_path": lora_path,
        "instance_token": instance_token,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidates": candidates,
    }
    (batch_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return VerifyResult(
        persona_slug=persona_slug,
        instance_token=instance_token,
        lora_path=lora_path,
        aspect_ratio=aspect_ratio,
        out_dir=str(batch_dir.as_posix()),
        candidates=candidates,
    )


def run_compare(
    *,
    persona_slug: str,
    lora_path: str,
    out_dir: Path,
    batch_id: str,
    aspect_ratio: str = "1:2",
    seed: int = 8888,
    instance_token: str | None = None,
) -> tuple[VerifyResult, VerifyResult]:
    """A/B verify: run the prompt grid both WITH and WITHOUT the LoRA so
    Don can compare side-by-side. Same seed + prompt + aspect for an
    apples-to-apples diff. Outputs land at:

        <out_dir>/<batch_id>__base/    (LoRA-OFF control)
        <out_dir>/<batch_id>__lora/    (LoRA-ON treatment)

    Total wall clock: ~2x single-verify (no pipeline cache shared between
    the two — different cache keys due to lora_path).
    """
    base = run_verify(
        persona_slug=persona_slug,
        lora_path=None,
        out_dir=out_dir,
        batch_id=f"{batch_id}__base",
        aspect_ratio=aspect_ratio,
        seed=seed,
        instance_token=instance_token,
    )
    lora = run_verify(
        persona_slug=persona_slug,
        lora_path=lora_path,
        out_dir=out_dir,
        batch_id=f"{batch_id}__lora",
        aspect_ratio=aspect_ratio,
        seed=seed,
        instance_token=instance_token,
    )
    return (base, lora)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify-lora")
    parser.add_argument("--persona", required=True)
    parser.add_argument(
        "--lora",
        default=None,
        help=(
            "Path to LoRA adapter dir or .safetensors file. If omitted, "
            "runs the verify grid against base FLUX-dev (control)."
        ),
    )
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output dir; defaults to "
            "personas/<slug>/_pipeline/step3_lora_verify/"
        ),
    )
    parser.add_argument("--aspect-ratio", default="1:2")
    parser.add_argument("--seed", type=int, default=8888)
    parser.add_argument("--instance-token", default=None)
    parser.add_argument(
        "--compare",
        action="store_true",
        help=(
            "A/B run: emit both base-only and LoRA-applied outputs at "
            "<batch_id>__base / <batch_id>__lora. Requires --lora."
        ),
    )
    args = parser.parse_args(argv)

    if args.out_dir is None:
        repo_root = Path(__file__).resolve().parents[2]
        args.out_dir = (
            repo_root / "personas" / args.persona / "_pipeline" / "step3_lora_verify"
        )

    if args.compare:
        if not args.lora:
            print("[verify] --compare requires --lora (need a LoRA to compare against base)")
            return 2
        base, lora = run_compare(
            persona_slug=args.persona,
            lora_path=args.lora,
            out_dir=args.out_dir,
            batch_id=args.batch_id,
            aspect_ratio=args.aspect_ratio,
            seed=args.seed,
            instance_token=args.instance_token,
        )
        mode = "LIVE" if backend_local_flux.is_live_mode() else "STUB"
        print(f"[verify-compare] {mode} persona={base.persona_slug}")
        print(f"[verify-compare] base_dir={base.out_dir}")
        print(f"[verify-compare] lora_dir={lora.out_dir}")
        print(f"[verify-compare] candidates_per_arm={len(base.candidates)}")
        return 0

    result = run_verify(
        persona_slug=args.persona,
        lora_path=args.lora,
        out_dir=args.out_dir,
        batch_id=args.batch_id,
        aspect_ratio=args.aspect_ratio,
        seed=args.seed,
        instance_token=args.instance_token,
    )

    mode = "LIVE" if backend_local_flux.is_live_mode() else "STUB"
    print(f"[verify] {mode} persona={result.persona_slug}")
    print(f"[verify] lora={result.lora_path or '(base model only)'}")
    print(f"[verify] out_dir={result.out_dir}")
    print(f"[verify] candidates={len(result.candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
