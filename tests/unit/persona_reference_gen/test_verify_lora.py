"""Tests for the verify_lora driver — orchestration in stub mode."""

from __future__ import annotations

import json

import verify_lora  # type: ignore[import-not-found]


def test_module_surface():
    assert hasattr(verify_lora, "run_verify")
    assert hasattr(verify_lora, "main")
    assert len(verify_lora._AURORA_VERIFY_PROMPTS) >= 4


def test_resolve_instance_token_known_persona():
    assert verify_lora._resolve_instance_token("aurora") == "aurora_nash"


def test_resolve_instance_token_unknown_persona_returns_slug():
    assert verify_lora._resolve_instance_token("ghost") == "ghost"


def test_run_verify_writes_manifest_and_images_in_stub(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    verify_lora.run_verify(
        persona_slug="aurora",
        lora_path=None,
        out_dir=tmp_path,
        batch_id="verify-stub-1",
    )

    batch_dir = tmp_path / "verify-stub-1"
    assert (batch_dir / "manifest.json").exists()
    images = list((batch_dir / "images").glob("*.png"))
    assert len(images) == len(verify_lora._AURORA_VERIFY_PROMPTS)

    manifest = json.loads((batch_dir / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "verify"
    assert manifest["persona_slug"] == "aurora"
    assert manifest["instance_token"] == "aurora_nash"  # noqa: S105 — persona token, not a credential
    assert manifest["lora_path"] is None
    assert manifest["aspect_ratio"] == "1:2"
    assert len(manifest["candidates"]) == len(verify_lora._AURORA_VERIFY_PROMPTS)
    for cand in manifest["candidates"]:
        # Every candidate's prompt_text must have substituted the token —
        # if formatting failed we'd still see the literal `{token}`.
        assert "aurora_nash" in cand["prompt_text"]
        assert "{token}" not in cand["prompt_text"]
        assert cand["seed"] == 8888
        assert cand["image_path"].startswith("images/")
        assert len(cand["sha256"]) == 64
        # Stub backend tag uniform across all candidates.
        assert cand["backend"] == "stub"


def test_run_verify_with_lora_path_records_in_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    fake_lora = tmp_path / "fake_lora"
    fake_lora.mkdir()
    (fake_lora / "pytorch_lora_weights.safetensors").write_bytes(b"\x00" * 16)

    out_dir = tmp_path / "out"
    result = verify_lora.run_verify(
        persona_slug="aurora",
        lora_path=str(fake_lora),
        out_dir=out_dir,
        batch_id="verify-with-lora",
    )

    manifest = json.loads(
        (out_dir / "verify-with-lora" / "manifest.json").read_text()
    )
    assert manifest["lora_path"] == str(fake_lora)
    # In stub mode the LoRA isn't actually applied (no live FLUX), but
    # the path is recorded so Don can see what was nominally targeted.
    assert result.lora_path == str(fake_lora)


def test_run_verify_custom_seed_and_aspect(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    verify_lora.run_verify(
        persona_slug="aurora",
        lora_path=None,
        out_dir=tmp_path,
        batch_id="verify-custom",
        aspect_ratio="9:16",
        seed=12345,
    )

    manifest = json.loads(
        (tmp_path / "verify-custom" / "manifest.json").read_text()
    )
    assert manifest["seed"] == 12345
    assert manifest["aspect_ratio"] == "9:16"
    for cand in manifest["candidates"]:
        assert cand["seed"] == 12345
        # Filename matches `<id>__<seed>.png`.
        assert cand["image_path"].endswith(f"__{12345}.png")


def test_run_verify_unknown_persona_uses_slug_as_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    verify_lora.run_verify(
        persona_slug="zelda",
        lora_path=None,
        out_dir=tmp_path,
        batch_id="verify-zelda",
    )
    manifest = json.loads(
        (tmp_path / "verify-zelda" / "manifest.json").read_text()
    )
    fallback_token = "zelda"  # noqa: S105 — persona slug, not a credential
    assert manifest["instance_token"] == fallback_token
    for cand in manifest["candidates"]:
        assert fallback_token in cand["prompt_text"]


def test_main_cli_stub(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PERSONA_REFGEN_LIVE", raising=False)

    rc = verify_lora.main([
        "--persona", "aurora",
        "--batch-id", "cli-stub",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "STUB" in captured
    assert "(base model only)" in captured
    assert (tmp_path / "cli-stub" / "manifest.json").exists()
