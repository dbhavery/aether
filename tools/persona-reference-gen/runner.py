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
    MODEL_PULID,
    is_live_mode,
    upload_reference_image,
)
from backend_fal import (
    generate as fal_generate,
)
import backend_local_flux  # noqa: E402  — see sys.path mutation above

# Backend dispatch table — `--backend` keys map to the typed generator
# callable. fal stays the default for backwards compatibility; local-flux
# is the bare-metal Phase 0 path.
_BACKENDS = {
    "fal": fal_generate,
    "local-flux": backend_local_flux.generate,
}
_DEFAULT_BACKEND = "fal"
from output_schema import (  # noqa: E402
    SCHEMA_VERSION,
    BatchManifest,
    Candidate,
    SelfTestRow,
    write_manifest,
)
from prompt_matrix import (  # noqa: E402
    MatrixAxes,
    expand_matrix,
    lookup_anchor,
)
from selftest import (  # noqa: E402
    is_live_mode as selftest_is_live_mode,
)
from selftest import (
    score_candidate,
    write_selftest_jsonl,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _manifest_backend_label(backend: str) -> str:
    """Discriminator string written into the manifest's `backend` field.

    Distinguishes (a) which adapter was used and (b) live-vs-stub. Stub mode
    is shared across adapters so the label is just `stub`; live mode names
    the adapter so downstream tools can branch on cost/latency expectations.
    """
    if not is_live_mode():
        return "stub"
    if backend == "local-flux":
        return "local-flux"
    return "fal.ai"


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


def _persona_anchor_path(slug: str) -> Path:
    """Canonical local path to a persona's identity anchor image.

    `personas/<slug>/avatar/anchor.png` is the v0 anchor image produced
    by `scripts/persona_generator/generate_anchor_set.py`. PuLID
    consumes this path's URL after upload.
    """
    return _REPO_ROOT / "personas" / slug / "avatar" / "anchor.png"


def run_batch(
    persona_slug: str,
    batch_id: str,
    *,
    axes: MatrixAxes | None = None,
    model: str = DEFAULT_MODEL,
    aspect_ratio: str = DEFAULT_ASPECT,
    num_images_per_prompt: int = 1,
    notes: str = "",
    use_pulid: bool = False,
    reference_image_path: Path | None = None,
    run_selftest: bool = False,
    backend: str = _DEFAULT_BACKEND,
) -> BatchManifest:
    """Run one batch end-to-end. Writes images + manifest.json. Returns the
    manifest for the caller (CLI prints a summary).

    When `use_pulid` is True the model defaults to `fal-ai/flux-pulid`
    and the persona's anchor image (`personas/<slug>/avatar/anchor.png`,
    or `reference_image_path` override) is uploaded once and forwarded
    to every prompt — locking face/body identity. Doctrine §5
    full-body-framing is still enforced via the prompt-matrix axis;
    PuLID's identity lock is composed with the framing prompt, not a
    replacement for it.

    When `run_selftest` is True, a multimodal-vision pass scores every
    generated candidate against the anchor on photorealism / framing /
    identity per Doctrine §8 + ADR-0014, and writes
    `selftest.jsonl` next to `manifest.json`. The default curation walk
    can then hide flagged candidates.
    """
    axes = axes or MatrixAxes.default()
    anchor = lookup_anchor(persona_slug)
    prompts = expand_matrix(persona_slug, anchor, axes)

    out_dir = _output_dir(persona_slug, batch_id)
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # PuLID prep: switch the model default and upload the anchor exactly
    # once. The URL is reused across every prompt to keep identity stable
    # and to keep upload spend at O(1) per batch.
    reference_image_url: str | None = None
    anchor_path: Path | None = None
    if use_pulid:
        if model == DEFAULT_MODEL:
            # The caller didn't override the model; flip to PuLID.
            model = MODEL_PULID
        anchor_path = reference_image_path or _persona_anchor_path(persona_slug)
        if not anchor_path.exists():
            raise FileNotFoundError(
                f"--use-pulid requires an anchor image at {anchor_path} "
                "(override with --reference-image)."
            )
        if is_live_mode():
            reference_image_url = upload_reference_image(anchor_path)
        else:
            # Stub mode: skip the upload so the default `pytest` run stays
            # free + offline. The stub backend ignores reference_image_url
            # but still verifies the runner threads it correctly.
            reference_image_url = f"stub://anchor/{persona_slug}"

    try:
        backend_generate = _BACKENDS[backend]
    except KeyError as exc:
        raise ValueError(
            f"unknown backend {backend!r}; valid: {sorted(_BACKENDS)}"
        ) from exc

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
                reference_image_url=reference_image_url,
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
        backend=_manifest_backend_label(backend),
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

    if run_selftest:
        # Doctrine §8: multimodal-vision pass before Don sees anything.
        # Anchor source: PuLID uses the explicit anchor; non-PuLID falls
        # back to the same canonical anchor path (we still need an
        # identity reference for the identity_match axis).
        anchor_for_selftest = anchor_path or _persona_anchor_path(persona_slug)
        if not anchor_for_selftest.exists():
            raise FileNotFoundError(
                f"--selftest requires an anchor image at {anchor_for_selftest}."
            )
        rows: list[SelfTestRow] = []
        prompts_by_id = {p.prompt_id: p for p in prompts}
        for cand in candidates:
            spec = prompts_by_id[cand.prompt_id]
            cand_path = out_dir / cand.image_path
            row = score_candidate(
                cand_path,
                anchor_for_selftest,
                prompt_id=cand.prompt_id,
                candidate_index=cand.candidate_index,
                prompt_text=spec.prompt_text,
                persona_slug=persona_slug,
            )
            rows.append(row)
        write_selftest_jsonl(rows, out_dir)

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
    parser.add_argument(
        "--backend",
        choices=sorted(_BACKENDS),
        default=_DEFAULT_BACKEND,
        help=(
            "image generation backend. `fal` calls fal.ai (default, "
            "deprecated path). `local-flux` runs FLUX.1-dev on the local GPU "
            "per Phase 0 of the bare-metal pivot."
        ),
    )
    parser.add_argument("--model", default=None,
                        help="override default model id for the chosen backend.")
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
    parser.add_argument(
        "--use-pulid",
        action="store_true",
        help=(
            "use fal-ai/flux-pulid with the persona's anchor image as identity "
            "reference. Locks face/body identity across the batch. Default model "
            "flips to fal-ai/flux-pulid if --model wasn't explicitly set."
        ),
    )
    parser.add_argument(
        "--reference-image",
        default=None,
        help=(
            "override the anchor image path (default: "
            "personas/<slug>/avatar/anchor.png). Only used with --use-pulid "
            "or --selftest."
        ),
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help=(
            "run the Doctrine §8 multimodal-vision self-test pass on every "
            "candidate after generation. Writes selftest.jsonl. Live mode "
            "requires OPENAI_API_KEY + PERSONA_REFGEN_SELFTEST_LIVE=1; stub "
            "mode marks every candidate as pass."
        ),
    )
    args = parser.parse_args(argv)

    # Resolve per-backend default model when --model is not given.
    if args.model is None:
        if args.backend == "local-flux":
            model = backend_local_flux.DEFAULT_MODEL
        else:
            model = DEFAULT_MODEL
    else:
        model = args.model

    manifest = run_batch(
        persona_slug=args.persona,
        batch_id=args.batch,
        model=model,
        aspect_ratio=args.aspect_ratio,
        num_images_per_prompt=args.num_images_per_prompt,
        notes=args.notes,
        use_pulid=args.use_pulid,
        reference_image_path=Path(args.reference_image) if args.reference_image else None,
        run_selftest=args.selftest,
        backend=args.backend,
    )
    out_dir = _output_dir(args.persona, args.batch)
    if is_live_mode():
        mode = f"LIVE {args.backend}"
    else:
        mode = "STUB (set PERSONA_REFGEN_LIVE=1 for live)"
    selftest_mode = (
        "LIVE openai" if (args.selftest and selftest_is_live_mode())
        else ("STUB" if args.selftest else "off")
    )
    print(
        f"[{args.persona}] batch {args.batch}: {len(manifest.prompts)} prompts, "
        f"{len(manifest.candidates)} candidates, mode={mode}, "
        f"pulid={'on' if args.use_pulid else 'off'}, selftest={selftest_mode}"
    )
    print(f"  manifest: {out_dir / 'manifest.json'}")
    print(f"  images:   {out_dir / 'images'}")
    if args.selftest:
        print(f"  selftest: {out_dir / 'selftest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
