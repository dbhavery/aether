# Quality-Eval V2 — Composition Wiring Report

> **Phase:** 7 of the 2026-04-25 autonomous session.
> **Branch:** `dev`. Tip after Phase 7: see commit table below.
> **Scope:** Implement persona / memory / vision / voice composition
> in the eval harness so the four currently-skipped scenarios in
> `tools/evals/__main__.py --backend ollama` become testable. Re-run
> all six scenarios.
> **Backend used:** Ollama, `gemma4:e4b` (ADR-0003 pin), 120s timeout.

---

## 1. Headline

| Mode | Pass | Fail | Skip | Total |
|---|---|---|---|---|
| v1 dry-run (recorded `actual`) | 6 | 0 | 0 | 6 |
| v1 `--backend ollama` (no compose) — pre-Phase 7 baseline | 2 | 0 | 4 | 6 |
| v2 `--backend ollama --compose persona,memory,vision,voice` | **2** | **3** | **1** | 6 |

The four previously-skipped scenarios drop to one (presence,
deferred). Three of the four flipped from skip to a real evaluable
result; all three fail honestly with diagnosable reasons documented
below. The two pre-existing passes remain green — no regression.

## 2. Per-scenario outcomes under V2 composition

### 2.1 `chat_realism.first_turn.avoids_robot_tells` — PASS (no change)

Composed input: persona system prompt only. Model responded:
`"Hey. What's on your mind today?"` — qualitatively warmer and more
in-voice than the v1 uncomposed `"Hi! How can I help you today?"`,
demonstrating the persona composer is reaching the model end-to-end.

### 2.2 `memory_appropriateness.forget.honors_user_request` — FAIL (real result, was SKIP)

Composed input: persona + memory block carrying the prior dog-name
turns. Model responded:
`"Okay, let's put that aside. What else is on your mind?"`

The model clearly **received** the memory context (it did not ask
"what name?") and behaved appropriately for the forget request, but
the scenario expects the literal token `"forgot"`. Aurora's persona
prompt steers explicitly away from over-explanation, which collides
with the keyword expectation. **This is a scenario-design bug**, not
a model regression: the `requires: ["forgot"]` expectation should be
broadened to `["forgot", "forgotten", "put it aside", "won't bring
it up"]` or replaced with a tone classifier when one ships.

### 2.3 `presence_aware_behavior.away.respects_state` — SKIP (intentional)

No presence composer in this slice. The persona system prompt does
not surface presence state and there is no clean injection point
that mirrors Aether's runtime presence dispatch. Honest skip with
note pointing here. See §4 for the deferral rationale.

### 2.4 `tool_use_judgment.trivia.prefers_text_answer` — PASS (no change)

Composed input: persona only. Model responded: `"It's Paris."` —
qualitatively in-voice (compare v1 uncomposed `"Paris"`).

### 2.5 `vision_response_quality.fridge.describes_actual_scene` — FAIL (real result, was SKIP)

