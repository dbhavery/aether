"""Tests for dataset_summary — read-only corpus inspection."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import dataset_summary  # type: ignore[import-not-found]


def _make_anchors(repo_root: Path, persona_slug: str = "aurora") -> None:
    avatar_dir = repo_root / "personas" / persona_slug / "avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x01"))
    iend = chunk(b"IEND", b"")
    body = sig + ihdr + idat + iend
    for name in ("anchor.png", "portrait.png", "profile_left.png", "profile_right.png"):
        (avatar_dir / name).write_bytes(body)


def test_module_surface():
    assert hasattr(dataset_summary, "summarise")
    assert hasattr(dataset_summary, "main")


def test_summarise_anchor_only(tmp_path):
    _make_anchors(tmp_path)
    summary = dataset_summary.summarise(
        persona_slug="aurora",
        repo_root=tmp_path,
        relax_selftest_verdict=False,
        min_photoreal_score=6,
        include_anchor_set=True,
        batch_ids=None,
    )
    assert summary["persona_slug"] == "aurora"
    assert summary["instance_token"] == "aurora_nash"  # noqa: S105 — token, not password
    assert summary["num_images"] == 4
    assert summary["by_kind"] == {"anchor": 4}
    assert "<anchor>" in summary["by_batch"]


def test_summarise_skipping_anchors(tmp_path):
    _make_anchors(tmp_path)
    summary = dataset_summary.summarise(
        persona_slug="aurora",
        repo_root=tmp_path,
        relax_selftest_verdict=False,
        min_photoreal_score=6,
        include_anchor_set=False,
        batch_ids=None,
    )
    assert summary["num_images"] == 0
    assert summary["by_kind"] == {}


def test_main_cli_smoke(tmp_path, monkeypatch, capsys):
    """Invoke main() with a custom repo by monkeypatching __file__."""
    _make_anchors(tmp_path)
    # Patch repo_root resolution via dataset_summary.Path resolution.
    # Simpler: build a fake __file__ at tmp_path/tools/persona-lora-train/x.py
    # so parents[2] resolves to tmp_path.
    fake_tools = tmp_path / "tools" / "persona-lora-train"
    fake_tools.mkdir(parents=True)
    monkeypatch.setattr(dataset_summary, "__file__", str(fake_tools / "ds.py"))

    rc = dataset_summary.main([
        "--persona", "aurora",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "persona=aurora" in out
    assert "num_images=4" in out
    assert "anchor: 4" in out
    assert "WARNING" in out  # 4 < 8 triggers underfit warning


def test_main_strict_flag(tmp_path, monkeypatch, capsys):
    _make_anchors(tmp_path)
    fake_tools = tmp_path / "tools" / "persona-lora-train"
    fake_tools.mkdir(parents=True)
    monkeypatch.setattr(dataset_summary, "__file__", str(fake_tools / "ds.py"))

    rc = dataset_summary.main([
        "--persona", "aurora",
        "--strict",
    ])
    # Strict mode + anchors-only fixture should still work — anchors don't
    # pass through the selftest gate (no selftest row → fall through to
    # curation, anchors are unconditional).
    assert rc == 0
    out = capsys.readouterr().out
    assert "anchor: 4" in out
