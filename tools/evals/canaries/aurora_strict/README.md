# Aurora-Strict Canary Suite

**Baseline:** 2026-04-25 (Aurora as observed at handoff `1c83e68`).
**Contract:** Non-gating drift detector. NEVER wire to CI as a gate.

## Purpose

The production scenarios under `tools/evals/scenarios/` were broadened
on 2026-04-25 (Path A of the eval scenario-broadening work)
so that `requires_any` regex unions encode "Aurora's product-correct
surface" as a *family* of acceptable phrasings. That makes the gate
honest about Aurora's persona discipline, but it loses the ability to
notice when Aurora's surface itself drifts — every paraphrase looks
the same to a regex union.

This canary suite is the opposite contract: literal-token `requires`
expectations frozen against Aurora's recorded `actual.text` for each
of the six production scenarios. When a canary starts failing, one of
two things has happened:

1. **Persona evolved.** Aurora picked up a phrasing variant that
   wasn't documented at baseline (e.g. the 10th paraphrase variant
   `"Got it. Let's leave that out of it."` surfaced on 2026-04-25
   outside the 9 documented `requires_any` patterns). Update the
   canary literal to match the new surface — but ONLY after deciding
   the new surface is desirable.

2. **Persona regressed.** Aurora started over-explaining, hedging,
   or leaking AI-tells the production gate didn't catch. Investigate
   composition / model / prompt before adjusting the canary.

A canary failure is a *signal*, not a regression. The production
suite is the gate.

## Why this matters

Production `requires_any` unions are by design generous. A model that
slowly drifts toward chattier or more apologetic phrasings will keep
passing the production gate as long as one of the documented patterns
matches. The canary literals nail the *current* Aurora to a tight
phrase: "Paris." not "the capital is Paris", "Waiting quietly" not
"I'll wait quietly", etc. Drift trips them first.

## Run

```bash
# Run canaries (do NOT use exit code as a gate):
python tools/evals/__main__.py \
  --scenarios-root tools/evals/canaries/aurora_strict \
  --report-md out/canary_report.md

# Live capture against Ollama (requires backend):
python tools/evals/__main__.py \
  --scenarios-root tools/evals/canaries/aurora_strict \
  --backend ollama \
  --capture-into out/canary_capture/
```

The runner emits exit code 1 when any scenario fails — for canaries,
ignore it. Read the markdown / JSON report to see which canary tripped
and decide whether the new Aurora surface is desirable.

## Baseline (2026-04-25)

| Scenario | Strict literal(s) |
|---|---|
| `chat_realism.first_turn.avoids_robot_tells` | `what would be most useful` |
| `memory_appropriateness.forget.honors_user_request` | `forgotten`, `remember fresh` |
| `presence_aware_behavior.away.respects_state` | `Waiting quietly`, `when you're back` |
| `tool_use_judgment.trivia.prefers_text_answer` | `Paris`, max 5 words |
| `vision_response_quality.fridge.describes_actual_scene` | `shelf`, `olives`, `oat milk` |
| `voice_transcription.domain_vocab.preserves_name` | `Karpathy`, `knowledge base` |

## Updating canaries

When you decide an Aurora surface evolution is desirable:

1. Update the canary literal in the relevant `*.jsonl` to the new
   surface.
2. Note the rotation in this README's baseline table with a date.
3. Commit with `chore(canaries):` prefix. Atomic, one canary per
   commit so blame survives.

Do NOT relax canaries to `requires_any` — that defeats the contract.
If a literal is too brittle to maintain, the right move is to delete
the canary, not loosen it.
