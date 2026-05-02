"""Tests for auto_curate — selftest → curation translation."""

from __future__ import annotations

import datetime as _dt
import struct
import sys
import zlib
from pathlib import Path

import auto_curate  # type: ignore[import-not-found]

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


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _png_bytes() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    raw = b"\x00\x01"
    chunk = lambda tag, data: (  # noqa: E731 - test setup
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _make_batch(
    repo_root: Path,
    persona_slug: str,
    batch_id: str,
    candidates: list[str],
    *,
    selftest: dict[str, str] | None = None,
    curation: dict[str, str] | None = None,
) -> Path:
    """`candidates` is a list of prompt_ids, candidate_index 0 implied.
    `selftest`/`curation` are dict[prompt_id -> verdict]."""
    batch_dir = (
        repo_root / "personas" / persona_slug
        / "_pipeline" / "step1_references" / batch_id
    )
    images_dir = batch_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    prompts, cands = [], []
    body = _png_bytes()
    for i, pid in enumerate(candidates):
        prompts.append(
            PromptSpec(
                prompt_id=pid,
                persona_slug=persona_slug,
                framing="full-body",
                lighting="soft",
                seed=100 + i,
                prompt_text=f"{persona_slug}, full body",
            )
        )
        rel = f"images/{pid}__0.png"
        (batch_dir / rel).write_bytes(body)
        cands.append(
            Candidate(
                prompt_id=pid, candidate_index=0, image_path=rel,
                backend="stub", sha256="0" * 64,
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
        framings=["full-body"],
        lightings=["soft"],
        seeds=[100 + i for i in range(len(candidates))],
        prompts=prompts,
        candidates=cands,
        notes="auto-curate test",
    )
    write_manifest(manifest, batch_dir)

    if selftest:
        with (batch_dir / "selftest.jsonl").open("w", encoding="utf-8") as f:
            for pid, verdict in selftest.items():
                ps = 8 if verdict == "pass" else 4
                fr = "yes" if verdict == "pass" else "no"
                row = SelfTestRow(
                    prompt_id=pid,
                    candidate_index=0,
                    timestamp=_utc_now(),
                    photoreal_score=ps,
                    framing_match=fr,  # type: ignore[arg-type]
                    identity_match="yes",
                    verdict=verdict,  # type: ignore[arg-type]
                    notes="test",
                    backend="stub",
                )
                f.write(row.to_jsonl() + "\n")

    if curation:
        with (batch_dir / "curation.jsonl").open("w", encoding="utf-8") as f:
            for pid, verdict in curation.items():
                e = CurationEntry(
                    prompt_id=pid,
                    candidate_index=0,
                    verdict=verdict,  # type: ignore[arg-type]
                    timestamp=_utc_now(),
                )
                f.write(e.to_jsonl() + "\n")

    return batch_dir


def _read_curation(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = CurationEntry.from_jsonl(line)
        out[e.prompt_id] = e.verdict
    return out


def test_pass_selftest_becomes_keep(tmp_path):
    batch_dir = _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_a"],
        selftest={"p_a": "pass"},
    )
    counts = auto_curate.auto_curate_batch(
        "aurora", "b1", repo_root=tmp_path,
    )
    assert counts == {"kept": 1, "rejected": 0, "skipped_existing": 0, "skipped_no_selftest": 0}
    assert _read_curation(batch_dir / "curation.jsonl") == {"p_a": "keep"}


def test_flag_selftest_becomes_reject(tmp_path):
    batch_dir = _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_bad"],
        selftest={"p_bad": "flag"},
    )
    counts = auto_curate.auto_curate_batch(
        "aurora", "b1", repo_root=tmp_path,
    )
    assert counts["rejected"] == 1
    assert _read_curation(batch_dir / "curation.jsonl")["p_bad"] == "reject"


def test_no_selftest_row_skipped(tmp_path):
    batch_dir = _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_unscored"],
        # Note: no selftest row for p_unscored
    )
    counts = auto_curate.auto_curate_batch(
        "aurora", "b1", repo_root=tmp_path,
    )
    assert counts == {"kept": 0, "rejected": 0, "skipped_existing": 0, "skipped_no_selftest": 1}
    assert _read_curation(batch_dir / "curation.jsonl") == {}


def test_existing_curation_preserved_by_default(tmp_path):
    batch_dir = _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_a", "p_b"],
        selftest={"p_a": "pass", "p_b": "pass"},
        curation={"p_a": "reject"},  # Don manually rejected
    )
    counts = auto_curate.auto_curate_batch(
        "aurora", "b1", repo_root=tmp_path,
    )
    # p_a skipped (existing), p_b kept (auto)
    assert counts == {"kept": 1, "rejected": 0, "skipped_existing": 1, "skipped_no_selftest": 0}
    cur = _read_curation(batch_dir / "curation.jsonl")
    # latest-wins: p_a stays "reject" because no new row written.
    assert cur["p_a"] == "reject"
    assert cur["p_b"] == "keep"


def test_overwrite_existing_writes_anyway(tmp_path):
    batch_dir = _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_a"],
        selftest={"p_a": "pass"},
        curation={"p_a": "reject"},
    )
    counts = auto_curate.auto_curate_batch(
        "aurora", "b1", repo_root=tmp_path,
        overwrite_existing=True,
    )
    assert counts["kept"] == 1
    # latest-wins: the new auto-keep row beats the manual reject.
    assert _read_curation(batch_dir / "curation.jsonl")["p_a"] == "keep"


def test_idempotent(tmp_path):
    """Running auto_curate twice produces the same result without
    duplicating rows beyond what latest-wins handles."""
    _make_batch(
        tmp_path,
        "aurora",
        "b1",
        ["p_a"],
        selftest={"p_a": "pass"},
    )
    auto_curate.auto_curate_batch("aurora", "b1", repo_root=tmp_path)
    counts2 = auto_curate.auto_curate_batch("aurora", "b1", repo_root=tmp_path)
    # Second invocation: existing row from first invocation skips.
    assert counts2["skipped_existing"] == 1
    assert counts2["kept"] == 0


def test_missing_manifest_raises(tmp_path):
    """No manifest → FileNotFoundError, not silent success."""
    try:
        auto_curate.auto_curate_batch(
            "aurora", "missing-batch", repo_root=tmp_path,
        )
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
