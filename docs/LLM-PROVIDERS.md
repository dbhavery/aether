# LLM Provider Abstraction

**Purpose:** Aether supports many LLM providers through a single internal abstraction. Users pick one in the onboarding wizard (or multiple, one per tier). The brain module never imports a specific provider's SDK directly — it always goes through `litellm`.

---

## 1. Why litellm

- 100+ providers supported via one call signature.
- Already in upstream Isabelle dependencies.
- Handles streaming, tool calling, and structured outputs uniformly.
- Unified error types across providers.
- Supports request/response caching, rate limiting, and cost tracking.

Docs: https://docs.litellm.ai/

---

## 2. Supported providers in v1.0

| Provider | Class | Notes |
|----------|-------|-------|
| **Anthropic** | Cloud, paid | Claude Opus / Sonnet / Haiku. Best overall quality. |
| **OpenAI** | Cloud, paid | GPT-5.x series. |
| **Google** | Cloud, paid | Gemini 2.5 Pro / Flash / Flash-Lite. Strong grounding for real-time queries. |
| **Groq** | Cloud, free tier + paid | Llama 3.x / Mixtral at very high speed. Good for fast tier. |
| **OpenRouter** | Cloud, pay-as-you-go | Aggregator — one key, many models. Useful for power users. |
| **Ollama** | Local, free | Any model the user has pulled. Default fast-tier option. |
| **Aether Guest** | Hosted by us, rate-limited | Groq-backed; used only by "Guest mode" on Screen 5 Card C. |

Future (post-v1.0): Mistral, Cohere, Together, DeepSeek, xAI. All are already supported by litellm; we just need to add them to the wizard UI.

---

## 3. Tier abstraction

Brain code never asks for a specific model. It asks for a **tier**:

```python
from src.brain.router import route_tier

response = await route_tier(
    tier="main",             # fast | main | heavy
    messages=[...],
    stream=True,
)
```

The tier gets mapped to an actual model through the user's config:

```yaml
llm:
  provider: "anthropic"
  tier_map:
    fast:  "ollama/qwen2.5:7b"     # Local fast path, even if main is cloud
    main:  "claude-sonnet-4-6"
    heavy: "claude-opus-4-7"
```

Tiers defined:
- **fast** — simple greetings, intent classification, instant acknowledgments, idle backchannels. Must return first token in < 200 ms under good conditions.
- **main** — general conversation, normal chat turns. < 1500 ms first-token acceptable.
- **heavy** — complex reasoning, long-form, research. No hard latency budget; takes as long as it needs.

Some wizard presets:

| User choice in wizard | fast | main | heavy |
|-----------------------|------|------|-------|
| Free & Local (Ollama) | `ollama/qwen2.5:7b` | `ollama/qwen2.5:14b` | `ollama/qwen2.5:32b` (if pulled) else fallback to main |
| Anthropic BYOK | `ollama/qwen2.5:7b` if Ollama detected, else `anthropic/claude-haiku-4-5` | `anthropic/claude-sonnet-4-6` | `anthropic/claude-opus-4-7` |
| OpenAI BYOK | `openai/gpt-5-mini` | `openai/gpt-5` | `openai/gpt-5-thinking` |
| Google BYOK | `gemini/gemini-2.5-flash-lite` | `gemini/gemini-2.5-flash` | `gemini/gemini-2.5-pro` |
| Groq BYOK | `groq/llama-3.3-70b-versatile` | `groq/llama-3.3-70b-versatile` | `groq/llama-3.3-70b-versatile` (no heavy tier on Groq; escalates to no-op) |
| OpenRouter BYOK | `openrouter/google/gemini-flash-1.5` | `openrouter/anthropic/claude-sonnet-4-6` | `openrouter/anthropic/claude-opus-4-7` |
| Guest | `groq/llama-3.3-70b-versatile` | `groq/llama-3.3-70b-versatile` | `groq/llama-3.3-70b-versatile` |

Advanced users can override any of these in Sandbox → LLM settings.

---

## 4. Complexity routing

Brain decides which tier to call for a given input by a three-stage classifier (same pattern as upstream Isabelle):

1. **Level 1 — Instant match.** Regex for greetings, farewells, thanks → FAST.
2. **Level 2 — Keyword match.** Regex for "research", "explain", "deep", "analyze", "code" → HEAVY. Regex for "what time", "weather", "news", "search" → MAIN with grounding if provider supports it.
3. **Level 3 — LLM classify.** Fast-tier model classifies intent with a tiny prompt; output cached in LRU-100.

Routing decision includes:
- Tier selection (fast/main/heavy).
- Whether to emit an acknowledgment phrase first (when tier ≠ fast AND expected-latency > 600 ms).
- Whether to enable tool grounding (search, code execution) — v1.0: always off.

---

## 5. Fallback chains

