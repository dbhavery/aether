# L2.1 Execution Report — Turn-Scoped Conversation Memory

**Date:** 2026-04-19
**Branch:** dev
**Status:** Complete, tests green, boundary lint clean, not pushed.

---

## 1. Goal

Close the immediate "amnesia gap" in the demo/runtime path: give Aether a small, bounded, turn-scoped working memory so recent user/assistant exchanges carry across turns. Narrow first slice only — no embeddings, no summarisation, no durable storage.

## 2. What shipped

### 2.1 `packages/l2-memory/src/session.rs` (new module)

Narrow API, deliberately disjoint from the Wave-4 `MemoryKernel` stub:

- `MemoryRole` — `User` / `Assistant` / `System`, with a stable `label()` for rendering.
- `TurnMemoryRecord { session_id, sequence, role, content, timestamp_ms }`.
- `RecentMemoryWindow { session_id, records: Vec<TurnMemoryRecord> }` (oldest-first).
- `RecentMemoryConfig { max_turns, max_chars }` + `default_narrow()` → 16 turns / 8 KiB.
- `SessionMemoryStore` trait:
  - `append(TurnMemoryRecord) -> Result<(), L2Error>` — assigns a monotonic per-session sequence, applies bounds immediately.
  - `recent(&str) -> Result<RecentMemoryWindow, L2Error>` — snapshot, empty for unknown sessions (not an error).
  - `clear_session(&str) -> Result<(), L2Error>` — no-op if unknown.
- `InMemorySessionMemoryStore` — `Mutex<HashMap<String, SessionState>>`, per-session `VecDeque` with front-eviction.
- `render_transcript(&RecentMemoryWindow) -> String` — deterministic `"Recent conversation:\n- User: …\n- Aether: …\n"` block; empty window returns `""`.

All new types re-exported from `aether_l2_memory` crate root so callers get a flat namespace.

### 2.2 Bounded-memory policy

Oldest-first eviction runs after every `append`:

1. Pop front while `records.len() > max_turns`.
2. Pop front while `total_chars > max_chars` and at least one record remains.

The `max_chars` guard preserves at least the most recent record even if it alone exceeds the cap — avoids losing the current turn's reply. `content.len()` is used (byte length), not UTF-8 scalar count — adequate for a narrow slice and cheaper.

### 2.3 Integration — `apps/l1-cli`

- New `Cargo.toml` dep: `aether-l2-memory` (apps crate is outside the boundary-lint allowlist, so this is permitted; `CLAUDE.md` §1.4).
- New `memory` module (`apps/l1-cli/src/memory.rs`) with:
  - `MemoryAwareRouter<R: TurnRouter>` — wraps an inner `TurnRouter`, holds `Arc<dyn SessionMemoryStore>` + `session_id`. On `dispatch` it loads the recent window, prepends `render_transcript(&w)` + `"User: <utterance>"` to the prompt, then forwards to the inner router. Never writes memory itself.
  - `build_prompt(&RecentMemoryWindow, &str) -> String` — pure helper exposed for tests and future reuse.
  - `summarise_turn_for_memory(&TurnResult) -> (MemoryRole, String)` — allow path uses the route response as assistant text; block paths produce a short system note so the next turn's transcript shows continuity across refusals.
  - `user_record` / `assistant_record` helpers for the main loop.
- `main.rs`:
  - Constructs a shared `Arc<dyn SessionMemoryStore>`.
  - Wraps the existing `ModelRouterAdapter` in `MemoryAwareRouter` inside `build_engine` (session = `"demo-session"`, the same constant already used for `SessionId`).
  - After each `engine.handle_turn`, appends `user_record` then `assistant_record` so the NEXT turn's dispatch sees the prior exchange.
  - New `--debug-memory` CLI flag: when present, prints `[memory] Recent conversation: …` before each turn so the user can see continuity in action.

**Layer hygiene:** `aether-l1-interaction` has no new dependency on L2; L1 still sees only its own `TurnRouter` trait. L2 has no new outgoing dependency. Only the apps crate (which is already the stitch point between L1/L4/L5/L6) learned about L2.

## 3. Integration point

