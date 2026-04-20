# L4.1 — Role-tagged `/api/chat` messages

**Date:** 2026-04-20 (P2b)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** When the shell is built with `--features ollama-provider`
and Ollama is reachable, every turn now sends a real role-tagged
message array to `/api/chat` — one `system` message with the compiled
persona's system prompt, one message per recorded turn mapped from
`MemoryRole` → `MessageRole`, then the current user utterance. This
lets instruction-tuned models use their own chat template instead of
being handed a pre-rendered transcript string.

The old concat path (`MemoryAwareRouter` + `ModelRouterAdapter`) stays
as the default for the reflex stub and remains the back-compat target
for `OllamaProvider::chat(prompt)`.

## 2. What shipped

### `packages/l4-router/src/providers/ollama.rs`

- New public types `ChatMessage` (owned, `role` + `content`) and
  `MessageRole` (`System` / `User` / `Assistant`, serde
  `rename_all = "lowercase"`).
- New public method `OllamaProvider::chat_with_messages(&[ChatMessage])`
  that POSTs the Ollama-canonical role-tagged payload.
- `OllamaProvider::chat(prompt)` now delegates to
  `chat_with_messages(&[ChatMessage::user(prompt)])` so the single-prompt
  path stays a one-liner.
- New pure helper `build_chat_payload_messages(model, &[ChatMessage])`
  for unit tests and callers that want to inspect the wire shape.
- The internal `ChatMessage<'a>` struct (the old wire-only type) is
  renamed `ChatMessageWire<'a>` to make room for the public
  `ChatMessage`.
- 3 new tests:
  - `build_chat_payload_messages_preserves_role_order`
  - `chat_delegates_to_chat_with_messages_single_user`
  - `chat_with_messages_round_trips_system_user_assistant_user`
    (mock HTTP; asserts a 4-message array round-trips).

### `packages/l4-router/src/lib.rs` + `providers/mod.rs`

- Re-export `ChatMessage` and `MessageRole` at crate root (behind the
  `ollama-provider` feature).

### `apps/desktop/src-tauri/src/memory_router.rs`

- New `RoleTaggedOllamaRouter` (feature-gated) that implements
  `TurnRouter` directly on top of `OllamaProvider`. Owns the memory
  store, session id, system prompt, tier label, and provider label.
- `build_messages(window, system_prompt, utterance) ->
  Vec<ChatMessage>` — exposed for tests. Skips the system entry when
  the prompt is blank. `MemoryRole::System` records (used for
  "policy denied", "draft-only", etc. continuity notes) round-trip as
  `MessageRole::System` so the model sees the real conversation
  state.
- 3 new tests covering the system + history + current user order, the
  blank-system-prompt skip, and the system-record round-trip.

### `apps/desktop/src-tauri/src/provider.rs`

- New `tier_label(RouterTier) -> &'static str` helper, kept in sync
  with the one inside `adapter.rs` so the `RouteOutcome::tier` string
  is identical regardless of which router the shell uses.

### `apps/desktop/src-tauri/src/state.rs`

- `build_router_stack` now picks `RoleTaggedOllamaRouter` when Ollama
  is enabled and healthy, instead of wrapping
  `ModelRouterAdapter(provider)` inside `MemoryAwareRouter`. The
  reflex-stub path is unchanged.
- Passes the compiled persona's `prompts.system` through to the
  router so the system prompt surfaces as a real `system` message
  rather than being inlined into the prompt string.

## 3. Deliberate non-goals

- **Not touching `TurnRouter`'s signature.** `dispatch(prompt: &str)`
  stays as-is. Adding a richer surface to that trait would force all
  downstream routers to adapt — too invasive for one slice.
- **No change to the reflex stub.** The reflex stub still reads one
  prompt. It doesn't have a concept of roles.
- **No streaming.** Ollama's `/api/chat` supports streaming but the
  adapter is still blocking. Streaming is a future slice.
- **No system-prompt truncation.** The compiled persona's system
  prompt goes in as-is; no per-turn rewriting yet.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | clean |
| `cargo test -p aether-l4-router --features ollama-provider` | **17 pass** (was 14, +3 new) |
| `cargo check` (src-tauri default) | clean |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `cargo test --features ollama-provider` (src-tauri) | **12 pass** (was 9, +3 new) |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. Known follow-ups

- The provider label is just `"ollama"` — the transcript meta-footer
  could carry the model id (`ollama/gemma3`) once P2d telemetry lands.
- The reflex stub doesn't get the role-tagged treatment. That's a
  deliberate non-goal; if we ever add a second real provider, we'll
  lift `RoleTaggedOllamaRouter` into a generic `RoleTaggedRouter<P>`.
- `MemoryAwareRouter::build_prompt` is now dead code for the ollama
  path but still alive for the reflex path. Don't remove it yet.

## 6. Commit

`feat(l4,apps/desktop): [L4.1] role-tagged /api/chat messages for Ollama`
