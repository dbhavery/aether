# L4.1 — Typed provider errors

**Date:** 2026-04-20 (P2c)
**Branch:** `dev` (local, not pushed)

---

## 1. Status

**Complete.** `L4Error` now carries five typed provider variants, and
`OllamaProvider` classifies every transport / HTTP failure into the
right one so the UI can show language like "Ollama isn't running —
start it with `ollama serve`" or "That model isn't installed" instead
of a raw `provider: ureq::Error: Connection refused ...` string.

## 2. What shipped

### `packages/l4-router/src/error.rs`

Five new variants on `L4Error`:

- `ProviderTimeout { detail }`
- `ProviderNotRunning { detail }`
- `ProviderModelNotFound { model, detail }`
- `ProviderBadResponse { detail }`
- `ProviderUnknown { detail }`

The existing `Provider(String)` variant is kept for back-compat (both
so external consumers that pattern-match on it don't break, and as a
catch-all for provider errors that don't fit any of the new shapes).
Docstring guides new code to the typed variants.

### `packages/l4-router/src/providers/ollama.rs`

- New private helper `classify_ureq_error(err, model) -> L4Error`:
  - `Status(404, body)` with body containing "model" / "not found" →
    `ProviderModelNotFound { model, detail: body }`.
  - `Status(other, body)` → `ProviderUnknown { detail }`.
  - `Transport(ConnectionFailed | Dns)` → `ProviderNotRunning`.
  - `Transport(Io)` with "timed out" / "timeout" in message →
    `ProviderTimeout`.
  - Other `Transport` → `ProviderUnknown`.
- `OllamaProvider::healthcheck` and `OllamaProvider::chat` now route
  ureq errors through `classify_ureq_error`.
- `.into_json()` failures on the response body become
  `ProviderBadResponse`.
- `parse_chat_response` migrated to `ProviderBadResponse` too.

### Tests

- Existing `chat_round_trips_through_mock_ollama` unchanged (still
  covers the happy path).
- `chat_surfaces_provider_error_on_malformed_response_body` updated
  to match on `ProviderBadResponse`.
- **New:** `chat_classifies_connection_refused_as_not_running` —
  grabs an ephemeral port, drops the listener, points the provider at
  the now-vacant port, asserts `ProviderNotRunning`.
- **New:** `chat_classifies_404_model_not_found` — mock responds HTTP
  404 with `{"error":"model 'llama9' not found..."}`, asserts
  `ProviderModelNotFound { model: "llama9", detail: <has "not found"> }`.
- New helper `spawn_mock_ollama_with_status(status, content_type,
  body)` supports both the 200 happy-path test and 404 classification.

## 3. Why typed errors matter (the UI angle)

Right now the desktop shell doesn't render provider errors at all —
`submit_turn` propagates engine errors via `.map_err(|e| format!(...))`
and they show up as Tauri command failures. Once the shell starts
mapping provider failures to transcript system messages, typed
variants give us three things for free:

1. **Actionable copy.** "Ollama isn't running" is a very different UI
   message from "Ollama timed out" or "Ollama doesn't know that model".
2. **Different icons / colours** in the transcript and trust drawer.
3. **Error metrics.** We can count retries by category instead of
   grepping for substrings.

## 4. Checks run

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | clean |
| `cargo test -p aether-l4-router --features ollama-provider` | **14 pass** (was 12, +2 new) |
| `cargo check --features ollama-provider` (src-tauri) | clean |
| `python tools/lint-layer-boundaries/check.py` | OK (0 violations) |

## 5. Known follow-ups

- The shell doesn't yet render any provider errors as transcript
  messages — they still propagate as Tauri command failures. That's
  P2d territory (telemetry + UI meta).
- `Io`-kind timeout detection is heuristic (string-match on "timed
  out" / "timeout"). A stronger classifier would downcast the
  `ureq::Error::source()` chain to an `io::Error` and check
  `ErrorKind::TimedOut` directly, but that requires more careful
  handling than this slice is worth. Upgrade target.
- `healthcheck()` is now more useful — if it returns
  `ProviderNotRunning`, the caller can surface that specifically
  instead of silently falling back.

## 6. Commit

`feat(l4): [L4.1] typed provider error variants for UI-actionable messages`