```text
 main loop ──(handle_turn)──► TurnEngine ──(evaluate)──► L5
                              TurnEngine ──(dispatch)──► MemoryAwareRouter
                                                            │ load recent(sess)
                                                            │ render_transcript
                                                            │ prepend
                                                            ▼
                                                         ModelRouterAdapter
                                                            │
                                                            ▼
                                                         L4 ModelRouter
 main loop ──(append user_record + assistant_record)─► SessionMemoryStore
```

## 4. Tests and checks

### 4.1 Tests added

**`packages/l2-memory` (module unit tests, 7 new):**

- `append_preserves_order_and_assigns_sequences`
- `max_turns_evicts_oldest`
- `max_chars_evicts_oldest`
- `sessions_are_isolated`
- `clear_session_removes_only_one_session`
- `recent_on_unknown_session_is_empty_not_error`
- `render_transcript_is_deterministic_and_skips_empty`

**`apps/l1-cli` (module unit tests, 6 new):**

- `build_prompt_with_empty_window_returns_raw_utterance`
- `build_prompt_prepends_rendered_transcript_and_user_line`
- `second_turn_prompt_contains_first_turn_content` — the integration-style test: drives two sequential dispatches through `MemoryAwareRouter` over a `CapturingRouter` stub, appends to memory between them, asserts the second prompt contains `"- User: what's the weather"`, `"- Aether: ok"`, and ends with `"User: and tomorrow"`.
- `different_sessions_do_not_see_each_others_memory` — builds two `MemoryAwareRouter`s over the same store with different session ids, appends into A, dispatches into B, confirms B's prompt is clean.
- `summarise_for_allow_uses_route_response`
- `summarise_for_deny_uses_system_note`

### 4.2 Check results

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (pre-existing unused-import warnings in `l5-policy/src/decision.rs` and two `missing_docs` in `l1-interaction/src/events.rs` are unchanged — not in scope) |
| `cargo test --workspace` | all crates green |
| `cargo test -p aether-l1-cli` | **14 / 14 passed** (8 prior + 6 new) |
| `cargo test -p aether-l2-memory` | **7 + 2 passed** (7 new session + 2 pre-existing smoke) |
| `python tools/lint-layer-boundaries/check.py` | `OK (0 violations)` |

## 5. Limitations and future work

- **In-process only.** `InMemorySessionMemoryStore` dies with the process. No session restoration across restarts.
- **No summarisation.** Once bounds are hit, older turns are evicted verbatim. A future wave can fold evicted content into a running summary.
- **Byte-length bounds.** `content.len()` is byte count, not token count or UTF-8 scalar count. Acceptable for a narrow slice; a real implementation should use a tokenizer for `max_chars`-as-`max_tokens`.
- **No privacy-posture gate.** This path bypasses the eventual L5 posture check that the richer kernel will enforce. L2.1 records are all treated as session-ephemeral and stay entirely inside the process — no remote route, no durable write.
- **Demo-side orchestration.** The main loop explicitly appends both user and assistant records. A cleaner future pattern is to let L1 emit a typed `TurnCompleted` event and have the demo subscribe, but that requires wider event-bus plumbing.
- **No user controls.** No "forget that", no "clear conversation", no inspect/edit UI. That belongs to L7 and a future UX surface.
- **Single shared session id in the CLI.** `SESSION = "demo-session"` is hard-coded. Multi-session is a trivial extension once a real UX surface lands.

## 6. Recommended next session

**L7.1 — approval surface for Ask tickets.**

Rationale: the remaining single largest "not a companion yet" gap is that when L5 returns `Decision::Ask` the demo simply stops with `BlockReason::AwaitingApproval`. The turn is dead. With L2.1 in place, the next thing a user hits is "I asked it to write a file, it said 'awaiting approval' and then… nothing." A minimal approval surface (accept/reject per open ticket, re-enter the turn FSM, record the outcome) is the narrowest cut that unblocks the whole write/edit/delete path and makes the human-in-loop story real.

Caveat: if driving this demo surfaces a worse gap (e.g. the transcript block blows past the model's context, or block-reason notes drown out the real conversation), prioritise the fix first. Memory quality is easier to judge now that memory exists.

---

**Commits (local, unpushed):** none yet — all changes currently uncommitted on `dev`. Don should review and commit (suggested: one commit for L2 session module + tests, one commit for demo wiring + tests + docs) before resuming.
