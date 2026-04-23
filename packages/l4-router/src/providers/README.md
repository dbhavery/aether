# L4 Provider Adapters

Feature-gated concrete backends behind `ProviderAdapter` / `ModelRouter`.

Nothing in this directory is compiled into the default OSS build — each provider lives behind its own Cargo feature.

## Ollama (`ollama-provider`)

Local-first adapter that talks to a running Ollama daemon via its HTTP `/api/chat` endpoint.

### Enable

```bash
cargo run -p aether-l1-cli --features ollama-provider
```

Pulls `ureq` (blocking HTTP, no TLS) as a transitive dep.

### Runtime opt-in

Env vars (all optional, all have defaults):

| Var | Default | Notes |
|---|---|---|
| `AETHER_OLLAMA_MODEL` | `gemma4` | Setting **any** Ollama env var counts as opt-in. |
| `AETHER_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | |
| `AETHER_OLLAMA_TIMEOUT_MS` | `60000` | Per-request ureq timeout. |

At startup the CLI runs a cheap `GET /api/tags` healthcheck; if it fails the demo falls back to the reflex stub and prints a one-line warning. The companion never hard-crashes on an unreachable daemon.

### Prereqs

1. Install Ollama: <https://ollama.com>
2. Start the daemon: `ollama serve`
3. Pull a model: `ollama pull gemma4` (or whatever you set `AETHER_OLLAMA_MODEL` to)

### Scope of L4.1

- Single provider, single model per process.
- `/api/chat` non-streaming. No tool calls (`execute_tool` errors out).
- Prompt is passed through as one `user` message — the `MemoryAwareRouter` layer upstream already renders recent conversation into the prompt before it reaches here.
- Persona-derived `RouterTier` still surfaces on the `RouteOutcome`, but Ollama treats all tiers the same (one model).

### Future

- Streaming via `/api/chat?stream=true` + incremental `Responding` presence updates.
- Split incoming prompt into role-tagged messages (`system` / `user` / `assistant`) using L6 persona + L2 memory directly.
- Multi-provider routing: `OllamaProvider` for local tiers, a separate adapter for remote tiers, selected by `RouterTier`.
- Cost / latency telemetry into the L5 audit stream.
