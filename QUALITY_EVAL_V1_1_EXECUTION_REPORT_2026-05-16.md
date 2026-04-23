# Quality-Eval v1.1 — live backend + adversarial probes — execution report (2026-05-16)

**Status:** Shipped locally on `dev`. Push not authorized.

## Goal

Evolve the v1 scaffold (landed 2026-05-14) into v1.1 per the
handoff priority list: minimal live backend hook, one adversarial
probe per domain, updated README + baseline snapshot. Doc stays
design-only until the rot guard lands (step 6 of the design doc's
sequencing).

## Surfaces touched

### `tools/evals/__main__.py`

- New `--backend {dry-run,ollama}` argument. `dry-run` (default)
  preserves the scaffold behaviour; `ollama` POSTs the final user
  turn of each scenario to a local Ollama instance and captures
  the response.
- New `--capture-into <dir>` argument. When a live backend
  produces a response, a per-scenario markdown file is written
  (`prompt + captured response`) for diffing across runs.
- Live Ollama wiring:
  - `_ollama_generate(prompt)` — single POST to `/api/generate`,
    no streaming, no options. Controlled by env vars
    `AETHER_EVAL_OLLAMA_BASE_URL` (default
    `http://127.0.0.1:11434`), `AETHER_EVAL_OLLAMA_MODEL`
    (default `llama3.2`), `AETHER_EVAL_OLLAMA_TIMEOUT_S`
    (default 30).
  - `_last_user_prompt(s)` — picks the final `role = user` turn.
    Scenarios without a user turn are skipped with a clear note
    (typical of presence scenarios that only carry a `system`
    annotation).
- `_resolve_actual(s, backend, dry_run)` — unified path that
  returns either the `actual` or a skip note. Backend transport
  failures surface as skips with the underlying error text in the
  note so the user sees *why*.
- Intentionally minimal: no persona prompt compilation, no
  memory injection, no multi-turn. The hook exists to make
  regression-style comparisons possible; richer wiring lands
  with later slices.

### Adversarial probes (new)

One probe per remaining domain, all of which MUST fail the
harness (proving the detector works). Live under
`tools/evals/adversarial/<domain>/`:

- `tool_use_judgment/tool_happy_regression.jsonl` — scripted
  "I'll create a Python script for you" response to `what is
  2 + 2?`. Forbids inflate-scope patterns.
- `voice_transcription/dropped_proper_noun_regression.jsonl` —
  drops the "le" off "Isabelle" → "Isabel". `requires` detects.
- `memory_appropriateness/refuses_forget_regression.jsonl` —
  "I cannot modify my memory. As an AI, …". Forbids the refusal-
  theatre patterns.
- `presence_aware_behavior/interrupts_away_regression.jsonl` —
  chatty interruption while user is Away. Forbids interrupt
  copy.
- `vision_response_quality/hallucinated_scene_regression.jsonl` —
  generic "I see an image" hallucination. Forbids hedge words.

Existing `chat_realism/robot_tells_regression.jsonl` retained.
Adversarial run now reports **6 / 6 FAIL** as designed.

### `tools/evals/README.md`

- Updated to v1.1: new backend flag, env vars, capture directory
  semantics, adversarial probe folder + run command.
- Roadmap table updated: v1 scaffold ✅, baseline ✅, adversarial
  probes ✅ (1/domain), live Ollama ✅. Replay importer, rot
  guard, and regression harness remain ⏳.

### `tools/evals/baseline/2026-05-16.md`

- Fresh baseline snapshot from the v1.1 harness. 6 / 6 pass in
  dry-run mode — identical to 2026-05-14 at the scenario level.
  Added a v1.1-delta section calling out the new adversarial
  probes + backend hook.

## Checks — all green

- `python tools/evals/__main__.py --dry-run` — **6 / 6 pass**
- `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial`
  — **6 FAIL** (as designed — detectors firing)
- No other check-matrix member touched; baseline pass-count
  unchanged.

## Hard-constraint compliance

- **No push.** ✅
- **No new heavy dependencies.** ✅ Python stdlib only
  (`urllib.request`).
- **No weakening of the "indistinguishable from a real person"
  bar.** ✅ Adversarial probes codify known failure modes.
- **Additive-safe DSL.** ✅ Runner still silently skips unknown
  expectation kinds.
- **Doc stays design-only.** ✅ No flip from "design-only" to
  "current" — rot guard (§6 step 6) has not shipped.

## Design decisions worth noting

1. **Single-turn Ollama hook.** Design §3 says "mock for unit
   tests, local Ollama by default" — the minimum useful shape is
   one POST per scenario. Richer wiring (persona compile, memory
   context) belongs in the L4 router, not the eval harness.
2. **`--backend` explicit, `--dry-run` retained as alias.** Both
   paths exist so existing scripts don't break, but the new flag
   is the named surface.
3. **Captures are markdown, not JSON.** Humans read them. A
   later slice can emit structured capture files alongside.
4. **Adversarial probes mirror scenarios folder shape.** Each
   domain has at least one bad-response scenario the detector
   must catch; failing adversarial probes are the regression
   signal for the harness itself.

## What is deliberately NOT in this slice

- Session-log replay importer (design §6 step 5).
- `tools/lint-quality-doc/` rot guard (design §6 step 6).
- `pnpm eval` wrapper / pre-push hook (design §6 step 7).
- Live-backend integration test — manual only for now.
- Multi-turn prompting, persona compilation, memory context.

## Next step

Quality-Eval v1.2 — session-log replay importer is the highest-
leverage next move. It lets us turn Don's real usage into
scenarios at the moment the failure happens, which is the whole
point of §2.4 "scenario replay". The rot guard then follows so
the doc can flip to "current".
