"""Holding the Ollama model resident is opt-in, and off by default.

Measured 2026-09-20 against qwen3:14b at its full 40960 context. Three
identical back-to-back calls reported load 0.04 s, 0.00 s, 0.00 s and
generation of 99.1, 103.9 and 102.1 ms per token. A turn that arrives after
Ollama has evicted the model instead pays a load measured between 8.1 s and
16.5 s, and that load was being recorded as part of the completion.

Default stays off because this model takes 19 GB of a 24 GB card and pinning
it would take the GPU from every other job on this box.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.brain.llm_client import _apply_ollama_keep_alive


def test_nothing_is_sent_when_config_is_silent(monkeypatch):
    """The default must not pin the card."""
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(llm_router, "_read_llm_config", lambda: {})

    kwargs: dict[str, Any] = {}
    _apply_ollama_keep_alive(kwargs)
    assert "keep_alive" not in kwargs.get("extra_body", {})


@pytest.mark.parametrize("configured", ["15m", "1h", -1, 0])
def test_a_configured_value_is_passed_through(monkeypatch, configured):
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(
        llm_router, "_read_llm_config", lambda: {"ollama_keep_alive": configured}
    )

    kwargs: dict[str, Any] = {}
    _apply_ollama_keep_alive(kwargs)
    assert kwargs["extra_body"]["keep_alive"] == configured


@pytest.mark.parametrize("empty", [None, ""])
def test_an_empty_setting_is_treated_as_unset(monkeypatch, empty):
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(
        llm_router, "_read_llm_config", lambda: {"ollama_keep_alive": empty}
    )

    kwargs: dict[str, Any] = {}
    _apply_ollama_keep_alive(kwargs)
    assert "keep_alive" not in kwargs.get("extra_body", {})


def test_an_explicit_caller_value_is_not_overwritten(monkeypatch):
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(
        llm_router, "_read_llm_config", lambda: {"ollama_keep_alive": "15m"}
    )

    kwargs: dict[str, Any] = {"extra_body": {"keep_alive": "5m"}}
    _apply_ollama_keep_alive(kwargs)
    assert kwargs["extra_body"]["keep_alive"] == "5m"


def test_the_thinking_flag_survives(monkeypatch):
    """Both helpers write to extra_body; the second must not clobber the first."""
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(
        llm_router, "_read_llm_config", lambda: {"ollama_keep_alive": "15m"}
    )

    kwargs: dict[str, Any] = {"extra_body": {"think": False}}
    _apply_ollama_keep_alive(kwargs)
    assert kwargs["extra_body"]["think"] is False
    assert kwargs["extra_body"]["keep_alive"] == "15m"


def test_a_broken_config_sends_nothing(monkeypatch):
    """A config failure must not silently pin 19 GB of VRAM."""
    import src.brain.llm_router as llm_router

    def boom():
        raise RuntimeError("config file is unreadable")

    monkeypatch.setattr(llm_router, "_read_llm_config", boom)

    kwargs: dict[str, Any] = {}
    _apply_ollama_keep_alive(kwargs)
    assert "keep_alive" not in kwargs.get("extra_body", {})


def test_the_flag_is_only_applied_to_ollama():
    """`keep_alive` is an Ollama field. The call site has to stay in that branch.

    Without this, hard-coding the helper somewhere generic would pass every
    other test in this file.
    """
    import inspect

    from src.brain import llm_client

    src = inspect.getsource(llm_client.complete)
    marker = "_apply_ollama_keep_alive(call_kwargs)"
    assert marker in src
    before = src.split(marker)[0]
    assert 'if provider == "ollama":' in before.split("call_kwargs: dict")[-1], (
        "the keep_alive flag must stay inside the ollama branch"
    )
