"""Tests for pipeline_status — cross-persona walking + markdown render."""

from __future__ import annotations

import datetime as _dt
import struct
import sys
import zlib
from pathlib import Path

import pipeline_status  # type: ignore[import-not-found]

# Schema modules sit in the same tool dir.
_TOOL_DIR = Path(__file__).resolve().parents[3] / "tools" / "persona-reference-gen"
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))

from output_schema import (  # type: ignore[import-not-found]  # noqa: E402
    SCHEMA_VERSION,
    BatchManifest,
    Candidate,
    CurationEntry,
    PromptSpec,
    SelfTestRow,
    write_manifest,
)


def _png_bytes() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    raw = b"\x00\x01"
    chunk = lambda tag, data: (  # noqa: E731 - short helper
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _make_batch(
    repo_root: Path,
    persona_slug: str,
    batch_id: str,
    candidates: list[tuple[str, str]],
    *,
    curation: dict[tuple[str, int], str] | None = None,
    selftest: dict[tuple[str, int], tuple[int, str, str, str]] | None = None,
    backend: str = "stub",
    model: str = "stub",
) -> Path:
    batch_dir = (
        repo_root / "personas" / persona_slug
        / "_pipeline" / "step1_references" / batch_id
    )
    images_dir = batch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    prompts = []
    cands = []
    body = _png_bytes()
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
        (batch_dir / rel).write_bytes(body)
        cands.append(
            Candidate(
                prompt_id=prompt_id,
                candidate_index=0,
                image_path=rel,
                backend=backend,
                sha256="0" * 64,
            )
        )
    manifest = BatchManifest(
        schema_version=SCHEMA_VERSION,
        batch_id=batch_id,
        persona_slug=persona_slug,
        created_at=_utc_now(),
        backend=backend,
        backend_model_id=model,
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
            for (pid, ci), v in curation.items():
                e = CurationEntry(
                    prompt_id=pid,
                    candidate_index=ci,
                    verdict=v,
                    timestamp=_utc_now(),
                )
                f.write(e.to_jsonl() + "\n")

    if selftest:
        with (batch_dir / "selftest.jsonl").open("w", encoding="utf-8") as f:
            for (pid, ci), (ps, fr, idn, vd) in selftest.items():
                row = SelfTestRow(
                    prompt_id=pid,
                    candidate_index=ci,
                    timestamp=_utc_now(),
                    photoreal_score=ps,
                    framing_match=fr,  # type: ignore[arg-type]
                    identity_match=idn,  # type: ignore[arg-type]
                    verdict=vd,  # type: ignore[arg-type]
                    notes="test",
                    backend="stub",
                )
                f.write(row.to_jsonl() + "\n")
    return batch_dir


def _make_anchor(repo_root: Path, persona_slug: str) -> None:
    avatar = repo_root / "personas" / persona_slug / "avatar"
    avatar.mkdir(parents=True, exist_ok=True)
    (avatar / "anchor.png").write_bytes(_png_bytes())


def test_collect_empty(tmp_path):
    reports = pipeline_status.collect(repo_root=tmp_path)
    assert reports == []


def test_collect_persona_with_no_batches(tmp_path):
    _make_anchor(tmp_path, "aurora")
    reports = pipeline_status.collect(repo_root=tmp_path)
    assert len(reports) == 1
    r = reports[0]
    assert r["persona_slug"] == "aurora"
    assert r["anchor_present"] is True
    assert r["lora_present"] is False
    assert r["batches"] == []


def test_collect_one_batch_with_curation_and_selftest(tmp_path):
    _make_anchor(tmp_path, "aurora")
    _make_batch(
        tmp_path,
        "aurora",
        "b1",
        [("p_a", "full-body, neutral"), ("p_b", "full-body, walking")],
        curation={("p_a", 0): "keep", ("p_b", 0): "reject"},
        selftest={
            ("p_a", 0): (8, "yes", "yes", "pass"),
            ("p_b", 0): (4, "no", "no", "flag"),
        },
        backend="local-flux",
        model="black-forest-labs/FLUX.1-dev",
    )

    reports = pipeline_status.collect(repo_root=tmp_path)
    assert len(reports) == 1
    batches = reports[0]["batches"]
    assert len(batches) == 1
    b = batches[0]
    assert b["batch_id"] == "b1"
    assert b["backend"] == "local-flux"
    assert b["model"] == "black-forest-labs/FLUX.1-dev"
    assert b["candidates"] == 2
    assert b["verdict_counts"] == {"keep": 1, "reject": 1}
    assert b["selftest_counts"] == {"pass": 1, "flag": 1}


def test_collect_handles_missing_manifest(tmp_path):
    """A batch dir that exists but has no manifest.json should report
    `manifest_present: False` rather than crash. Mirrors the
    in-progress GPU-run case where the dir exists but the manifest
    hasn't been written yet."""
    _make_anchor(tmp_path, "aurora")
    batch_dir = tmp_path / "personas" / "aurora" / "_pipeline" / "step1_references" / "in-flight"
    batch_dir.mkdir(parents=True)

    reports = pipeline_status.collect(repo_root=tmp_path)
    batches = reports[0]["batches"]
    assert len(batches) == 1
    assert batches[0]["manifest_present"] is False


def test_skips_underscore_dirs(tmp_path):
    """`personas/_culled/` and similar housekeeping dirs are skipped
    so the report only walks real persona slugs."""
    (tmp_path / "personas" / "_culled").mkdir(parents=True)
    _make_anchor(tmp_path, "aurora")
    reports = pipeline_status.collect(repo_root=tmp_path)
    slugs = {r["persona_slug"] for r in reports}
    assert "_culled" not in slugs
    assert "aurora" in slugs


def test_lora_detected_when_safetensors_present(tmp_path):
    _make_anchor(tmp_path, "aurora")
    lora_dir = tmp_path / "personas" / "aurora" / "loras"
    lora_dir.mkdir(parents=True)
    (lora_dir / "aurora_v1.safetensors").write_bytes(b"fake-weights")

    reports = pipeline_status.collect(repo_root=tmp_path)
    assert reports[0]["lora_present"] is True


def test_render_markdown_shape(tmp_path):
    _make_anchor(tmp_path, "aurora")
    _make_batch(
        tmp_path,
        "aurora",
        "b1",
        [("p_a", "full-body, neutral")],
        curation={("p_a", 0): "keep"},
    )
    md = pipeline_status.render_markdown(pipeline_status.collect(repo_root=tmp_path))
    assert "# Persona Pipeline Status" in md
    assert "## aurora" in md
    assert "| batch | backend | candidates" in md
    assert "b1" in md
