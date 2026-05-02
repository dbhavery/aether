"""Filter-matrix tests for dataset_builder.build_dataset.

GPU-free. Builds a fake repo tree with manifests, curation rows, and
selftest rows, then asserts the dataset builder picks exactly the
right images for each filter combination.
"""

from __future__ import annotations

import datetime as _dt
import json
import struct
import sys
import zlib
from pathlib import Path

import dataset_builder  # type: ignore[import-not-found]

# Tests need access to the persona-reference-gen schema modules to
# write valid manifests/curation.jsonl. Reuse the same path-mutation
# the dataset_builder does internally.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFGEN_DIR = _REPO_ROOT / "tools" / "persona-reference-gen"
if str(_REFGEN_DIR) not in sys.path:
    sys.path.insert(0, str(_REFGEN_DIR))

from output_schema import (  # type: ignore[import-not-found]  # noqa: E402
    SCHEMA_VERSION,
    BatchManifest,
    Candidate,
    CurationEntry,
    PromptSpec,
    SelfTestRow,
    write_manifest,
)


def _write_png(path: Path, *, byte: int = 1) -> None:
    """Write a 1×1 grayscale PNG with `byte` as its pixel value.

    Mirrors backend_fal._write_stub_png so test images are valid PNGs
    a future PIL-based step can also open without crashing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sig = b"\x89PNG\r\n\x1a\n"
    raw = b"\x00" + bytes([byte])
    ihdr_chunk = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat_chunk = _png_chunk(b"IDAT", zlib.compress(raw))
    iend_chunk = _png_chunk(b"IEND", b"")
    path.write_bytes(sig + ihdr_chunk + idat_chunk + iend_chunk)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _make_batch(
    repo_root: Path,
    *,
    persona_slug: str = "aurora",
    batch_id: str,
    candidates: list[tuple[str, str]],
    curation: dict[tuple[str, int], str] | None = None,
    selftest: dict[tuple[str, int], tuple[int, str, str, str]] | None = None,
) -> Path:
    """Materialise a batch dir with manifest + images and optional
    curation/selftest jsonl files.

    `candidates` is a list of (prompt_id, framing) — one candidate per
    prompt, candidate_index 0. Lighting is fixed to a single string and
    seeds increment.
    """
    batch_dir = (
        repo_root / "personas" / persona_slug / "_pipeline" / "step1_references" / batch_id
    )
    images_dir = batch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    prompts = []
    cands = []
    for i, (prompt_id, framing) in enumerate(candidates):
        prompts.append(
            PromptSpec(
                prompt_id=prompt_id,
                persona_slug=persona_slug,
                framing=framing,
                lighting="soft natural daylight",
                seed=100 + i,
                prompt_text=f"{persona_slug}, {framing}",
            )
        )
        rel = f"images/{prompt_id}__0.png"
        _write_png(batch_dir / rel, byte=(i + 1) % 256)
        cands.append(
            Candidate(
                prompt_id=prompt_id,
                candidate_index=0,
                image_path=rel,
                backend="stub",
                sha256="0" * 64,
            )
        )
    manifest = BatchManifest(
        schema_version=SCHEMA_VERSION,
        batch_id=batch_id,
        persona_slug=persona_slug,
        created_at=_utc_now(),
        backend="stub",
        backend_model_id="stub",
        aspect_ratio="9:16",
        num_images_per_prompt=1,
        framings=[c[1] for c in candidates],
        lightings=["soft natural daylight"],
        seeds=[100 + i for i in range(len(candidates))],
        prompts=prompts,
        candidates=cands,
        notes="test batch",
    )
    write_manifest(manifest, batch_dir)

    if curation:
        with (batch_dir / "curation.jsonl").open("w", encoding="utf-8") as f:
            for (pid, ci), verdict in curation.items():
                entry = CurationEntry(
                    prompt_id=pid,
                    candidate_index=ci,
                    verdict=verdict,
                    timestamp=_utc_now(),
                )
                f.write(entry.to_jsonl() + "\n")

    if selftest:
        with (batch_dir / "selftest.jsonl").open("w", encoding="utf-8") as f:
            for (pid, ci), (ps, fr, idn, verdict) in selftest.items():
                row = SelfTestRow(
                    prompt_id=pid,
                    candidate_index=ci,
                    timestamp=_utc_now(),
                    photoreal_score=ps,
                    framing_match=fr,  # type: ignore[arg-type]
                    identity_match=idn,  # type: ignore[arg-type]
                    verdict=verdict,  # type: ignore[arg-type]
                    notes="test",
                    backend="stub",
                )
                f.write(row.to_jsonl() + "\n")

    return batch_dir


def _make_anchors(repo_root: Path, persona_slug: str = "aurora") -> None:
    """Materialise the 4 v0 anchor images."""
    avatar_dir = repo_root / "personas" / persona_slug / "avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    for name, byte in [
        ("anchor.png", 10),
        ("portrait.png", 20),
        ("profile_left.png", 30),
        ("profile_right.png", 40),
    ]:
        _write_png(avatar_dir / name, byte=byte)


def test_anchor_only_when_no_batches(tmp_path):
    """With no Step 1 batches but anchor flag on, dataset should
    contain exactly the 4 anchor images."""
    _make_anchors(tmp_path)

    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=True,
    )

    assert report.num_images == 4
    assert report.persona_slug == "aurora"
    assert report.instance_token == "aurora_nash"  # noqa: S105 — not a password

    # Layout: <out>/images/<n>.png + <out>/captions/<n>.txt + metadata.json
    assert (out / "metadata.json").exists()
    pngs = sorted(p for p in (out / "images").iterdir() if p.suffix == ".png")
    txts = sorted(p for p in (out / "captions").iterdir() if p.suffix == ".txt")
    assert len(pngs) == 4
    assert len(txts) == 4

    # Captions encode the framing hints.
    captions = [s.caption for s in report.sources]
    assert any("head and shoulders" in c for c in captions)
    assert any("profile" in c for c in captions)


def test_skips_anchors_when_flag_off(tmp_path):
    _make_anchors(tmp_path)
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert report.num_images == 0


def test_keep_only_filtering(tmp_path):
    """Curation gates: only `keep` verdicts land in the dataset."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, neutral"), ("p_b", "full-body shot, walking"), ("p_c", "full-body shot, seated")],
        curation={("p_a", 0): "keep", ("p_b", 0): "reject", ("p_c", 0): "pending"},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert report.num_images == 1
    src = report.sources[0]
    assert src.source_kind == "batch_candidate"
    assert src.prompt_id == "p_a"


