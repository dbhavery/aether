"""Unit tests for selftest_qwen2vl — local VLM adapter.

Live path (loads Qwen2-VL-7B, ~16 GB fp16) is NOT exercised here. We
test the parsing helper (deterministic, pure), the env-controlled quant
strategy picker, and module surface.
"""

from __future__ import annotations

import selftest_qwen2vl  # type: ignore[import-not-found]


def test_module_surface():
    assert selftest_qwen2vl.LIVE_ENV_VAR == "PERSONA_REFGEN_SELFTEST_LIVE"
    assert selftest_qwen2vl.QUANT_ENV_VAR == "PERSONA_REFGEN_SELFTEST_QUANT"
    assert selftest_qwen2vl.DEFAULT_MODEL == "Qwen/Qwen2-VL-7B-Instruct"
    assert hasattr(selftest_qwen2vl, "score")


def test_pick_quant_strategy_env_override(monkeypatch):
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_QUANT", "int4")
    assert selftest_qwen2vl._pick_quant_strategy() == "int4"
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_QUANT", "int8")
    assert selftest_qwen2vl._pick_quant_strategy() == "int8"
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_QUANT", "fp16")
    assert selftest_qwen2vl._pick_quant_strategy() == "none"
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_QUANT", "none")
    assert selftest_qwen2vl._pick_quant_strategy() == "none"


def test_pick_quant_strategy_unknown_value_falls_through(monkeypatch):
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_QUANT", "bogus")
    assert selftest_qwen2vl._pick_quant_strategy() in {"none", "int8", "int4"}


def test_coerce_response_clean_json():
    raw = (
        '{"photoreal_score": 8, "framing_match": "yes", '
        '"identity_match": "maybe", "notes": "auburn shifted to blonde"}'
    )
    photoreal, framing, identity, notes = selftest_qwen2vl._coerce_response(raw)
    assert photoreal == 8
    assert framing == "yes"
    assert identity == "maybe"
    assert "blonde" in notes


def test_coerce_response_with_prose_wrapper():
    """Qwen sometimes prepends prose despite the prompt — strip it."""
    raw = (
        "Here is my analysis:\n\n"
        '{"photoreal_score": 5, "framing_match": "no", '
        '"identity_match": "no", "notes": "bust crop only"}\n\n'
        "Hope this helps!"
    )
    photoreal, framing, identity, notes = selftest_qwen2vl._coerce_response(raw)
    assert photoreal == 5
    assert framing == "no"
    assert identity == "no"
    assert "bust" in notes


def test_coerce_response_clamps_out_of_range_score():
    raw = '{"photoreal_score": 99, "framing_match": "yes", "identity_match": "yes"}'
    photoreal, framing, identity, _ = selftest_qwen2vl._coerce_response(raw)
    assert photoreal == 10
    assert framing == "yes"
    assert identity == "yes"


def test_coerce_response_normalises_unknown_enums():
    raw = (
        '{"photoreal_score": 7, "framing_match": "kind of", '
        '"identity_match": "definitely not"}'
    )
    photoreal, framing, identity, _ = selftest_qwen2vl._coerce_response(raw)
    assert photoreal == 7
    # Unknown values fall through to the strict-no branch.
    assert framing == "no"
    assert identity == "no"


def test_coerce_response_handles_non_json():
    photoreal, framing, identity, notes = selftest_qwen2vl._coerce_response(
        "I cannot evaluate these images."
    )
    assert photoreal == 0
    assert framing == "no"
    assert identity == "no"
    assert "non-JSON" in notes


def test_open_and_resize_downscales_large_input(tmp_path):
    """1024x1536 input must come back at <= 768 long edge to keep the
    Qwen2-VL vision-token budget under control."""
    pytest_pillow = _maybe_skip_no_pillow()
    if pytest_pillow:
        return

    from PIL import Image

    src = tmp_path / "big.png"
    Image.new("RGB", (1024, 1536), color="white").save(src)

    out = selftest_qwen2vl._open_and_resize(src)
    assert max(out.size) == 768
    # Aspect ratio preserved.
    assert out.size[0] / out.size[1] == 1024 / 1536


def test_open_and_resize_passthrough_when_small(tmp_path):
    """Inputs already under the target are not upscaled."""
    pytest_pillow = _maybe_skip_no_pillow()
    if pytest_pillow:
        return
    from PIL import Image

    src = tmp_path / "small.png"
    Image.new("RGB", (256, 384), color="white").save(src)
    out = selftest_qwen2vl._open_and_resize(src)
    assert out.size == (256, 384)


def _maybe_skip_no_pillow() -> bool:
    """Returns True if PIL is unavailable so the caller can early-return.
    Pillow is a heavyweight dep; we don't want unit tests to hard-fail
    if a CI box hasn't installed it. PuLID-style image work always has
    PIL in scope, so this is mostly defensive."""
    import importlib.util

    return importlib.util.find_spec("PIL") is None


def test_selftest_dispatcher_routes_qwen2vl_when_env_set(monkeypatch):
    """When PERSONA_REFGEN_SELFTEST_BACKEND=qwen2vl, score_candidate must
    select the local backend even with no explicit arg.

    Asserted via the resolver helper rather than running a live call —
    actually invoking the dispatcher would require a candidate image
    and the live env var, both of which would trigger model loading.
    """
    import selftest  # type: ignore[import-not-found]

    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_BACKEND", "qwen2vl")
    assert selftest._resolved_backend(None) == "qwen2vl"
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_BACKEND", "openai")
    assert selftest._resolved_backend(None) == "openai"
    monkeypatch.delenv("PERSONA_REFGEN_SELFTEST_BACKEND", raising=False)
    assert selftest._resolved_backend(None) == "openai"
    # Explicit arg wins.
    monkeypatch.setenv("PERSONA_REFGEN_SELFTEST_BACKEND", "openai")
    assert selftest._resolved_backend("qwen2vl") == "qwen2vl"
