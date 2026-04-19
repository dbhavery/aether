# 18 — Model Router Specification

The model router is a **must-own custom layer** (see [01_product_doctrine.md](01_product_doctrine.md)). It decides, per turn, which model handles the response — routing between the reflex path (local Gemma 4) and deliberative path (local large variant or remote frontier).

Ported and generalized from v1.0 `LLM-PROVIDERS.md` — the v1.0 `litellm`-based abstraction is replaced with a custom Rust-backed router for Aether Pro.

---

## Tier abstraction

Cognition code never asks for a specific model. It asks for a **tier**:

```
route_tier(
    tier="main",             # fast | main | heavy
    messages=[...],
    stream=True,
)
```

The router maps tier → concrete model based on:
- User's configured providers
- Performance tier (Lite / Balanced / Full)
- Privacy scope of the task
- Current network state
- Budget and cost policy
- Persona `llm_preferences` hint

### Three canonical tiers

| Tier | Purpose | Latency budget | Default model |
|------|---------|---------------|---------------|
| **fast** | Greetings, intent classification, instant acknowledgments, idle backchannels, state classification | First token < 200 ms under good conditions | Gemma 4 (smallest variant) local |
| **main** | General conversation, normal chat turns | First token < 1500 ms | Gemma 4 (tier-sized) local; frontier if escalated |
| **heavy** | Complex reasoning, long-form, research, multi-step tools | No hard budget — takes as long as needed | Gemma 4 largest for local-only; frontier LLM for hardest |

**Important:** these are the new plan's tiers. The v1.0 `fast/main/heavy` split carries forward conceptually, but the concrete model choices are different:
- v1.0 fast-tier default was Ollama qwen2.5:7b → **NEW:** Gemma 4
- v1.0 main/heavy defaulted to claude-sonnet / claude-opus BYOK → **NEW:** local Gemma 4 first, frontier only when escalated

---

## Default local LLM: Gemma 4

Per [09_realtime_interaction.md](09_realtime_interaction.md) and [16_tech_stack.md](16_tech_stack.md):

- **Reflex path:** always local Gemma 4 (smallest variant for Lite tier; largest available for Full tier)
- **Local deliberative:** Gemma 4 (larger variant) when VRAM budget allows and privacy/offline scope applies
- **Remote deliberative:** frontier LLM (Anthropic / OpenAI / equivalent) only for hardest tasks

### Per-tier model sizing

| Tier | Reflex path | Local deliberative | Remote escalation |
|------|-------------|--------------------|-------------------|
| **Lite** | Gemma 4 smallest | N/A — always remote | Required for non-reflex |
| **Balanced** | Gemma 4 mid | Gemma 4 mid | Frontier for edge cases |
| **Full / Pro** | Gemma 4 largest within 50% VRAM | Gemma 4 largest | Frontier only for hardest tasks |

Variant selection is auto-recommended during onboarding based on detected VRAM; expert override available.

---

## Complexity routing

The router classifies each turn in three stages (same pattern carries forward from v1.0):

1. **Level 1 — Instant match.** Regex for greetings, farewells, thanks → FAST.
2. **Level 2 — Keyword match.** Regex for "research", "explain", "analyze", "deep", "code" → HEAVY. Regex for "what time", "weather", "news", "search" → MAIN (with grounding if provider supports).
3. **Level 3 — LLM classify.** FAST-tier model classifies intent with a short prompt; output cached (LRU-100).

### Routing decision includes

- Tier selection (fast / main / heavy)
- Whether to emit an acknowledgment phrase first (when expected latency > 600 ms AND tier ≠ fast)
- Whether to enable tool grounding (search, code execution, browser)
- Whether the request needs explicit user approval (policy check)

---

## Fallback chains

Every call has a cascade. If primary fails, fall through:

```
HEAVY → MAIN → FAST → [local-only fallback] → user-visible error
```

### Failure categories

