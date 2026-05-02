"""Tests for body_extension — stub-path behaviour + canvas helpers."""

from __future__ import annotations

import importlib.util

import body_extension  # type: ignore[import-not-found]


def _has_pillow() -> bool:
    return importlib.util.find_spec("PIL") is not None


def test_module_surface():
    assert hasattr(body_extension, "extend_to_full_body")
    assert body_extension.DEFAULT_EXTEND_DOWN == 512
    assert body_extension.DEFAULT_EXTEND_TARGET_WIDTH == 1024
    assert body_extension.DEFAULT_MODEL == "black-forest-labs/FLUX.1-dev"


def test_prepare_canvas_pads_below(tmp_path):
    if not _has_pillow():
        return
    from PIL import Image

    src = tmp_path / "in.png"
    Image.new("RGB", (1024, 1536), color="red").save(src)

    canvas, mask = body_extension._prepare_canvas(
        src, extend_down=512, target_width=1024,
    )
    assert canvas.size == (1024, 2048)
    # Original area preserved (top of canvas).
    assert canvas.getpixel((0, 0)) == (255, 0, 0)
    # Padded area is gray.
    assert canvas.getpixel((0, 2000)) == (127, 127, 127)
    # Mask: 0 in original area, 255 in padded area.
    assert mask.getpixel((0, 0)) == 0
    assert mask.getpixel((0, 2000)) == 255


def test_prepare_canvas_resizes_to_target_width(tmp_path):
    if not _has_pillow():
        return
    from PIL import Image

    src = tmp_path / "in.png"
    # 512x768 input — half target width — should be scaled up to 1024x1536
    # before extension.
    Image.new("RGB", (512, 768), color="white").save(src)

    canvas, _mask = body_extension._prepare_canvas(
        src, extend_down=256, target_width=1024,
    )
    assert canvas.size == (1024, 1536 + 256)


def test_stub_extend_writes_padded_image(tmp_path, monkeypatch):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    src = tmp_path / "in.png"
    out = tmp_path / "out.png"
    Image.new("RGB", (1024, 1536), color="green").save(src)

    result = body_extension.extend_to_full_body(src, out)
    assert out.exists()
    assert result.backend == "stub"
    assert result.width == 1024
    assert result.height == 2048

    # Output image preserves the original RGB in the top region and pads
    # gray below — same shape as the live path's input would be.
    img = Image.open(out)
    assert img.size == (1024, 2048)
    assert img.getpixel((0, 0)) == (0, 128, 0)  # PIL "green"
    assert img.getpixel((0, 2000)) == (127, 127, 127)


def test_stub_main_cli(tmp_path, monkeypatch, capsys):
    if not _has_pillow():
        return
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)
    from PIL import Image

    src = tmp_path / "in.png"
    out = tmp_path / "out.png"
    Image.new("RGB", (1024, 1536), color="blue").save(src)

    rc = body_extension.main([
        "--input", str(src),
        "--output", str(out),
    ])
    assert rc == 0
    assert out.exists()
    captured = capsys.readouterr().out
    assert "STUB" in captured
    assert "1024x2048" in captured
