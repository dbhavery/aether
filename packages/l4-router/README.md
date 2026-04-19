# @aether/l4-router

**Status:** Wave 4 stub.

L4 owns model + tool routing: 7-tier abstraction, tool dispatch, per-request L5 gating, cost-event emission, Decision-4 per-step re-evaluation.

## References

- `planning/plans/L4_model_router_system_design.md`
- `planning/plans/implementation_prep/L4_interface_pack.md`

## Wave 4 contents

- `RouterTier` (7), `ProviderId`, `ToolCall`, `ToolResult`, `ToolError`.
- `ModelRouter` + `ProviderAdapter` traits.
- `L4Error`.

## Next wave

Wave 5+ — concrete `DefaultModelRouter` with L5 evaluate per tool-call, Anthropic / OpenAI / Ollama provider adapters, `CostEvent` emission on every completion, Decision-4 re-eval engine.
