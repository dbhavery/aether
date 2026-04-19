# L4 — Model Router

**Status:** draft
**Last updated:** 2026-04-18
**Layer type:** must-own (doctrine §1.3)
**Depends on:** L1 (reflex hands off routable turns), L5 (policy scope enforcement), L2 (memory-confidence signal).
**Blocked by:** none.

---

## Purpose

Latency-aware local-vs-remote decision engine. Takes a turn's context (intent, memory confidence, tool availability, persona privacy posture, user cost posture) and decides: which model tier (fast / main / heavy), which provider (local Gemma 4 / frontier API / BYOK), which fallback chain.

## Why must-own

Routing is the single place where cost, privacy, latency, and quality are traded. Ceding this to a vendor (e.g. one cloud API) caps the ceiling and leaks data. The router *is* the product's economics and privacy surface.

## Boundaries

**Owns:**
- Tier abstraction (fast / main / heavy).
- Routing policy (inputs → decision).
- Fallback chain (primary → secondary → offline-degraded).
- Cost accounting + budget caps + per-provider rolling costs (ported from v1.0 — see content-lock).
- BYOK key management (user-owned keys; scoped; revocable).
- Privacy-posture enforcement (never route private-memory turns to remote without explicit consent).
- Prompt compilation handoff (persona → compiled system prompt → sent to selected model).

**Does not own:**
- Inference runtimes (borrowable — Ollama, llama.cpp, vLLM, Anthropic/OpenAI SDKs).
- The models themselves.
- Persona content (L6).
- Permission evaluation for tool-using models (L5).

## Dependencies

- **L1** — receives routable turns from reflex.
- **L2** — memory confidence feeds routing (low confidence → escalate).
- **L5** — tool-plan turns must pass policy pre-route.
- **L6** — persona supplies privacy posture and compiled prompt.
- **Trust center** — exposes routing decisions per turn (for audit).

## Borrowable vs custom

| Piece | Decision |
|---|---|
| Inference runtimes | **Borrow** all (Ollama for local, vendor SDKs for remote). |
| Model weights | **Borrow.** Gemma 4 is doctrine default. |
| Tier abstraction | **Custom.** Defines the API the rest of the system calls. |
| Routing policy | **Custom.** Moat surface. |
| Cost accounting | **Custom** (ported from v1.0). |
| BYOK key vault | **Custom.** Uses OS keychain (borrow) behind our interface. |
| Fallback orchestrator | **Custom.** |

## Tier abstraction

| Tier | Purpose | Default model | Latency target |
|---|---|---|---|
| **fast** | Reflex classifier, intent hints | Gemma 4 2B local | <150 ms |
| **main** | Conversational deliberation | Gemma 4 9B local | <2 s TTFT |
| **heavy** | Research, tool planning, long reasoning | Frontier API (Claude/GPT) or Gemma 4 27B local | <5 s TTFT |

All three tiers have local fallbacks on all performance tiers (may degrade model size, not abstraction).

## Key risks

1. **Silent remote escalation.** User thought they were local-only; private data leaked. Mitigation: hard privacy-posture gate; remote requires per-session or per-memory consent.
2. **Cost surprise.** BYOK user hits $100 overnight. Mitigation: budget caps with warn/hard-cap + trust-center visibility.
3. **Fallback loops.** Primary fails → secondary fails → retries primary. Mitigation: typed failure reasons + circuit breaker.
4. **Prompt injection via memory hit.** Memory-sourced content reaches remote model unvetted. Mitigation: compile-time sanitization + provenance-aware escalation.
5. **Latency-blind routing.** Policy picks remote when local would have been faster. Mitigation: rolling p95 latency per tier per provider feeds policy.

## Sequencing

1. **P0 (OSS Preview)** — fast + main tiers only, local Gemma 4, single optional BYOK to frontier. Basic cost display.
2. **P1 (Pro Phase 0)** — full three-tier abstraction, fallback chain, privacy-posture enforcement, trust-center routing audit.
3. **P2 (Pro Phase 1)** — cost accounting + budget caps; warn/hard-cap UX.
4. **P3 (Pro Phase 2)** — latency-aware feedback loop (rolling p95 per provider).
5. **P4 (Pro Phase 3+)** — adaptive routing based on user posture learning; Isabelle private-data protections.

## Acceptance criteria

- Every routed turn has a decision record (inputs, chosen tier, chosen provider, rationale, latency, cost).
- Zero private-memory turns reach remote providers without explicit consent event.
- BYOK cost tracking accurate to ±5% vs provider billing.
- Fallback chain completes within 2× primary budget under any single-provider outage.
- Trust center exposes every routing decision for audit.
- Privacy posture change (e.g. "local only") takes effect immediately — no in-flight remote calls continue.

## Open decisions for executing agent

- Default model per tier per performance tier (surfaces in `18_model_router_spec.md`).
- BYOK scope (which providers are first-class vs generic OpenAI-compatible endpoint).
- Budget-cap default values.

## Reference specs

- `file:///C:/Users/dbhav/Projects/aether-planning/18_model_router_spec.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/09_realtime_interaction.md`
- `file:///C:/Users/dbhav/Projects/aether-planning/14_performance_tiers_vram.md`