def test_selftest_score_threshold(tmp_path):
    """Below-threshold photoreal scores get dropped even if curation says keep."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[
            ("p_high", "full-body shot, standing"),
            ("p_low", "full-body shot, sitting"),
        ],
        curation={("p_high", 0): "keep", ("p_low", 0): "keep"},
        selftest={
            ("p_high", 0): (8, "yes", "yes", "pass"),
            ("p_low", 0): (4, "yes", "yes", "pass"),  # photoreal below 6 default
        },
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
        min_photoreal_score=6,
    )
    assert report.num_images == 1
    assert report.sources[0].prompt_id == "p_high"
    assert report.sources[0].photoreal_score == 8


def test_relax_selftest_verdict_keeps_flagged_high_score(tmp_path):
    """`relax_selftest_verdict=True` lets a flagged candidate pass through
    if its photoreal_score is high enough. Use case: 1:2 aspect-ratio
    candidates that fail strict Doctrine §8 framing but are best-available
    for LoRA training."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_high_flagged", "full-body, neutral")],
        curation={("p_high_flagged", 0): "keep"},
        # Flag verdict from selftest, but high photoreal score
        selftest={("p_high_flagged", 0): (9, "no", "yes", "flag")},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
        relax_selftest_verdict=True,
        min_photoreal_score=6,
    )
    assert report.num_images == 1
    assert report.sources[0].photoreal_score == 9


