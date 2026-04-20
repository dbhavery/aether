# L4.1 — Ollama provider mock-HTTP integration test

**Date:** 2026-04-20 (P2a)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** `OllamaProvider::chat` now has full end-to-end coverage
through a real TCP socket, not just unit-level `build_chat_payload` +
`parse_chat_response` assertions that existed before.

## 2. What shipped

Two new `#[cfg(test)]` tests inside
`packages/l4-router/src/providers/ollama.rs`, and a small mock HTTP
responder helper to support them:

- `spawn_mock_ollama(response_body)` — binds `127.0.0.1:0` via
  `std::net::TcpListener`, accepts exactly one connection in a
  background thread, reads the full HTTP request (headers + body
  honouring `Content-Length`), writes a canned HTTP/1.1 200 JSON
  response, and returns the captured `method` / `path` / `headers` /
  `body` to the test thread via the `JoinHandle`.
- `find_subslice` — tiny `memmem` replacement so the mock doesn't
  pull in `memchr` just for header delimiting.
- `chat_round_trips_through_mock_ollama` — asserts the full happy
  path: request goes to `POST /api/chat`, carries
  `Content-Type: application/json`, serializes as
  `{"model":"llama3","stream":false,"messages":[{"role":"user",
  "content":"ping"}],...}`, and the response parses to `"pong"`.
- `chat_surfaces_provider_error_on_malformed_response_body` — asserts
  that a syntactically-valid but schema-wrong response body surfaces
  as `L4Error::Provider(...)` with a useful message.

### What this test proves that the old unit tests didn't

- The `ureq` agent actually opens a TCP connection to the configured
  base URL (not some other URL we forgot about).
- The request line is `POST /api/chat HTTP/1.1` (not `GET`, not
  `/api/generate`, not a trailing-slash variant).
- The Content-Type header is set (we relied on `send_json` to do this
  — the test confirms the agent still does).
- The full request body round-trips through serde unchanged.
- The response path in `OllamaProvider::chat` — including the
  `.into_json()` hop — correctly hands off to `parse_chat_response`.

## 3. Deliberate non-goals

- **No new dev-deps.** `std::net::TcpListener` + `std::thread` only,
  as specified in the priority backlog. No `mockito`, `wiremock`,
  `hyper`, or `tokio` added.
- **No real network.** Binds ephemeral `127.0.0.1:0`; each test owns
  its port; mock closes after one request.
- **No streaming test.** The provider is deliberately non-streaming
  for Wave 4. A streaming test belongs to the streaming slice.
- **No `/api/tags` healthcheck test.** The healthcheck hits a
  different endpoint and has its own call path; adding coverage there
  is a trivial follow-up but out of scope here.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean (after one auto-fmt pass) |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | clean |
| `cargo test -p aether-l4-router --features ollama-provider` | **12 pass** (was 10, +2 new) |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. Known follow-ups (absorbed into P2b/c/d)

- The provider still sends a single concatenated `user` prompt. P2b
  introduces `chat_with_messages(&[ChatMessage])` and wires the shell
  to role-tag history.
- `L4Error::Provider(String)` is still the only variant — the mock
  error test just pattern-matches on message text. P2c replaces this
  with typed variants (`Timeout`, `NotRunning`, `ModelNotFound`,
  `BadResponse`).
- No latency/token telemetry propagated. P2d.

## 6. Commit

`feat(l4): [L4.1] mock-HTTP integration test for OllamaProvider::chat`
