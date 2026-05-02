"""Build a flat LoRA training dataset from curated persona reference batches.

Phase 3 prep of the bare-metal local inference pivot
(file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-05-01_NIGHT_BARE_METAL_PIVOT.md).
Pulls images that survive Don's curation walk + the Doctrine §8 self-test
gate from `personas/<slug>/_pipeline/step1_references/<batch_id>/` into a
single flat directory in the layout that `diffusers/train_dreambooth_lora_flux.py`
(or kohya) consumes:

    <out_dir>/
        00.png
        00.txt
        01.png
        01.txt
        ...
        metadata.json

Each `<n>.txt` is the caption pinned to the matching `<n>.png`. The
caption template includes the persona's instance token (e.g.
`aurora_nash`) so the trained LoRA learns to bind that token to the
identity. Optionally folds in framing/lighting strings from the
manifest so the LoRA learns variation rather than a single pose/light.

Filtering rules (locked):

  - Require `curation.jsonl` verdict == "keep".
  - Require `selftest.jsonl` row (if present) verdict == "pass" AND
    photoreal_score ≥ `min_photoreal_score`.
  - Optionally include the persona's `avatar/anchor.png` + the three
    `profile_*.png` / `portrait.png` siblings; these are the v0 anchors
    Don already trusts.

GPU-free. Pure data-shaping. No model loading. Tests under
`tests/unit/persona_lora_train/` cover the full filter matrix.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Tool-dir sibling — same `sys.path` mutation pattern as the test
# harness. `output_schema` lives in `tools/persona-reference-gen/`.
_THIS_DIR = Path(__file__).resolve().parent
_REFGEN_DIR = _THIS_DIR.parent / "persona-reference-gen"


def _load_refgen_modules():
    """Lazy-import the persona-reference-gen schema modules.

    Hyphen in `persona-reference-gen` blocks normal Python imports; we
    add the dir to `sys.path` on first call. Hidden behind a function so
    test fixtures that monkeypatch the path can take effect without
    racing module-level imports.
    """
    import sys

    if str(_REFGEN_DIR) not in sys.path:
        sys.path.insert(0, str(_REFGEN_DIR))
    from output_schema import (  # type: ignore[import-not-found]
        BatchManifest,
        CurationEntry,
        SelfTestRow,
        read_manifest,
    )

    return read_manifest, BatchManifest, CurationEntry, SelfTestRow


DEFAULT_INSTANCE_TOKEN_BY_PERSONA: dict[str, str] = {
    "aurora": "aurora_nash",
}
"""Per-persona instance token used in the LoRA training caption. Keyed
on slug. Aurora-only at v0; backfill as Phase 2 personas enter
training. Tokens are intentionally distinct from common English words
so they don't fight with FLUX's prior."""


@dataclass
class DatasetSource:
    """Provenance row — where one training image came from."""

    output_index: int
    """0-based index in the flat training dir (matches `<n>.png` filename)."""

    image_path: str
    """Path of the image as written into the training dir, relative to it."""

    caption: str
    """Caption text written to the matching `<n>.txt`."""

    source_kind: str
    """One of: `anchor` | `batch_candidate`."""

    # Anchor-source fields (one of these blocks populated based on source_kind).
    anchor_filename: str | None = None
    """For source_kind == 'anchor', the original anchor filename."""

    # Batch-candidate-source fields.
    batch_id: str | None = None
    prompt_id: str | None = None
    candidate_index: int | None = None
    photoreal_score: int | None = None
    framing: str | None = None
    lighting: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class DatasetReport:
    """Result of a dataset build. Written as `metadata.json` next to the
    flat image set so the training script + the next dev to look at this
    can trace every training image back to its source candidate."""

    persona_slug: str
    instance_token: str
    output_dir: str
    num_images: int
    sources: list[DatasetSource] = field(default_factory=list)

    def to_json(self) -> str:
        # asdict recurses into DatasetSource, so sources become list[dict]
        # automatically. Then strip None fields per-source so the
        # provenance metadata stays clean (anchor rows don't carry batch
        # fields, batch rows don't carry anchor fields).
        d = asdict(self)
        d["sources"] = [
            {k: v for k, v in src.items() if v is not None} for src in d["sources"]
        ]
        return json.dumps(d, indent=2, sort_keys=False)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_curation(batch_dir: Path):
    """Latest-wins parse of `curation.jsonl`. Returns dict[(prompt_id,
    candidate_index)] -> verdict string. Empty dict if file is absent."""
    _, _, CurationEntry, _ = _load_refgen_modules()
    curations: dict[tuple[str, int], str] = {}
    path = batch_dir / "curation.jsonl"
    if not path.exists():
        return curations
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = CurationEntry.from_jsonl(line)
        curations[(entry.prompt_id, entry.candidate_index)] = entry.verdict
    return curations


def _load_selftest(batch_dir: Path):
    """Latest-wins parse of `selftest.jsonl`. Returns dict keyed on
    (prompt_id, candidate_index) → SelfTestRow. Empty dict if absent."""
    _, _, _, SelfTestRow = _load_refgen_modules()
    rows: dict[tuple[str, int], object] = {}
    path = batch_dir / "selftest.jsonl"
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = SelfTestRow.from_jsonl(line)
        rows[(row.prompt_id, row.candidate_index)] = row
    return rows


def _compose_caption(
    *,
    instance_token: str,
    framing: str | None,
    lighting: str | None,
) -> str:
    """Compose a training caption.

    Pattern: `<instance_token>, photorealistic, <framing>, <lighting>`
    with optional axes elided when missing. The training script reads
    this verbatim — keep it short and concrete.
    """
    parts: list[str] = [instance_token, "photorealistic"]
    if framing:
        parts.append(framing)
    if lighting:
        parts.append(lighting)
    return ", ".join(parts)


def _compose_anchor_caption(instance_token: str, anchor_filename: str) -> str:
    """Caption for the v0 anchor images. Anchors are headshot/portrait
    crops — that's fine for LoRA training (the LoRA learns identity from
    crops too, even though full-body is the inference target). We label
    them appropriately so the LoRA doesn't generalise the framing wrong.
    """
    name = anchor_filename.lower()
    if "anchor" in name:
        framing_hint = "head and shoulders, neutral expression"
    elif "portrait" in name:
        framing_hint = "head and shoulders, soft natural light"
    elif "profile_left" in name:
        framing_hint = "profile portrait facing left, head and shoulders"
    elif "profile_right" in name:
        framing_hint = "profile portrait facing right, head and shoulders"
    else:
        framing_hint = "head and shoulders"
    return f"{instance_token}, photorealistic, {framing_hint}"


def build_dataset(
    persona_slug: str,
    output_dir: Path,
    *,
    repo_root: Path | None = None,
    batch_ids: list[str] | None = None,
    include_anchor_set: bool = True,
    instance_token: str | None = None,
    min_photoreal_score: int = 6,
    require_keep_verdict: bool = True,
    relax_selftest_verdict: bool = False,
) -> DatasetReport:
    """Build a flat LoRA training dataset for `persona_slug`.

    Args:
        persona_slug: e.g. "aurora".
        output_dir: target directory; created if missing. Wiped before
            writing if it already contains an old dataset (we rewrite
            cleanly; metadata-only state on disk is the contract).
        repo_root: repo root; defaults to inferred parent of this tool dir.
        batch_ids: filter to specific Step 1 batch ids. None = include
            every batch directory under
            `personas/<slug>/_pipeline/step1_references/`.
        include_anchor_set: if True, copy in the 4 v0 anchor images
            (`personas/<slug>/avatar/{anchor,portrait,profile_left,profile_right}.png`)
            with portrait-style captions.
        instance_token: override the default per-persona token.
        min_photoreal_score: drop any candidate whose selftest row
            scores below this. Candidates without a selftest row are
            included (no row = not yet evaluated, defer to curation).
        require_keep_verdict: if True (default), only candidates with
            a `keep` verdict in `curation.jsonl` are included.

    Returns:
        DatasetReport with a per-image provenance row for every output
        image. Also written to `<output_dir>/metadata.json`.
    """
    repo_root = repo_root or _THIS_DIR.parents[1]
    instance_token = instance_token or DEFAULT_INSTANCE_TOKEN_BY_PERSONA.get(
        persona_slug, persona_slug
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    # Clean any prior contents — the dataset is the build's full output.
    for child in output_dir.iterdir():
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)

    # Diffusers' DreamBooth script tries to load every file in
    # `instance_data_dir` as a PIL image and crashes on non-image files.
    # Put images and captions in separate sibling subdirs so:
    #   - <output_dir>/images/<n>.png  → diffusers --instance_data_dir
    #   - <output_dir>/captions/<n>.txt → kohya/manual training paths
    images_dir = output_dir / "images"
    captions_dir = output_dir / "captions"
    images_dir.mkdir(parents=True, exist_ok=True)
    captions_dir.mkdir(parents=True, exist_ok=True)

    sources: list[DatasetSource] = []
    next_idx = 0

    # 1. Anchor set (optional, unconditional inclusion).
    if include_anchor_set:
        avatar_dir = repo_root / "personas" / persona_slug / "avatar"
        for anchor_name in (
            "anchor.png",
            "portrait.png",
            "profile_left.png",
            "profile_right.png",
        ):
            src = avatar_dir / anchor_name
            if not src.exists():
                continue
            dst_name = f"{next_idx:02d}.png"
            dst = images_dir / dst_name
            shutil.copy2(src, dst)
            caption = _compose_anchor_caption(instance_token, anchor_name)
            (captions_dir / f"{next_idx:02d}.txt").write_text(caption, encoding="utf-8")
            sources.append(
                DatasetSource(
                    output_index=next_idx,
                    image_path=f"images/{dst_name}",
                    caption=caption,
                    source_kind="anchor",
                    anchor_filename=anchor_name,
                    sha256=_hash_file(src),
                )
            )
            next_idx += 1

    # 2. Curated batch candidates.
    read_manifest, _, _, _ = _load_refgen_modules()
    step1_root = repo_root / "personas" / persona_slug / "_pipeline" / "step1_references"
    if step1_root.exists():
        candidate_batches = sorted(p.name for p in step1_root.iterdir() if p.is_dir())
        if batch_ids is not None:
            candidate_batches = [b for b in candidate_batches if b in set(batch_ids)]

        for batch_id in candidate_batches:
            batch_dir = step1_root / batch_id
            manifest_path = batch_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = read_manifest(manifest_path)
            curation = _load_curation(batch_dir)
            selftest = _load_selftest(batch_dir)

            prompts_by_id = {p.prompt_id: p for p in manifest.prompts}

            for candidate in manifest.candidates:
                key = (candidate.prompt_id, candidate.candidate_index)

                if require_keep_verdict and curation.get(key) != "keep":
                    continue

                row = selftest.get(key)
                photoreal_score: int | None = None
                if row is not None:
                    # Strict mode (default): selftest 'flag' verdict drops
                    # the candidate. Relaxed mode: only photoreal_score is
                    # gated; framing/identity flags are tolerated. Used
                    # when the LoRA training set legitimately wants
                    # best-available even if Doctrine §8 strict framing
                    # failed (e.g. 1:2 aspect-ratio candidates with ~80%
                    # body coverage).
                    if not relax_selftest_verdict and row.verdict != "pass":
                        continue
                    if row.photoreal_score < min_photoreal_score:
                        continue
                    photoreal_score = row.photoreal_score

                src = batch_dir / candidate.image_path
                if not src.exists():
                    # Manifest references an image that's not on disk —
                    # treat as a soft-miss rather than crashing the
                    # build (allows partial / pre-curated batches).
                    continue

                spec = prompts_by_id.get(candidate.prompt_id)
                framing = spec.framing if spec else None
                lighting = spec.lighting if spec else None

                dst_name = f"{next_idx:02d}.png"
                dst = images_dir / dst_name
                shutil.copy2(src, dst)
                caption = _compose_caption(
                    instance_token=instance_token,
                    framing=framing,
                    lighting=lighting,
                )
                (captions_dir / f"{next_idx:02d}.txt").write_text(caption, encoding="utf-8")
                sources.append(
                    DatasetSource(
                        output_index=next_idx,
                        image_path=f"images/{dst_name}",
                        caption=caption,
                        source_kind="batch_candidate",
                        batch_id=batch_id,
                        prompt_id=candidate.prompt_id,
                        candidate_index=candidate.candidate_index,
                        photoreal_score=photoreal_score,
                        framing=framing,
                        lighting=lighting,
                        sha256=candidate.sha256,
                    )
                )
                next_idx += 1

                # Body-extension sibling: for `images/<prompt>__<idx>.png`,
                # check for `images/<prompt>__<idx>_extended.png` and
                # include it as a separate source if present. Lets
                # body_extension augmentation flow into the LoRA training
                # set without requiring a separate manifest entry.
                ext_path = src.with_name(src.stem + "_extended" + src.suffix)
                if ext_path.exists():
                    ext_dst_name = f"{next_idx:02d}.png"
                    ext_dst = images_dir / ext_dst_name
                    shutil.copy2(ext_path, ext_dst)
                    ext_caption = _compose_caption(
                        instance_token=instance_token,
                        framing="full body, head to feet visible, standing",
                        lighting=lighting,
                    )
                    (captions_dir / f"{next_idx:02d}.txt").write_text(
                        ext_caption, encoding="utf-8"
                    )
                    sources.append(
                        DatasetSource(
                            output_index=next_idx,
                            image_path=f"images/{ext_dst_name}",
                            caption=ext_caption,
                            source_kind="body_extended",
                            batch_id=batch_id,
                            prompt_id=candidate.prompt_id,
                            candidate_index=candidate.candidate_index,
                            sha256=_hash_file(ext_path),
                        )
                    )
                    next_idx += 1

    report = DatasetReport(
        persona_slug=persona_slug,
        instance_token=instance_token,
        output_dir=str(output_dir.as_posix()),
        num_images=next_idx,
        sources=sources,
    )
    (output_dir / "metadata.json").write_text(report.to_json(), encoding="utf-8")
    return report


__all__ = [
    "DEFAULT_INSTANCE_TOKEN_BY_PERSONA",
    "DatasetReport",
    "DatasetSource",
    "build_dataset",
]
