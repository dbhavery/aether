# @aether/l4-router

**Status:** Wave 4 stub.

L4 owns model + tool routing: 7-tier abstraction, tool dispatch, per-request L5 gating, cost-event emission, Decision-4 per-step re-evaluation.

## References

- `ARCHITECTURE.md` — the L4 model/tool routing layer.
- `docs/LLM-PROVIDERS.md` — provider tiers and routing surface.
- `docs/adr/ADR-0003-model-defaults-supersession.md`, `docs/adr/ADR-0006-hardware-tier-model.md`.

## Wave 4 contents

- `RouterTier` (7), `ProviderId`, `ToolCall`, `ToolResult`, `ToolError`.
- `ModelRouter` + `ProviderAdapter` traits.
- `L4Error`.

## Next wave

Wave 5+ — concrete `DefaultModelRouter` with L5 evaluate per tool-call, Anthropic / OpenAI / Ollama provider adapters, `CostEvent` emission on every completion, Decision-4 re-eval engine.