- **Network timeout** (default 10 s): try next tier
- **401 / 403** (key invalid): notify user, don't silently retry
- **429** (rate limit): back off, try next tier
- **500 / 503** (provider issue): try next tier
- **Local OOM / VRAM pressure**: downgrade local model variant; if impossible, escalate to remote

Users are never told "Anthropic is down" mid-conversation. They see the response come through the next tier. Trust center (see `13_trust_security_redteam.md`) surfaces recent fallbacks so the user can see observability data if they care.

---

## Provider catalog

The router supports an expandable provider set. Current candidates:

| Provider | Class | Role |
|----------|-------|------|
| **Local Gemma 4** | Local, always | Default for reflex + local deliberative |
| **Anthropic** | Cloud, BYOK | Claude models for deliberative escalation |
| **OpenAI** | Cloud, BYOK | GPT models for deliberative |
| **Google** | Cloud, BYOK | Gemini for grounded / search-linked tasks |
| **Groq** | Cloud, free tier + BYOK | High-speed inference for specific tasks |
| **OpenRouter** | Cloud, pay-as-you-go | Aggregator (one key, many models) |
| **Ollama** | Local, user-managed | Alternative local inference (user provides models) |

### Aether Pro design

The Pro router does **not** use `litellm` as the abstraction (v1.0 pattern). Instead:

- **Custom Rust-backed router** — each provider is a typed adapter behind a uniform `route_tier()` interface
- **Provider adapters** isolate vendor-specific streaming/tool/error semantics
- **One integration point** but NOT via a borrowed library that could constrain or change underneath us

Rationale: the model router is a must-own layer. Depending on `litellm` (or similar) makes the router someone else's product. Aether Pro owns this.

---

## Wizard presets (user-facing)

During onboarding, the user picks a preset. Each maps to tier choices:

| Preset | fast | main | heavy | Notes |
|--------|------|------|-------|-------|
| **Local only (Gemma 4)** | Gemma 4 small | Gemma 4 tier-sized | Gemma 4 largest | No cloud; no BYOK needed |
| **Anthropic BYOK** | Gemma 4 local | Claude Sonnet | Claude Opus | Cloud escalation for deep tasks |
| **OpenAI BYOK** | Gemma 4 local | GPT-main | GPT-thinking | — |
| **Google BYOK** | Gemma 4 local | Gemini Flash | Gemini Pro | — |
| **Groq BYOK** | Gemma 4 local | Groq-hosted LLaMA | Escalate to other frontier | — |
| **OpenRouter BYOK** | Gemma 4 local | OpenRouter-configurable | OpenRouter-configurable | — |
| **Mixed BYOK** | Gemma 4 local | user-selected | user-selected | Advanced users mix providers per tier |

Advanced users can override any tier per persona or task-type in settings.

---

## Key storage (BYOK)

BYOK keys never touch disk as plaintext.

- **Primary:** OS keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service)
  - Service name: `aether.<provider>` (e.g., `aether.anthropic`)
  - Username: the user's installation UUID
  - Password: the API key
- **Mirror:** encrypted file fallback only when keyring is unavailable — derived from machine-specific secret
- **Never:** plaintext in config, env vars, logs, crash reports, telemetry

Key rotation, deletion, and "test this key" actions are first-class settings surfaces.

---

## Per-persona LLM preferences

A persona's `persona.yaml` can specify a nudge (not a hard override):

```yaml
llm_preferences:
  preferred_tier: "main"
  temperature: 0.7
  max_output_tokens: 1024
```

The complexity router still escalates to HEAVY for genuinely complex queries and downgrades to FAST for trivial ones. The persona nudge is a starting point, not a ceiling.

Advanced users can pin a specific model (not just tier) per persona in settings: "Atlas always uses the largest model." This overrides the complexity router entirely for that persona.

---

## Cost visibility (BYOK)

For BYOK providers, the router tracks and displays:

- **Rolling costs:** last-hour, today, this-month spend per provider
- **Token counting:** prompt + completion tokens per call, aggregated
- **Estimated USD:** using provider pricing tables (kept updated)
- **Budgets:** optional warn-at / hard-cap-at thresholds
- **No PII in cost logs:** only aggregate tokens + estimated USD

