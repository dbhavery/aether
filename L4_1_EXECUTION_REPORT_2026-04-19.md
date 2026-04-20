# L4.1 Execution Report — Real Provider Adapter (Ollama)

**Date:** 2026-04-19
**Branch:** dev
**Status:** Complete, tests green both with and without feature, boundary lint clean, not pushed.

---

## 1. Provider chosen — Ollama

Why Ollama for the first slice:

- Runs locally (`ollama serve`) with zero authentication and no remote egress — aligns with the local-first posture Aether already commits to in policy and persona defaults.
- HTTP surface (`/api/chat`) is stable, documented, and trivial to hit synchronously.
- No Rust SDK dependency needed; a tiny blocking HTTP client (`ureq`, no TLS) is enough. That keeps the default build free of async runtimes and keeps the Ollama dep behind a feature flag.
- Feature parity target: the existing `ReflexModelRouter` implements `ModelRouter` with one blocking `route(tier, prompt)` method. Ollama's non-streaming `/api/chat` matches that shape 1:1.

llama.cpp server was the other candidate but requires more user setup and carries more wire-format variation across releases. Revisit in a later wave once the Ollama path is battle-tested.

## 2. APIs / types added in L4

### 2.1 `packages/l4-router/src/providers/mod.rs`

Feature-gated submodule namespace. Re-exports `OllamaConfig`, `OllamaConfigError`, `OllamaProvider` when `ollama-provider` is on; empty otherwise.

### 2.2 `packages/l4-router/src/providers/ollama.rs`

Public surface:

```rust
pub struct OllamaConfig {
    pub base_url: String,   // default "http://127.0.0.1:11434"
    pub model: String,      // default "llama3"
    pub timeout_ms: u64,    // default 60_000
}
impl OllamaConfig {
    pub fn from_env() -> Result<Self, OllamaConfigError>;
    pub fn env_opts_in() -> bool;
}

pub enum OllamaConfigError { InvalidTimeout(String), EmptyBaseUrl, EmptyModel }

pub struct OllamaProvider { /* config + ureq::Agent */ }
impl OllamaProvider {
    pub fn new(cfg: OllamaConfig) -> Self;
    pub fn model(&self) -> &str;
    pub fn base_url(&self) -> &str;
    pub fn healthcheck(&self) -> Result<(), L4Error>;   // GET /api/tags
    pub fn chat(&self, prompt: &str) -> Result<String, L4Error>; // POST /api/chat
}

// Both traits — the existing L4 `ProviderAdapter` and `ModelRouter`.
impl ProviderAdapter for OllamaProvider { … }
impl ModelRouter for OllamaProvider { … }

// Pure helpers exposed for unit tests and wire-shape inspection.
pub fn build_chat_payload(model: &str, prompt: &str) -> serde_json::Value;
pub fn parse_chat_response(json: &serde_json::Value) -> Result<String, L4Error>;
```

Internal wire shapes (`ChatRequest`, `ChatMessage`, `ChatOptions`, `ChatResponse`, `OwnedChatMessage`) stay private — callers round-trip through the public helpers.

Design choices:

- `ureq` chosen over `reqwest`: pure-Rust, no async runtime, no TLS deps needed for localhost Ollama. Behind the feature so the default build pulls zero of it.
- Blocking only for Wave 4.1. Streaming (`stream: true`) is a later wave; the `ModelRouter::route` signature is already synchronous.
- `RouterTier` accepted on the route surface but not forwarded to Ollama — a single-model adapter doesn't tier-discriminate. Persona-derived tier continues to surface on `RouteOutcome` so downstream UX still sees it.
- No tool-call dispatch. `execute_tool` returns `ToolError::Internal(...)`; documented in the README. Tool use lands with the router rewrite in a later wave.

## 3. Configuration and feature flags

### Build-time

```toml
# packages/l4-router/Cargo.toml
[dependencies]
ureq = { version = "2", default-features = false, features = ["json"], optional = true }

[features]
default = []
ollama-provider = ["dep:ureq"]
```

```toml
# apps/l1-cli/Cargo.toml
[features]
default = []
ollama-provider = ["aether-l4-router/ollama-provider"]
```

### Run-time

Two gates:

1. `ollama-provider` feature compiled in.
2. At least one of `AETHER_OLLAMA_MODEL` or `AETHER_OLLAMA_BASE_URL` set (the `env_opts_in()` predicate). Without that, even a feature-on build uses the reflex stub. Goal: feature-on builds that are run on a machine without Ollama should still work.

Defaults fill in anything unset. An invalid `AETHER_OLLAMA_TIMEOUT_MS` surfaces as `OllamaConfigError::InvalidTimeout`; empty base URL / model as `EmptyBaseUrl` / `EmptyModel`.

## 4. How the CLI/demo uses the provider

`build_engine` now delegates router selection to `choose_router(tier, memory_store)`, a pair of feature-gated implementations:

- **`#[cfg(feature = "ollama-provider")]`** path:
  1. Check `OllamaConfig::env_opts_in()`. If false → stub fallback.
  2. `OllamaConfig::from_env()`. If error → print `[model] Invalid Ollama config (…)` on stderr, stub fallback.
  3. `OllamaProvider::new(cfg)` + `healthcheck()`. If healthcheck fails → print `[model] Ollama daemon not reachable (…)` on stderr, stub fallback.
  4. On success: print `[model] Using Ollama model <name> via <url>` on stdout, then wrap the provider in the existing `ModelRouterAdapter` → `MemoryAwareRouter` stack.

