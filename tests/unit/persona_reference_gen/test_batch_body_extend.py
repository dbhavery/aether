"""Tests for batch_body_extend — sequential driver semantics."""

from __future__ import annotations

import importlib.util

import batch_body_extend  # type: ignore[import-not-found]


def _has_pillow() -> bool:
    return importlib.util.find_spec("PIL") is not None


def test_module_surface():
    assert hasattr(batch_body_extend, "main")


def test_stub_batch_extends_all_inputs(tmp_path, monkeypatch, capsys):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    inputs = []
    for i in range(3):
        path = tmp_path / f"in_{i}.png"
        Image.new("RGB", (1024, 1536), color=(50 + i * 10, 50, 50)).save(path)
        inputs.append(path)

    rc = batch_body_extend.main([
        "--inputs", *map(str, inputs),
        "--extend-down", "512",
    ])
    assert rc == 0

    for src in inputs:
        out = src.with_name(src.stem + "_extended.png")
        assert out.exists(), f"missing {out}"
        img = Image.open(out)
        assert img.size == (1024, 2048)

    err = capsys.readouterr().err
    assert "[batch] STUB mode, 3 input(s)" in err
    assert err.count("DONE") == 3
    assert "all done" in err


def test_skip_existing_short_circuits(tmp_path, monkeypatch, capsys):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    src = tmp_path / "already_done.png"
    Image.new("RGB", (1024, 1536), color="white").save(src)
    pre_existing = src.with_name(src.stem + "_extended.png")
    Image.new("RGB", (1024, 2048), color="black").save(pre_existing)
    pre_size_before = pre_existing.stat().st_size

    rc = batch_body_extend.main([
        "--inputs", str(src),
        "--skip-existing",
    ])
    assert rc == 0
    # Output untouched.
    assert pre_existing.stat().st_size == pre_size_before
    err = capsys.readouterr().err
    assert "SKIP (exists)" in err


def test_missing_input_logged_and_continues(tmp_path, monkeypatch, capsys):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    real = tmp_path / "real.png"
    Image.new("RGB", (1024, 1536), color="red").save(real)
    missing = tmp_path / "ghost.png"

    rc = batch_body_extend.main([
        "--inputs", str(missing), str(real),
    ])
    assert rc == 0

    real_extended = real.with_name(real.stem + "_extended.png")
    assert real_extended.exists()

    err = capsys.readouterr().err
    assert "MISSING" in err
    assert "ghost.png" in err


def test_seed_increments_per_image(tmp_path, monkeypatch, capsys):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    inputs = []
    for i in range(2):
        path = tmp_path / f"in_{i}.png"
        Image.new("RGB", (1024, 1536), color=(10, 10, 10)).save(path)
        inputs.append(path)

    rc = batch_body_extend.main([
        "--inputs", *map(str, inputs),
        "--seed-base", "1000",
    ])
    assert rc == 0
    err = capsys.readouterr().err
    # First image gets seed=1000 (base + 0), second gets seed=1001.
    assert "seed=1000" in err
    assert "seed=1001" in err