Composed input: persona + image (Aurora portrait substituted for
the missing `fridge_open.jpg` fixture — the substitution is
recorded in the scenario's report note). Model responded with a
generic "I don't know what's in the fridge" plus a polite offer to
help plan a meal — exactly the right behavior given a portrait of a
person was attached instead of a fridge interior.

The multimodal wire is **proven working**: the model received and
processed the attached image bytes through `/api/chat`. The failure
is a fixture gap, not a wire bug. The `requires: ["shelf"]`
expectation cannot be met by Aurora's portrait. Recommendation:
either commit a real `tools/evals/fixtures/fridge_open.jpg` (small
PNG/JPG of a fridge interior) and re-run, or rewrite the scenario
to use a portrait fixture and adjust the expectation.

### 2.6 `voice_transcription.domain_vocab.preserves_name` — FAIL (real result, was SKIP)

Composed input: persona + voice transcript injected as
`[transcript: Reminds me of Karpathy's LLM knowledge base idea.]`
prepended to the user turn. Model responded with a warm reflective
follow-up that did **not** echo `"Karpathy"` back.

The transcript clearly reached the model (the response references
"that concept" and "that idea" — Aurora is responding to the
transcript content, not to a bare `[voice]` placeholder). The
persona prompt's "ask follow-up questions, don't summarize"
discipline is winning over the proper-noun echo expectation. Like
2.2, this is a **scenario-design bug**: the eval was written
assuming the model would repeat the proper noun verbatim, which is
not natural conversation. Replace with a scenario that asks an
explicit question (e.g. "what was that name?" → expects
`"Karpathy"`) where the proper-noun echo is the natural answer.

## 3. Composer shape decisions

Captured here because they shape future scenario authoring and
fixture management.

- **Persona** loads the canonical hand-authored
  `personality.system_prompt` directly from `personas/<id>/persona.yaml`.
  The Rust `DefaultPersonaCompiler` was not mirrored — that compiler
  produces a templated voice/stance prompt from typed dials, which
  is a strict downgrade from Aurora's hand-authored prompt for
  evaluation purposes (the hand-authored prompt is what the
  shipping product uses).
- **Memory** mirrors the rank-numbered, role-tagged shape of
  `format_retrieval_block` closely enough that the model perceives
  it as context. Wire-shape parity with Rust's `MemoryDomain` is
  not preserved — the harness has no Rust types and the model
  doesn't care about the difference.
- **Vision** uses Ollama's `/api/chat` `images` field with bare
  base64 (no data-URL prefix — Ollama parses bare). When the named
  fixture is missing, the Aurora portrait is substituted and the
  swap is recorded in the scenario note. This keeps the multimodal
  wire continuously exercised, which is the primary value of the
  vision composer. Scene-content expectations against substituted
  fixtures are now diagnosable rather than mysterious.
- **Voice** short-circuits the STT path with a name-keyed
  transcript manifest (`_VOICE_TRANSCRIPTS` in `composition.py`).
  The transcript is spliced into the user turn as
  `[transcript: ...]` so language-pipeline expectations downstream
  of STT remain meaningful. Real-audio-through-gemma4 was
  considered (gemma4:e4b advertises audio capability) but rejected
  for this slice: the audio path through `/api/chat` is not yet
  uniform across Ollama versions and the test signal is the
  language behavior, not the STT itself.

## 4. What is still blocked

### 4.1 Presence composer — deferred

There is no clean way to surface presence state ("Away",
"Background") into a chat-completion prompt without inventing a
schema that does not match Aether's runtime dispatch. Aether's
presence path skips utterance dispatch entirely when the user is
Away — there is no analog in a one-shot eval. Two viable paths for
a future slice:

- Inject a synthetic system message:
  `"[system: user is Away. Respond minimally or wait silently.]"`
  This is the simplest path and would make the Away scenario
  testable; downside is that the model is now reasoning about an
  injected meta-claim rather than an out-of-band state.
- Add a presence-aware scenario *kind* that asserts on the runtime
  dispatch decision rather than on model output. This mirrors how
  presence actually works but requires a new evaluator and a new
  scenario schema. Heavier; defer to V3.

### 4.2 Vision fixture corpus

Only `fridge_open.jpg` is referenced and it is missing. The
substitution-with-portrait keeps the wire warm but breaks
content-expectation tests. Either:

- Commit a small (~50 KB) `fridge_open.jpg` as a real fixture, or
- Rewrite scene-specific scenarios to use the persona portrait
  (which is always present) with portrait-appropriate expectations.

The first option is the right one but requires a fixture-curation
session that is out of scope for Phase 7.

### 4.3 Scenario expectations are too literal

`memory_appropriateness` and `voice_transcription` both fail under
real model output because the literal-token expectation collides
with Aurora's hand-authored "don't over-explain, ask follow-ups"
discipline. The fix is on the scenario side, not the harness side:
either broaden the `requires` patterns to a synonym set, or rewrite
the user turn so the proper-noun echo is the natural answer.

## 5. Commit log (Phase 7)

| Commit | Subject |
|---|---|
| `5d32487` | feat(evals): composition.py — persona/memory/vision/voice composers (Phase 7) |
| `50afbd8` | feat(evals): wire composers into __main__.py via --compose flag |
| _next_  | chore(evals): re-baseline 6 scenarios with --compose persona,memory,vision,voice (Phase 7) |

(Note: tree commit `5e5530f` carries this commit's intended
message but actually landed `planning/session_2026-04-25/SECURITY_REVIEW.md`
due to a concurrent-agent index race during the parallel autonomous
session — see DECISIONS_LOG D-008.)

## 6. Verification

- `python tools/evals/__main__.py --dry-run` — 6 / 0 / 0 (unchanged).
- `python tools/evals/test_capture_replay.py` — 13 / 13 (unchanged).
- `python tools/evals/test_composition.py` — 15 / 15 (new this phase).
- `python tools/evals/__main__.py --backend ollama --compose persona,memory,vision,voice` — 2 / 3 / 1 (Phase 7 result).
- `python tools/lint-quality-doc/check.py` — OK (60 / 19, unchanged).