- **`#[cfg(not(feature = "ollama-provider"))]`** path: direct call to `build_stub_router`, identical to prior behaviour.

Result: every run prints a clear one-liner about which backend was chosen, and the demo never panics or hangs because Ollama isn't running. The persona, memory, approval, and presence paths are unchanged — the router swap is a pure substitution at one seam.

### Runbook (new section in `packages/l4-router/src/providers/README.md`)

```bash
# 1. install Ollama (https://ollama.com)
# 2. start the daemon
ollama serve

# 3. pull a model
ollama pull llama3

# 4. run Aether with the provider
export AETHER_OLLAMA_MODEL=llama3
cargo run -p aether-l1-cli --features ollama-provider
```

## 5. Tests / checks

### 5.1 Tests added — `aether-l4-router` (10 unit tests, feature-gated)

| Test | What it covers |
|---|---|
| `from_env_uses_defaults_when_vars_unset` | Defaults fill in when no env is set. |
| `from_env_reads_explicit_values` | All three env vars flow through. |
| `from_env_rejects_non_numeric_timeout` | `AETHER_OLLAMA_TIMEOUT_MS=lots` → `InvalidTimeout`. |
| `from_env_rejects_empty_base_url` | Explicit empty string → `EmptyBaseUrl`. |
| `env_opts_in_detects_either_var` | `env_opts_in()` true iff at least one var is set. |
| `build_chat_payload_shapes_single_user_message` | Request JSON has `model`, `messages[0].role="user"`, `messages[0].content=<prompt>`, `stream=false`, `options.num_predict=512`. |
| `parse_chat_response_extracts_assistant_content` | Happy-path JSON → assistant text. |
| `parse_chat_response_tolerates_missing_done_flag` | Daemons that omit `done` on terminal chunk still parse. |
| `parse_chat_response_errors_on_malformed_body` | Bad JSON → typed `L4Error::Provider`. |
| `provider_id_is_stable` | `ProviderId("ollama")` + accessor consistency. |

All env-mutating tests serialize via a process-wide `OnceLock<Mutex<()>>` so they don't race on shared `std::env`. Each grabs the lock, sets the full env trio, then clears on drop. Result: 10/10 stable across `cargo test --features ollama-provider`.

### 5.2 Check results

| Check | Result |
|---|---|
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean (only pre-existing warnings) |
| `cargo check -p aether-l1-cli --features ollama-provider` | clean |
| `cargo test --workspace` | 37 `test result: ok` groups, 0 failed |
| `cargo test --workspace --features aether-l1-cli/ollama-provider` | 37 `test result: ok` groups (10 new), 0 failed |
| `cargo test -p aether-l4-router --features ollama-provider` | 10 unit + 1 smoke |
| `python tools/lint-layer-boundaries/check.py` | `OK (0 violations)` — L4's new optional dep is not a workspace edge, so the linter stays clean. |

## 6. Limitations and future work

- **No streaming.** The whole reply arrives at once from Ollama. Token-level output is out of scope for L4.1; the next wave can stream into a per-chunk `Responding` presence update.
- **Non-network only in tests.** The provider `chat` path is never exercised in CI — only wire-shape encoders/decoders are. Adding a mock HTTP server (wiremock / tiny-http) is a straightforward next step; kept out here to avoid a new dev-dep.
- **Single model, single provider.** No tier-based routing (local-tiny → local-full → remote-*), no per-turn provider swap. The scaffolding is there (`RouterTier` flows through `route`) but Ollama is the only real backend.
- **Prompt is a single `user` message.** The `MemoryAwareRouter` upstream renders transcript into one string. A richer path would split L2 memory into `role`-tagged messages and pass the L6 persona system prompt as a `system` message, but that requires reshaping either L2's render helper or the L4 message contract.
- **No L5-audit integration for model calls.** L4.1 does not emit cost / latency / token events into the L5 audit stream. The `PolicyCommands::audit_append` surface is the natural target.
- **Error surfacing is a one-line eprint.** The demo falls back silently-ish when Ollama is down or misconfigured. A trust-centre view of provider health (pairs nicely with L7.1) is a later UX wave.
- **`ureq` is blocking.** Fine for a REPL; insufficient once a Tauri shell wants non-blocking interaction. Swap-out cost is low because it's bounded to `OllamaProvider`.

## 7. Recommended next session

**Option A — Tauri desktop shell v0.**

Rationale: L2.1 memory, L7.1 approvals, L3.1 presence, and L4.1 real provider are all in. The companion now remembers, asks permission, shows its state, and can speak through a real model. The one remaining "not a product yet" gap is that it still lives in a terminal. A minimal Tauri shell (single window, token-streaming response area, presence dot, approval modal bound to `ApprovalSurface`, memory-aware session) is the first real Aether product surface. The cost: non-trivial — new crate, IPC boundary, webview tooling. Schedule for a full afternoon.

**Option B — harden L4.1 before moving on.**

If the manual runbook (install Ollama, pull a model, run with feature flag) surfaces pain points — timeouts, prompt shape issues, rate-of-response on small models, context length errors — fix those first. Candidates: streaming, role-tagged messages, audit events, a mock HTTP server in tests.

Suggested call: **A**, unless a real Ollama run reveals something that would make the Tauri shell ship a broken experience. In that case do **B** first.

---

**Commits (local, unpushed):** none yet on top of the existing L2.1 + L7.1 + L3.1 work. Suggested split — one commit for L4 `providers/ollama.rs` + feature + tests, one commit for the demo-side `choose_router` wiring + Cargo features + provider README.
