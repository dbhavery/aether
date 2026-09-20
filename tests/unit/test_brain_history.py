"""The brain's history fetch must actually reach the store.

`_get_recent_history` calls `src.memory.store.get_recent_turns` and wraps it in
a broad `except Exception` that logs a warning and returns `[]`. That is the
right behaviour for a store that is down, but it also swallows a programming
error in the call itself.

It did. The call read `get_recent_turns(n_turns=n)` while the function is
`get_recent_turns(limit=20)`, so every call raised TypeError, every turn was
logged as a degraded fetch, and the brain ran with no conversation history from
the day the line was written. `CONTEXT_TURNS = 20` never did anything.

These tests pin the call to the real signature. The first would have caught the
defect; the second states why the ordinary tests did not.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.asyncio
async def test_history_fetch_returns_what_the_store_returns(monkeypatch):
    """A wrong keyword shows up here as an empty list, not an exception."""
    from src.memory import store

    turns = [
        {"role": "user", "content": "what did I just ask", "timestamp": 1.0},
        {"role": "assistant", "content": "you asked about the brakes", "timestamp": 2.0},
    ]
    seen: dict[str, object] = {}

    # Same signature as the real function. Binding is what does the work: a
    # call with an unexpected keyword raises TypeError here exactly as it does
    # against the real store.
    async def fake_get_recent_turns(limit: int = 20) -> list[dict]:
        seen["limit"] = limit
        return turns

    monkeypatch.setattr(store, "get_recent_turns", fake_get_recent_turns)

    from src.brain.handler import CONTEXT_TURNS, _get_recent_history

    got = await _get_recent_history(CONTEXT_TURNS)

    assert got == turns, (
        "the brain got no history. The store was healthy and returned two "
        "turns, so an empty list here means the call itself failed and was "
        "swallowed by the except in _get_recent_history."
    )
    assert seen["limit"] == CONTEXT_TURNS, (
        f"CONTEXT_TURNS is {CONTEXT_TURNS} but the store was asked for "
        f"{seen.get('limit')!r}"
    )


def test_the_store_still_takes_limit_and_not_n_turns():
    """Pin the store's parameter name, which is what the handler depends on.

    This does NOT catch the original defect, and saying otherwise would make it
    the kind of check this repo has been removing. Reverting the handler to
    `n_turns=n` leaves this test green, because it reads the store's signature
    rather than the handler's call. Only the first test above goes red.

    What it does buy: if someone renames `limit` on the store, the handler's
    call breaks and this names the cause immediately instead of leaving another
    silent degraded fetch.
    """
    from src.memory.store import get_recent_turns

    sig = inspect.signature(get_recent_turns)
    sig.bind(limit=20)  # the call the handler makes

    with pytest.raises(TypeError):
        sig.bind(n_turns=20)  # the call it used to make


@pytest.mark.asyncio
async def test_a_broken_store_still_degrades_instead_of_raising(monkeypatch):
    """The control.

    The except is not the bug and must stay. Without this, tightening the call
    could be "fixed" by removing the error handling, and a real store outage
    would take the whole turn down.
    """
    from src.memory import store

    async def exploding_get_recent_turns(limit: int = 20) -> list[dict]:
        raise RuntimeError("chroma is down")

    monkeypatch.setattr(store, "get_recent_turns", exploding_get_recent_turns)

    from src.brain.handler import _get_recent_history

    assert await _get_recent_history(20) == []
