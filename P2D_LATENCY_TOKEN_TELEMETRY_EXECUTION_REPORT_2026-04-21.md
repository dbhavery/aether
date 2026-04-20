# P1 / P2d — Latency + token telemetry in RouteOutcome and UI

**Date:** 2026-04-21
**Branch:** `dev`
**Parent run:** Continuation of 2026-04-20 autonomous build.
**Layers touched:** L1 (interaction), L4 (router), apps/desktop shell.

## What shipped

1. **L1 RouteOutcome** gained `latency_ms: Option<u64>` and
   `tokens: Option<TokenUsage>` fields (`TokenUsage { prompt, completion }`).
   Both are `Option` so synthetic `RouteOutcome`s (test stubs,
   post-approval denial reconstruction) keep compiling without having to
   lie about timing.
2. **TurnEngine::handle_turn** wraps the `router.dispatch` call in an
   `Instant::now() → elapsed()` measurement and overwrites
   `latency_ms` on the Allow path. Measuring outside the router means
   every adapter (echo stub, reflex stub, Ollama) gets a consistent
   number without self-timing. Routers that pre-populate the field are
   deliberately overwritten.
3. **L4 OllamaProvider** gained `chat_with_messages_detailed` returning a
   new `ChatCompletion { text, prompt_tokens, completion_tokens }`. The
   wire `ChatResponse` struct now captures `prompt_eval_count` and
   `eval_count`. Back-compat `chat_with_messages` still returns `String`
   (delegates + drops counts). New pure parser
   `parse_chat_response_detailed` is exposed.
4. **Shell RoleTaggedOllamaRouter** switched to
   `chat_with_messages_detailed` and populates `RouteOutcome::tokens`
   when both counts are reported by the daemon. When only one side is
   present, `tokens` stays `None` — a half-filled TokenUsage would be
   harder for the UI to render truthfully than an omission.
5. **Shell MessageMeta** gained `latency_ms`, `prompt_tokens`,
   `completion_tokens`, all `#[serde(skip_serializing_if = "Option::is_none")]`
   so stubbed turns don't bloat the IPC surface.
6. **UI Transcript** now renders a dot-separated meta footer:
   `tier · provider · 1.4s · p42/c17 tok`. Formatting rules:
   - `<1000ms` → `820ms`, else `1.4s`.
   - Both token counts present → `p<N>/c<N> tok`, one side only →
     `<N> tok`, both absent → token segment omitted.
7. **Tests added (5 new, all green):**
   - `parse_chat_response_detailed_extracts_token_counts`
   - `parse_chat_response_detailed_tolerates_missing_token_counts`
   - `chat_with_messages_detailed_captures_counts_from_mock` (mock-HTTP)
   - `turn_slice.rs::allow_path_reaches_router_and_completes`
     extended with `latency_ms.is_some()` + `tokens.is_none()` on the
     reflex path.

## What I explicitly did not change

- Persistent / durable storage of per-turn telemetry. P3 will handle the
  SQLite conversation log; piping `latency_ms` into that schema is a
  P3-adjacent task, not P1.
- Cross-crate telemetry crate (`packages/telemetry`). The field lives
  on `RouteOutcome` because that's what crosses the L1→shell boundary;
  nothing beyond the shell reads it today.
- Streaming. Ollama non-streaming only — Wave 5+ work.
- Reflex stub latency attribution. Populated by `TurnEngine` but
  effectively 0–1ms on this machine; not meaningful for the stub.

## Checks run

- `cargo fmt --all -- --check` — clean.
- `cargo check --workspace` — clean (pre-existing doc-lint warnings only).
- `cargo test --workspace` — all pass (same green count + 2 new assertions).
- `cargo test -p aether-l4-router --features ollama-provider` — 20 passed.
- `cd apps/desktop/src-tauri && cargo test` — 9 passed.
- `cd apps/desktop/src-tauri && cargo test --features ollama-provider` — 12 passed.
- `cd apps/desktop && pnpm typecheck` — clean.
- `pnpm build` — 45 modules transformed; production bundle OK.
- `python tools/lint-layer-boundaries/check.py` — 0 violations
  across 11 workspace crates.

## Risks / follow-ups

- `latency_ms` is stamped *per dispatch*, not *per turn*. If a future
  wave introduces retry-inside-router, the number will describe only
  the last attempt. Acceptable for the v0 meta footer; worth revisiting
  when P3 lands real telemetry rows.
- `TokenUsage` is optional end-to-end. If a user ever reports "no
  tokens shown", the culprit is almost always the daemon/model pair
  not emitting `eval_count` — worth surfacing in `README.md` when the
  shell gains real user-facing docs.
- The meta footer now shows four pieces; visually fine in the dev
  shell but could crowd a narrow viewport. If we add a fifth piece
  (e.g. cost) we'll want to collapse to an expandable chip.
