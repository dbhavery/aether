# Known issues

Found while working on something else. Logged rather than fixed, per the repo
rule: report unrelated breakage, do not expand the current task into it.

---

## 2. The withdrawn 449 ms claim survives in a showcase design spec

**Found:** 2026-09-19, while removing the figure from `docs/DISTRIBUTION.md`.
**Where:** `docs/superpowers/specs/2026-03-24-anima-showcase-design.md` lines
158 and 202.
**Severity:** medium. It is outbound copy for a showcase page.

The 449 ms latency claim was removed from all four places it appeared in
`docs/DISTRIBUTION.md` on 2026-09-19 because no instrument had ever produced it
(see `docs/MEASURED-LATENCY.md`). Two more copies remain in the Anima showcase
design spec:

    line 158: *"449ms. Your voice never left this machine."*
    line 202: Stats with counter animations: 537+ tests. 22K+ lines. 14 modules. 28 tools. 449ms latency.

Line 202 also claims **537+ tests**. The real count on 2026-09-19 is 262
collected by pytest, so that figure needs checking too. Left alone here because
this task's scope named `docs/DISTRIBUTION.md` only.

---

## 1. The brain has never had conversation history: `get_recent_turns(n_turns=...)`

**Found:** 2026-09-19, while instrumenting the voice path.
**Where:** `src/brain/handler.py` `_get_recent_history`, line 34.
**Severity:** high. The assistant has no memory of the current conversation.

`src/brain/handler.py` calls:

    return await get_recent_turns(n_turns=n)

`src/memory/store.py` line 232 defines:

    async def get_recent_turns(limit: int = 20) -> list[dict]

There is no `n_turns` parameter, so the call raises
`TypeError: get_recent_turns() got an unexpected keyword argument 'n_turns'`
on every turn. It is caught by the surrounding handler and the turn proceeds
with an empty history list, so the LLM receives the system prompt and the
current user message only. `CONTEXT_TURNS = 20` has never had any effect.

Verified by binding the real signature:

    python -c "import inspect; from src.memory.store import get_recent_turns; \
      inspect.signature(get_recent_turns).bind(n_turns=20)"
    TypeError: got an unexpected keyword argument 'n_turns'

This is the same defect class as the `store_conversation_turn` missing
`timestamp` bug fixed on 2026-09-19 (see commit "[AETHER] Fix
store_conversation_turn call that raised TypeError on every turn"): a wrong
call signature into `src/memory/store.py` hidden by a broad `except` in the
brain handler. That fix raised this swallow from DEBUG to WARNING, so the
failure is now visible in the log at the shipped level instead of silent.

The sibling call on the next line, `search_memory(query, n_results=5)`, does
bind correctly and works.

**Fix is one keyword** (`n_turns=n` -> `limit=n`), but it needs a check on what
`get_recent_turns` returns versus what the LLM message list expects: the store
returns `{"role", "content", "timestamp"}` dicts and the handler passes them
straight into `messages`, so the extra `timestamp` key may need stripping
before litellm sees it. Not attempted here.
