"""Ollama thinking is off by default on the voice path.

A reasoning model spends its tokens before it says anything, and the brain
speaks `message.content` and throws `message.thinking` away. The committed voice
trace recorded 2,475 completion tokens for 9.9 seconds of speech, with the first
content token arriving at 41,634 ms of a 42,322 ms stage.

Measured here 2026-09-20 against qwen3.5:4b, same prompt, warm model:

    thinking on    12.6 s to first content token
    thinking off    2.8 s

These tests pin the flag onto the request rather than the wall-clock number, so
they stay meaningful on a machine with no Ollama running.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.brain.llm_client import _apply_ollama_thinking


def test_thinking_is_disabled_by_default():
    kwargs: dict[str, Any] = {"model": "ollama/qwen3.5:4b"}
    _apply_ollama_thinking(kwargs)
    assert kwargs["extra_body"]["think"] is False


def test_an_explicit_caller_value_is_not_overwritten():
    kwargs: dict[str, Any] = {"extra_body": {"think": True}}
    _apply_ollama_thinking(kwargs)
    assert kwargs["extra_body"]["think"] is True


def test_other_extra_body_fields_survive():
    """A dict copy, not a replacement. Clobbering these would be a silent bug."""
    kwargs: dict[str, Any] = {"extra_body": {"keep_alive": "10m", "seed": 7}}
    _apply_ollama_thinking(kwargs)
    assert kwargs["extra_body"]["keep_alive"] == "10m"
    assert kwargs["extra_body"]["seed"] == 7
    assert kwargs["extra_body"]["think"] is False


def test_config_can_turn_thinking_back_on(monkeypatch):
    """The control.

    Without this, hard-coding ``think = False`` and ignoring config would pass
    every other test in this file. The escape hatch has to actually work, or the
    docstring promising it is the kind of claim this repo has been removing.
    """
    import src.brain.llm_router as llm_router

    monkeypatch.setattr(llm_router, "_read_llm_config", lambda: {"ollama_think": True})

    kwargs: dict[str, Any] = {}
    _apply_ollama_thinking(kwargs)
    assert "extra_body" not in kwargs or "think" not in kwargs.get("extra_body", {})


def test_a_broken_config_still_leaves_thinking_off(monkeypatch):
    """Config lookup failure must not re-enable the slow path."""
    import src.brain.llm_router as llm_router

    def boom():
        raise RuntimeError("config file is unreadable")

    monkeypatch.setattr(llm_router, "_read_llm_config", boom)

    kwargs: dict[str, Any] = {}
    _apply_ollama_thinking(kwargs)
    assert kwargs["extra_body"]["think"] is False


@pytest.mark.parametrize("provider", ["anthropic", "openai", "aether_guest"])
def test_the_flag_is_only_applied_to_ollama(provider):
    """`think` is an Ollama field. Sending it elsewhere could be rejected.

    `complete()` calls the helper inside `if provider == "ollama"`, so this
    asserts the call site rather than the helper.
    """
    import inspect

    from src.brain import llm_client

    src = inspect.getsource(llm_client.complete)
    marker = '_apply_ollama_thinking(call_kwargs)'
    assert marker in src
    before = src.split(marker)[0]
    assert 'if provider == "ollama":' in before.split("call_kwargs: dict")[-1], (
        "the thinking flag must stay inside the ollama branch"
    )