Every call has a chain. If primary fails, cascade:

```
HEAVY → MAIN → FAST → Aether Guest (if user opted in) → Error
```

Failure categories handled:
- Network timeout (10s default).
- 401/403 (key invalid — notify user, don't silently retry).
- 429 (rate limit — back off, try next tier).
- 500/503 (provider issue — try next tier).

Users are never told "Anthropic is down" mid-conversation. They see the response come through the next tier. In Sandbox → Status, they can see "2 calls fell back to MAIN in the last hour" as observability.

---

## 6. Key storage

API keys never touch disk as plaintext.

- **Primary:** OS keyring (`keyring` Python lib → Windows Credential Manager / macOS Keychain / Secret Service on Linux).
  - Service name: `aether.<provider>` (e.g., `aether.anthropic`).
  - Username: the user's installation UUID.
  - Password: the API key.
- **Mirror:** an encrypted YAML at `%APPDATA%/aether/secrets.enc` using a key derived from a machine-specific secret (for the unusual case of keyring being unavailable).
- **Never:** plaintext in `config.yaml`, environment variables, logs, crash reports, or telemetry.

Access pattern:
```python
from src.shared.secrets import get_key, set_key, delete_key

get_key("anthropic")  # -> str or None
set_key("anthropic", "sk-ant-...")
delete_key("anthropic")
```

---

## 7. Per-persona pinning

A persona can specify a preferred tier in its `persona.yaml`:

```yaml
llm_preferences:
  preferred_tier: "main"
  temperature: 0.7
  max_output_tokens: 1024
```

This is a **nudge**, not a hard override. The complexity router still escalates to HEAVY for genuinely complex queries and falls back to FAST for trivial ones.

Advanced users in Sandbox can pin a specific model (not just tier) per persona. Example: "Atlas always uses Claude Opus." This overrides the complexity router entirely.

---

## 8. Cost visibility

For BYOK providers, display rolling costs:
- Sandbox → LLM → Usage shows: last-hour, today, this-month spend per provider.
- Based on litellm's token-counting + provider pricing tables.
- Budgets optional: user can set "warn at $X/day", "hard cap at $Y/day".
- No PII in cost logs — just aggregate tokens and estimated USD.

For Ollama and Aether Guest: display "$0.00" but still show token counts for parity.

---

## 9. Streaming

All LLM calls stream by default. The brain emits `RESPONSE_TEXT_CHUNK` events to the EventBus; frontend assembles via WebSocket. Non-streaming is a config flag for providers that don't support streaming well, or for cases where the UI needs the full response at once (e.g., wizard welcome message on Screen 8).

Streaming contract:
```python
async for chunk in route_tier(tier="main", messages=[...], stream=True):
    # chunk.content: str (delta)
    # chunk.finish_reason: None | "stop" | "length" | "error"
```

---

## 10. Tool calling

**Not in v1.0.** The existing Isabelle tool system (PC control, file ops, shell exec) is intentionally not ported. v1.0 is a conversational product, not an agent. Tool use returns in the v2 ground-up rebuild.

One exception: built-in, safe tool calls that the frontend needs — `get_current_time`, `get_persona_context`, `change_persona`. These bypass litellm entirely and run as local Python functions gated by a tiny allow-list. They exist so the LLM can answer "what time is it" without hallucinating.

---

## 11. Aether Guest endpoint

For wizard Screen 5 Card C ("Guest mode"), Aether hosts a tiny proxy at a URL like `guest.aether.sh`.

Design:
- Hit Cloudflare Worker that proxies to Groq with our key.
- Rate-limited per installation UUID: 10 requests/hour, 40 requests/day, 4096 max tokens/request.
- Refuses anything that looks like a jailbreak attempt (simple keyword filter).
- Logs aggregate counts only. No prompt or response content stored.

Cost estimate: Groq free tier is generous; a Worker bound to our own $0.01/day caps the blast radius if someone tries to abuse it.

Deferred: if guest mode becomes popular, we can move it to a paid Groq tier or swap to OpenRouter free models.

---

## 12. Testing

Every provider has a test suite under `tests/providers/` that:
- Makes one real streaming call with a minimal prompt.
- Asserts the response has content and finishes cleanly.
- Runs on CI against env-stored test keys (one key per provider, scoped minimally).

Fallback chain tested with mocked failures to verify cascade behavior.

---

## 13. Future (not v1.0)

- Local-model router: detect when `ollama` has new models and offer them in Sandbox.
- Semantic cache: if the same question was answered recently, return the cached answer.
- Cross-provider ensembling: call two providers in parallel and pick the better answer.
- Speculative decoding: use the fast tier to draft, verify with the main tier.
- Model benchmarking harness: let users A/B models for their own workloads.

All deferred. v1.0 scope is tight: one provider at a time per tier, deterministic mapping, clean failures.
