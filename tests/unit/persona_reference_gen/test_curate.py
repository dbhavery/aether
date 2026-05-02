"""Tests for curate.py — focuses on the selftest-filter behavior added
during the bare-metal pivot (commit 8508efe).

Doesn't exercise the interactive prompt path. Uses --auto-keep +
--report-only paths to drive the main() function deterministically.
"""

from __future__ import annotations

import datetime as _dt
import struct
import sys
import zlib
from pathlib import Path

import curate  # type: ignore[import-not-found]

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
) -> Path:
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
        notes="curate test",
    )
    write_manifest(manifest, batch_dir)

    if selftest:
        with (batch_dir / "selftest.jsonl").open("w", encoding="utf-8") as f:
            for pid, verdict in selftest.items():
                row = SelfTestRow(
                    prompt_id=pid,
                    candidate_index=0,
                    timestamp=_utc_now(),
                    photoreal_score=8 if verdict == "pass" else 4,
                    framing_match="yes" if verdict == "pass" else "no",
                    identity_match="yes",
                    verdict=verdict,  # type: ignore[arg-type]
                    notes=f"test {verdict}",
                    backend="stub",
                )
                f.write(row.to_jsonl() + "\n")
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


def _isolate_repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(curate, "_REPO_ROOT", tmp_path)
    return tmp_path


def test_auto_keep_skips_flagged_by_default(tmp_path, monkeypatch):
    """Default behavior: candidates flagged by selftest are NOT
    auto-kept — they're skipped from the walk entirely."""
    fake_root = _isolate_repo(tmp_path, monkeypatch)
    batch_dir = _make_batch(
        fake_root,
        "aurora",
        "b1",
        ["p_pass", "p_flag"],
        selftest={"p_pass": "pass", "p_flag": "flag"},
    )
    rc = curate.main([
        "--persona", "aurora",
        "--batch", "b1",
        "--auto-keep",
    ])
    assert rc == 0
    cur = _read_curation(batch_dir / "curation.jsonl")
    assert cur == {"p_pass": "keep"}


def test_include_flagged_surfaces_them_for_auto_keep(tmp_path, monkeypatch):
    """With --include-flagged, flagged candidates are visible to the walk
    (and thus auto-kept under --auto-keep)."""
    fake_root = _isolate_repo(tmp_path, monkeypatch)
    batch_dir = _make_batch(
        fake_root,
        "aurora",
        "b1",
        ["p_pass", "p_flag"],
        selftest={"p_pass": "pass", "p_flag": "flag"},
    )
    rc = curate.main([
        "--persona", "aurora",
        "--batch", "b1",
        "--auto-keep",
        "--include-flagged",
    ])
    assert rc == 0
    cur = _read_curation(batch_dir / "curation.jsonl")
    assert cur == {"p_pass": "keep", "p_flag": "keep"}


def test_no_selftest_file_means_all_candidates_visible(tmp_path, monkeypatch):
    """Backwards compat: a batch without selftest.jsonl behaves exactly
    as before — every candidate is in the walk."""
    fake_root = _isolate_repo(tmp_path, monkeypatch)
    batch_dir = _make_batch(
        fake_root,
        "aurora",
        "b1",
        ["p_a", "p_b"],
        selftest=None,
    )
    rc = curate.main([
        "--persona", "aurora",
        "--batch", "b1",
        "--auto-keep",
    ])
    assert rc == 0
    cur = _read_curation(batch_dir / "curation.jsonl")
    assert cur == {"p_a": "keep", "p_b": "keep"}


def test_report_only_returns_zero_without_writing(tmp_path, monkeypatch):
    """--report-only emits a summary and writes nothing to curation.jsonl."""
    fake_root = _isolate_repo(tmp_path, monkeypatch)
    batch_dir = _make_batch(
        fake_root,
        "aurora",
        "b1",
        ["p_a"],
        selftest={"p_a": "pass"},
    )
    rc = curate.main([
        "--persona", "aurora",
        "--batch", "b1",
        "--report-only",
    ])
    assert rc == 0
    assert not (batch_dir / "curation.jsonl").exists()


def test_missing_manifest_returns_two(tmp_path, monkeypatch):
    """No manifest → exit code 2 (signaling operator error)."""
    _isolate_repo(tmp_path, monkeypatch)
    rc = curate.main([
        "--persona", "aurora",
        "--batch", "missing-batch",
        "--auto-keep",
    ])
    assert rc == 2


def test_existing_keep_not_re_walked(tmp_path, monkeypatch):
    """An existing non-pending verdict for a candidate is preserved —
    auto-keep doesn't re-touch it."""
    fake_root = _isolate_repo(tmp_path, monkeypatch)
    batch_dir = _make_batch(
        fake_root,
        "aurora",
        "b1",
        ["p_a", "p_b"],
        selftest={"p_a": "pass", "p_b": "pass"},
    )
    # Plant an existing reject for p_a.
    with (batch_dir / "curation.jsonl").open("w", encoding="utf-8") as f:
        e = CurationEntry(
            prompt_id="p_a", candidate_index=0, verdict="reject",
            timestamp=_utc_now(),
        )
        f.write(e.to_jsonl() + "\n")

    rc = curate.main([
        "--persona", "aurora",
        "--batch", "b1",
        "--auto-keep",
    ])
    assert rc == 0
    cur = _read_curation(batch_dir / "curation.jsonl")
    # p_a stays reject (existing wins because no new row written).
    assert cur["p_a"] == "reject"
    assert cur["p_b"] == "keep"
