# Known issues

Found while working on something else. Logged rather than fixed, per the repo
rule: report unrelated breakage, do not expand the current task into it.

---

## 3. Five duplicate worktrees are still in `.claude/worktrees/`, holding uncommitted work

**Found:** 2026-09-19, during the worktree cleanup.
**Severity:** low, but it needs one decision from Don.

`.claude/worktrees/` held 8 full duplicate checkouts. Three were moved to
`_deprecated/2026-09-19/`. Five were left where they are because each contains
uncommitted changes, and moving a checkout that holds work nobody has reviewed
is not a cleanup:

| directory | branch | uncommitted |
|---|---|---|
| `agent-a209cefbe70d0ee83` | (unregistered, no `.git`) | 7 modified files under `planning/plans/` |
| `agent-a4096556bb2c2b011` | `worktree-agent-a4096556bb2c2b011` | `Cargo.lock`, +44/-1 |
| `agent-a8ad56458adecae0e` | `worktree-agent-a8ad56458adecae0e` | `Cargo.lock`, +42/-1 |
| `agent-aa59f354461670409` | `temp-rebase-12` | `Cargo.lock`, +44/-1 |
| `agent-afd56eb5f7c252eaa` | `worktree-agent-afd56eb5f7c252eaa` | `Cargo.lock`, +44/-1 |

The four `Cargo.lock` diffs look like `cargo build` regenerating a lockfile
(they add `tokio` and `tracing` to a dependency block) rather than authored
work, and three of the four are byte-identical to each other. The seven
`planning/plans/` files in `agent-a209cefbe70d0ee83` differ from its branch tip
and need a real look before anything moves.

Those five still hold 1,416 `def test_` lines and 1,525 `.py` files, so a
recursive count from the repo root still over-reports the test suite by roughly
six times. Run any count against `tests/` or with `.claude/worktrees/` excluded.

**Also needs Don's call:** the two registered worktrees that were moved
(`agent-a3a3b35474edfbe47`, `agent-aab31793adb46bd32`) are still listed by
`git worktree list` at their old paths, because moving a directory does not
update git's admin files and both are `locked`. Nothing is lost: both HEAD
commits (`c01fab6`, `8f54b81`) are still reachable through their branches, and
`git fsck` exits clean. To tidy the listing, Don would unlock and prune:

    git worktree unlock .claude/worktrees/agent-a3a3b35474edfbe47
    git worktree unlock .claude/worktrees/agent-aab31793adb46bd32
    git worktree prune

Not done here: `git worktree remove` and `prune` were outside what was
authorized for this pass.

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

Line 202 also claims **537+ tests**. The real count on 2026-09-19 is 237
collected by pytest from `tests/`, of which 44 were added that day, so the
figure before this work was 193. 537 is not reproducible from this repo. Left
alone here because this task's scope named `docs/DISTRIBUTION.md` only.

### 2026-09-20: annotated in place, and the severity was overstated

**Severity corrected to low.** `docs/superpowers/` is gitignored (`.gitignore:62`)
and the spec is untracked, so it is not in the repo and does not reach anyone
through it. It is a local working document. The risk is real but narrower than
"outbound copy": a future session reading it could build Act 4 straight from the
numbers.

All five Act 4 figures were measured and the file now carries a blocking notice
at the top plus an inline marker at each of the two sites. Nothing in the visual
direction was touched.

| Spec says | Measured 2026-09-20 | How |
|---|---|---|
| `449ms` | **84,337 ms** warm, 78,911 ms cold | `tools/trace-bench/measurements/2026-09-19-voice-path-rtx3090ti.jsonl` |
| `537+ tests` | **237** | `pytest --collect-only -q` |
| `22K+ lines` | **16,041** under `src/` | `find src -name '*.py' \| xargs wc -l` |
| `14 modules` | **13** top level packages under `src/` | directory count |
| `28 tools` | **not derivable** | `src/tools/` is untracked and empty of source; no tool registry exists anywhere in `src/`. A first grep for `@register_tool` returned 0, which was the grep being wrong, not an answer. |

**The annotation cannot be committed** and that is deliberate. `git add` refuses
the ignored path, and force adding it would change what this repo tracks, which
is not a call to make inside a docs fix. The notice lives on disk only.

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