def test_relax_selftest_still_drops_low_photoreal(tmp_path):
    """`relax_selftest_verdict` only relaxes the verdict gate, not the
    photoreal_score gate. Low-photoreal candidates still drop."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_low_flagged", "full-body, neutral")],
        curation={("p_low_flagged", 0): "keep"},
        selftest={("p_low_flagged", 0): (4, "no", "yes", "flag")},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
        relax_selftest_verdict=True,
        min_photoreal_score=6,
    )
    assert report.num_images == 0


def test_selftest_flag_verdict_drops_candidate(tmp_path):
    """A `flag` verdict drops the candidate even at high photoreal score."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, neutral")],
        curation={("p_a", 0): "keep"},
        selftest={("p_a", 0): (9, "no", "yes", "flag")},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert report.num_images == 0


def test_no_selftest_row_falls_through_to_curation(tmp_path):
    """When selftest.jsonl is missing or doesn't cover a candidate,
    only the curation gate applies. Documents the deferred-evaluation
    case (Phase 0 batches that haven't been scored yet)."""
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, neutral")],
        curation={("p_a", 0): "keep"},
        selftest=None,
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert report.num_images == 1


def test_batch_id_filter(tmp_path):
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, b1")],
        curation={("p_a", 0): "keep"},
    )
    _make_batch(
        tmp_path,
        batch_id="b2",
        candidates=[("p_b", "full-body shot, b2")],
        curation={("p_b", 0): "keep"},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
        batch_ids=["b2"],
    )
    assert report.num_images == 1
    assert report.sources[0].batch_id == "b2"


def test_caption_includes_framing_and_lighting(tmp_path):
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, walking")],
        curation={("p_a", 0): "keep"},
    )
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    cap = report.sources[0].caption
    assert "aurora_nash" in cap
    assert "photorealistic" in cap
    assert "walking" in cap
    assert "soft natural daylight" in cap


def test_metadata_json_round_trips(tmp_path):
    _make_anchors(tmp_path)
    _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body shot, neutral")],
        curation={("p_a", 0): "keep"},
    )
    out = tmp_path / "dataset"
    dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=True,
    )
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["persona_slug"] == "aurora"
    assert meta["instance_token"] == "aurora_nash"  # noqa: S105 — not a password
    assert meta["num_images"] == 5  # 4 anchors + 1 candidate
    assert len(meta["sources"]) == 5
    # No-source-kind None fields leaked into json.
    for src in meta["sources"]:
        assert "image_path" in src
        if src["source_kind"] == "anchor":
            assert "anchor_filename" in src
        else:
            assert "batch_id" in src


def test_rebuild_overwrites_prior_dataset(tmp_path):
    """Calling build_dataset twice must produce a clean state — the
    second call replaces the first call's output rather than appending."""
    _make_anchors(tmp_path)

    out = tmp_path / "dataset"
    out.mkdir()
    # Plant a stale file that should be wiped.
    (out / "stale.png").write_bytes(b"old")

    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=True,
    )
    assert not (out / "stale.png").exists()
    assert report.num_images == 4


def test_body_extended_sibling_picked_up(tmp_path):
    """A `<prompt>__<idx>_extended.png` next to a kept candidate becomes
    a separate dataset row with source_kind='body_extended'."""
    batch_dir = _make_batch(
        tmp_path,
        batch_id="b1",
        candidates=[("p_a", "full-body, hips visible")],
        curation={("p_a", 0): "keep"},
    )
    # Plant the body-extended sibling next to the original.
    orig = batch_dir / "images" / "p_a__0.png"
    ext = batch_dir / "images" / "p_a__0_extended.png"
    _write_png(ext, byte=99)

    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "aurora",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    # Original + extended = 2 rows from one curated candidate.
    assert report.num_images == 2
    kinds = sorted(s.source_kind for s in report.sources)
    assert kinds == ["batch_candidate", "body_extended"]
    extended = next(s for s in report.sources if s.source_kind == "body_extended")
    assert "full body" in extended.caption
    assert orig.exists()  # original still present in the batch dir
    assert ext.exists()


def test_per_persona_token_lookup(tmp_path):
    """Unknown personas fall back to the slug as the instance token."""
    out = tmp_path / "dataset"
    report = dataset_builder.build_dataset(
        "marcus_chen",
        out,
        repo_root=tmp_path,
        include_anchor_set=False,
    )
    assert report.instance_token == "marcus_chen"  # noqa: S105 — not a password
