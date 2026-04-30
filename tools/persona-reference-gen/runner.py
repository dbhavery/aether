"""Batch orchestration for the persona reference-image generator.

Reads a persona's anchor + axes config, expands the prompt matrix
deterministically, calls the backend per prompt, writes images +
manifest.json into the canonical output dir:

    personas/<slug>/_pipeline/step1_references/<batch_id>/
        manifest.json
        images/<prompt_id>__<idx>.png
        curation.jsonl   (created by curate.py, not here)

Doctrine §5 is enforced via prompt_matrix.validate_framings.
Doctrine §8 (visual self-test) is currently a TODO — see README.

Reproducibility: invoking the runner twice with the same persona, axes,
backend model, and aspect_ratio produces identical prompt sets and
identical fal.ai request payloads (seed is on the prompt; model+ar are
pinned in the manifest).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import sys
from pathlib import Path

# Allow `python tools/persona-reference-gen/runner.py` style invocation
# without polluting sys.path globally — add this dir only.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from backend_fal import (  # noqa: E402  — sys.path mutation above is intentional
    DEFAULT_ASPECT,
    DEFAULT_MODEL,
    LIVE_ENV_VAR,
    generate as backend_generate,
    is_live_mode,
)
from output_schema import (  # noqa: E402
    SCHEMA_VERSION,
    BatchManifest,
    Candidate,
    write_manifest,
)
from prompt_matrix import (  # noqa: E402
    MatrixAxes,
    expand_matrix,
    lookup_anchor,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _persona_yaml_sha256(slug: str) -> str | None:
    path = _REPO_ROOT / "personas" / slug / "persona.yaml"
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_dir(slug: str, batch_id: str) -> Path:
    return _REPO_ROOT / "personas" / slug / "_pipeline" / "step1_references" / batch_id


def _file_sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_batch(
    persona_slug: str,
    batch_id: str,
    *,
    axes: MatrixAxes | None = None,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT,
    num_images_per_prompt: int = 1,
    notes: str = "",
) -> BatchManifest:
    """Run one batch end-to-end. Writes images + manifest.json. Returns the
    manifest for the caller (CLI prints a summary)."""
    axes = axes or MatrixAxes.default()
    anchor = lookup_anchor(persona_slug)
    prompts = expand_matrix(persona_slug, anchor, axes)

    out_dir = _output_dir(persona_slug, batch_id)
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[Candidate] = []
    for spec in prompts:
        for idx in range(num_images_per_prompt):
            img_name = f"{spec.prompt_id}__{idx}.png"
            img_path = images_dir / img_name
            result = backend_generate(
                prompt_text=spec.prompt_text,
                negative_prompt=spec.negative_prompt,
                seed=spec.seed + idx,  # deterministic per-image variation
                out_path=img_path,
                model=model,
                aspect_ratio=aspect_ratio,
            )
            candidates.append(
                Candidate(
                    prompt_id=spec.prompt_id,
                    candidate_index=idx,
                    image_path=str(img_path.relative_to(out_dir).as_posix()),
                    backend=result.backend,
                    backend_request_id=result.backend_request_id,
                    backend_source_url=result.backend_source_url,
                    sha256=_file_sha256(img_path),
                )
            )

    manifest = BatchManifest(
        schema_version=SCHEMA_VERSION,
        batch_id=batch_id,
        persona_slug=persona_slug,
        created_at=_utc_now(),
        backend=("fal.ai" if is_live_mode() else "stub"),
        backend_model_id=model,
        aspect_ratio=aspect_ratio,
        num_images_per_prompt=num_images_per_prompt,
        framings=list(axes.framings),
        lightings=list(axes.lightings),
        seeds=list(axes.seeds),
        prompts=prompts,
        candidates=candidates,
        persona_yaml_sha256=_persona_yaml_sha256(persona_slug),
        notes=notes,
    )

    write_manifest(manifest, out_dir)
    return manifest


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="persona-reference-gen",
        description=(
            "Generate a batch of full-body photoreal reference images for a "
            "persona. Implements ADR-0014 Step 1 / ADR-0015. "
            "Default backend is a deterministic stub; set "
            f"{LIVE_ENV_VAR}=1 to call fal.ai live."
        ),
    )
    parser.add_argument("--persona", required=True, help="persona slug, e.g. aurora")
    parser.add_argument(
        "--batch",
        required=True,
        help="batch id, e.g. 2026-05-18a — used as output dir name",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--aspect-ratio", default=DEFAULT_ASPECT)
    parser.add_argument(
        "--num-images-per-prompt",
        type=int,
        default=1,
        help="candidates per prompt; >1 is useful when seed-variation is wanted",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="freeform note recorded in manifest (e.g. 'Aurora kickoff per gpu_queue.md')",
    )
    args = parser.parse_args(argv)

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        model=args.model,
        aspect_ratio=args.aspect_ratio,
        num_images_per_prompt=args.num_images_per_prompt,
        notes=args.notes,
    )
    out_dir = _output_dir(args.persona, args.batch)
    mode = "LIVE fal.ai" if is_live_mode() else "STUB (set PERSONA_REFGEN_LIVE=1 for live)"
    print(
        f"[{args.persona}] batch {args.batch}: {len(manifest.prompts)} prompts, "
        f"{len(manifest.candidates)} candidates, mode={mode}"
    )
    print(f"  manifest: {out_dir / 'manifest.json'}")
    print(f"  images:   {out_dir / 'images'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