For local (Gemma 4): `$0.00` displayed, but token counts shown for parity.

---

## Streaming

All LLM calls stream by default:

- Router emits typed events into the event bus (see [08_system_architecture.md](08_system_architecture.md))
- Frontend assembles via WebSocket (desktop) or native IPC (future mobile)
- Non-streaming is a per-call flag for cases where the UI needs the full response at once (e.g., onboarding welcome message)

Streaming contract (logical):
```
for chunk in router.route_tier(tier="main", messages=..., stream=True):
    # chunk.content: str delta
    # chunk.finish_reason: None | "stop" | "length" | "error"
    # chunk.tier_used: the actual tier after cascades
    # chunk.provider: the resolved provider
    ...
```

---

## Tool calling

**Aether Pro phase 4+.** (See [roadmaps/aether_pro.md](roadmaps/aether_pro.md#phase-4-tools-and-autonomy).)

- Tool calls go through the **policy engine** (see [12_permissions_autonomy.md](12_permissions_autonomy.md)) — no bypass
- Tool definitions live in `src/tools/<tool>.rs` (or equivalent); router calls tools only after policy approval
- Every tool invocation emits `action_request` → policy → `action_approval` or denial
- Audit log records every tool call with intent, target, outcome

v1.0 had PC control tools (pyautogui, psutil) — these **do not carry forward** to Aether Pro. Pro starts with safer scoped tools (browser, files, memory) behind strict permissions.

---

## Testing

Every provider adapter has a test suite:
- Real streaming call with minimal prompt
- Asserts response has content and finishes cleanly
- Runs against env-stored test keys in CI (scoped minimally)

Fallback chain tested with mocked failures to verify cascade behavior.

Contract tests verify the router produces the same events for equivalent prompts across providers where that's meaningful.

---

## Anti-patterns (rejected)

- **Vendor-lock via a 3rd-party "one-library-for-all-providers" dependency** — the router is a must-own layer; we don't outsource it.
- **Router inside the LLM prompt** — the router decides *before* the LLM call; not by asking an LLM which model to call.
- **Silent cost overruns** — budget caps are hard. User is always informed before exceeding a configured threshold.
- **Cross-turn tier memory** — each turn routes fresh. Sticky tier selection creates drift.
- **Automatic PII forwarding to cloud** — privacy-sensitive scopes stay local by router policy, not by user discipline.

---

## Migration from v1.0 conceptually

v1.0 model routing (from `file:///C:/Users/dbhav/Projects/aether/docs/LLM-PROVIDERS.md`) concepts that carry forward:
- ✅ Tier abstraction (fast / main / heavy)
- ✅ Three-stage complexity classification
- ✅ Fallback cascades
- ✅ Per-persona nudge
- ✅ Cost visibility with BYOK
- ✅ Streaming contract
- ✅ OS keyring for BYOK keys

v1.0 concepts that **do not** carry forward:
- ❌ `litellm` as the integration library (Aether Pro owns the router)
- ❌ Ollama qwen2.5:7b as default fast (replaced with Gemma 4)
- ❌ Guest mode / Aether Guest endpoint (see [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) — candidate for Pro onboarding low-friction tier)
- ❌ PC control tool invocations (`pyautogui`, `psutil`) — replaced with safer scoped tools behind policy engine

---

## Cross-references
- Doctrine (must-own status): [01_product_doctrine.md](01_product_doctrine.md)
- Realtime model (two-speed cognition): [09_realtime_interaction.md](09_realtime_interaction.md)
- Tech stack (Gemma 4, inference runtime): [16_tech_stack.md](16_tech_stack.md)
- Performance tiers (VRAM budget by tier): [14_performance_tiers_vram.md](14_performance_tiers_vram.md)
- Permissions (tool policy engine): [12_permissions_autonomy.md](12_permissions_autonomy.md)
- Persona LLM preferences: [17_persona_pack_schema.md](17_persona_pack_schema.md)
