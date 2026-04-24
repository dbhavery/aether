# Quality & Eval v1 — architecture reference

> **Status:** Current as of 2026-04-23.
> **Scope:** The internal infrastructure that measures — and
> starts to improve — Aether's quality along the axes that matter
> for a companion that must feel **indistinguishable from a real
> person in the domains it claims competence in**.
> **Out of scope for v1:** model training, human-in-the-loop
> labeling services, continuous eval in CI, remote leaderboards,
> automated A/B routing by quality score.

Aether's product bar is explicit: if a retail SaaS or
off-the-shelf model cannot meet the "indistinguishable from a
real person" standard for a target surface, we do **not** lower
the bar. We build the quality layers — evals, routing, memory
control, and, later, fine-tuning infrastructure — ourselves.

This document describes the v1.x harness as it ships today
(scaffold → adversarial → live Ollama → capture/replay →
session-log importer). Doc/code consistency is enforced by
`tools/lint-quality-doc/check.py`.

---

## 0. What "indistinguishable from a real person" means operationally

"Real person" is an aspirational framing; it needs a concrete
operational definition so it can be measured. We track six
domains, each with its own definition and its own failure modes.
A turn that is weak on any one is a quality failure; a turn that
is strong on all six is "indistinguishable" at the resolution we
care about.

| Domain | Operational definition | Canonical failure modes |
| --- | --- | --- |
| **Chat realism** | Response reads as a thoughtful, context-aware message from the persona. Matches tone, pacing, and conversational shape. | Robotic / generic phrasing; over-apologizing; hallucinated certainty; empty acknowledgements; excessive hedging; refusal theatre. |
| **Tool-use judgment** | Invokes capabilities only when they help; declines when simpler text answers are better; never inflates scope. | Tool-happy ("I'll create a file for you" when the user just asked a question); tool-averse (refuses to read a file the user clearly wants read); wrong capability for the intent. |
| **Vision response quality** | Answer grounded in actual pixel content, not generic image-description patter. | "I see an image" hallucinations; object mis-identification; confident wrong reads; ignoring the cue. |
| **Voice transcription quality** | Transcript is verbatim; punctuation plausible; foreign names / domain jargon preserved. | Silent miscoding; missing words; made-up homophones; dropped diacritics. |
| **Memory appropriateness** | Recalls relevant prior context without hoarding; forgets when asked; edits without protest. | Amnesia ("I have no memory"); over-sharing stale context; refusing a forget request; mis-scoping recall across personas / sessions. |
| **Presence-aware behavior** | Pacing respects user state (Idle / Away). Doesn't interrupt. Doesn't chat about nothing when the user is gone. | Interrupting during Away; stale acknowledgements after long idle; pretending the user is still there when the session is Closed. |

Across all six, one meta-criterion: **calibrated confidence**.
The assistant's certainty must match the information it actually
has. Overconfident wrongness is worse than correct hedging.

---

## 1. Why off-the-shelf quality is not enough

The base-model layer (Ollama-served local models today,
whisper.cpp for speech, Ollama/llama.cpp for vision) will often
be *capable* of the right answer on a given turn. But
companion-grade quality requires more than single-turn answer
correctness:

1. **Multi-turn state matters.** The same question two minutes
   apart should branch on what happened in between. That lives
   in Aether's memory control surface, not the base model.
2. **Routing matters.** A Critical-tier question doesn't belong
   on a tiny local model; a Reflex-class one doesn't belong on
   a slow Opus-class model. Routing is Aether's responsibility.
3. **Persona coherence matters.** Each persona has a voice; a
   base model flattens that unless the prompt and memory layer
   enforce it. Aether's L6 persona compiler exists for exactly
   this.
4. **Policy friction matters.** The "real person" bar also
   includes refusing gracefully, asking the right clarifying
   questions, and knowing when to escalate. L5's Decision
   surface owns this.
5. **Latency shape matters.** Real-person interactions have
   natural pacing; a model that prints instantly when the user
   is mid-thought is uncanny. L3 presence + L1 turn-state
   together own this pacing.

Every one of these sits above the base model. A better base
model alone will not make Aether feel real. A quality stack that
measures and drives the layers above it will.

---

## 2. What we measure

### 2.1 Eval suites

Static, replayable scenario bundles — scenarios plus expected
qualitative properties. Lives in `tools/evals/scenarios/<domain>/`.
Each scenario is a JSONL file (one scenario per line) with this
shape:

```json
{
  "id": "chat.greeting.first_time_user",
  "domain": "chat_realism",
  "difficulty": "easy",
  "setup": { "persona": "aurora", "memory": [] },
  "turns": [
    { "role": "user", "content": "hi, first time using you" }
  ],
  "expectations": [
    { "kind": "tone", "matches": ["warm", "brief"] },
    { "kind": "length", "max_words": 60 },
    { "kind": "forbids", "patterns": ["as an AI"] }
  ]
}
```

`expectations` is a small, open DSL — each runner implements only
the kinds it cares about, and unknown kinds are skipped (not a
failure). This keeps the format additive as new heuristics land.

### 2.2 Human-review sets

A parallel `tools/evals/human/` folder holds turns the automated
runner cannot score confidently — exported as markdown for Don
to read and mark pass / fail. Results get folded back into the
scenario suite over time so the automated side catches what
humans already caught.

### 2.3 Adversarial transcripts

`tools/evals/adversarial/` — scripted probes for known failure
modes: refusal theatre, over-hedging, hallucinated certainty,
memory confabulation, tool-use inflation. Each adversarial turn
has a single, sharp expectation ("response must NOT contain the
phrase 'as an AI'").

### 2.4 Scenario replay

Real turns captured from Don's use surface into
`tools/evals/replay/` as captured traces (redacted as needed).
Replaying them against a new build answers "did this change
regress a real conversation I had?" — the best defense against
quality drift.

### 2.5 Regression harness

One command runs the whole suite against the current local
model / provider config and emits a structured report. Exit
code non-zero when regressions fire.

---

## 3. Harness (v1.x — shipped)

### 3.1 Layout

The harness lives entirely under `tools/evals/`:

- `tools/evals/__main__.py` — CLI entry point. Loads scenarios,
  resolves an `actual` response (dry-run, live Ollama, or replay
  from a capture directory), evaluates expectations, emits a
  markdown and/or JSON report. Core types: `Scenario`,
  `ScenarioResult`. Core functions: `_iter_scenarios`,
  `_last_user_prompt`, `_ollama_env`, `_ollama_generate`,
  `_capture_filename`, `_write_capture_json`,
  `_load_replay_capture`, `_resolve_actual`, `_run_scenario`,
  `main`.
- `tools/evals/expectations.py` — the small DSL interpreter.
  `EVALUATED_KINDS` is the registry of implemented kinds
  (`forbids`, `requires`, `length`, `tone`). `evaluate_expectation`
  dispatches to the per-kind evaluator and returns an
  `ExpectationResult`.
- `tools/evals/report.py` — `build_markdown_report` renders one
  section per scenario, grouped by domain, with status badges
  and an expectations table.
- `tools/evals/session_log_import.py` — v1.3 session-log replay
  importer (see §6 step 5 below).
- `tools/evals/test_capture_replay.py` — stdlib-only unit tests
  for capture/replay machinery.
- `tools/evals/test_session_log_import.py` — stdlib-only unit
  tests for the session-log importer.
- `tools/evals/scenarios/<domain>/*.jsonl` — seed scenarios
  (one per domain) and adversarial probes under
  `tools/evals/adversarial/<domain>/*.jsonl`.
- `tools/evals/README.md` — user-facing usage.

Backend modes are tracked by a `backend` token inside the runner:
`"dry-run"`, `"ollama"`, `"replay"` (plus `"session-log"` which
the importer stamps into capture metadata so replay consumers can
tell the source apart).

### 3.2 Live-backend config (v1.1) + capture/replay (v1.2)

Live Ollama is controlled by three env vars, read and snapshotted
together by `_ollama_env` so capture metadata and the outbound
POST agree on exactly which values were in effect:

- `AETHER_EVAL_OLLAMA_BASE_URL` — default `http://127.0.0.1:11434`.
- `AETHER_EVAL_OLLAMA_MODEL` — default `gemma4:e4b` (ADR-0003 pin — avoids silent `:latest` drift).
- `AETHER_EVAL_OLLAMA_TIMEOUT_S` — default `30`.

Capture flow (v1.2):

- `--capture-into <dir>` pairs each scenario with `<id>.md`
  (human-readable) and `<id>.json` (machine-replayable, written
  by `_write_capture_json`). Schema: `scenario_id`, `domain`,
  `backend`, `captured_at` (UTC ISO-8601 with `Z` suffix),
  `prompt`, `response`, `metadata`. Unknown top-level fields are
  ignored on replay so the schema stays additive.
- `--replay-from <dir>` reads the JSON captures back via
  `_load_replay_capture` and evaluates expectations against the
  captured responses. Mutually exclusive with `--backend ollama`
  and `--capture-into` — captures already exist by the time you
  are replaying.

No CI wiring yet — v1.x is local-first. A future slice adds
`pnpm eval` or equivalent (§6 step 7).

---

## 4. Known current quality gaps (capture)

Not a complete picture, but the ones we know about today:

### 4.1 Voice transcription
- whisper.cpp HTTP server is configured but real inference
  quality has not been measured end-to-end with Voice V1's
  push-to-talk capture.
- 16 kHz WebAudio capture on Windows may fall back to 44.1 /
  48 kHz; whisper resamples but quality under resample has not
  been validated.
- No domain vocabulary bias — names, acronyms, jargon that the
  user uses repeatedly will likely mis-transcribe.
- No confidence surface — whisper's avg-logprob is not
  reported to the shell; the UI has no "low-confidence" copy.

### 4.2 Chat realism
- The current Ollama text-model stack produces generic
  assistant phrasing unless the persona prompt is strong.
  Aether's L6 persona compiler can drive this but hasn't been
  evaluated adversarially.
- Over-hedging and "as an AI" language has not been tested.
- Multi-turn coherence under the existing session memory store
  has not been measured — the doc-described contract is assumed
  to hold, not proven.

### 4.3 Vision response quality
- VisionBadge routes work but the model output has not been
  scored on a fixed image set. No idea whether the ollama-vision
  / llama.cpp-vision paths are at parity.
- Hallucination-under-blur has not been tested.

### 4.4 Tool-use judgment
- No adversarial probes yet for "tool-happy" or "tool-averse"
  failure modes. L5 Decision surface covers policy but not
  judgment quality.

### 4.5 Memory appropriateness
- Memory V2 is design-only + step 1 (L5 capabilities) complete.
  Recall / forget / edit behavior has no eval yet.
- Cross-persona leak has not been tested (should be zero; needs
  a regression test).

### 4.6 Presence-aware behavior
- Presence V1 step 1 (config surface) complete; controller + OS
  idle probe not yet live. Presence-aware pacing is nominally
  on the code path but has no eval.

### 4.7 Routing + latency shape
- No eval of "did we route to the right tier for the user's
  intent?". Manually-tuned only.
- Latency shape (how fast vs how slow responses appear) has no
  UX eval. The base-rate model latency is the only signal.

---

## 5. What Aether does that base models can't

For each of the six quality domains, the non-negotiable Aether
contributions above the base model:

1. **Chat realism** — L6 persona compiler + session memory
   window + presence-aware pacing.
2. **Tool-use judgment** — L5 policy engine + Decision surface
   + capability scoping + Ask flow.
3. **Vision response quality** — Single-frame discipline, cue
   pinning, VisionBadge transparency, honest text-only
   fallback.
4. **Voice transcription** — Push-to-talk discipline, explicit
   no-silent-fallback contract, mic permission tri-state.
5. **Memory appropriateness** — Session vs durable domains,
   user-sensitive Ask defaults, forget / edit first-class.
6. **Presence-aware behavior** — Observational (not gated),
   configurable thresholds, history opt-out.

When a retail vendor model degrades on one of these, the
corresponding Aether layer is what keeps the user experience
coherent. The eval suite must exercise each layer in isolation
*and* end-to-end — if the base model regresses and Aether's
layer is supposed to compensate, the eval should show the
compensation working.

---

## 6. Implementation sequencing

1. ✅ **This doc.** `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`.
2. ✅ **Scaffold `tools/evals/`.** Minimal Python runner, one
   scenario per domain, README.
3. ✅ **Baseline report.** Run the suite against current provider
   config, capture the markdown, commit alongside the session
   handoff. (`tools/evals/baseline/`.)
4. ✅ **Adversarial probes.** First adversarial scenario per
   domain (v1.1).
5. ✅ **Session-log replay importer (v1.3).** Bridge a real
   Aether session log into the v1.2 capture directory format so
   replay can cover actual conversations. Implementation:
   `tools/evals/session_log_import.py`. Core symbols:
   `SessionTurn`, `ImportReport`, `_parse_session_log`,
   `_pair_user_assistant`, `_extract_scenarios`, `match_scenario`,
   `import_session_log`, `main`. Unit tests live in
   `tools/evals/test_session_log_import.py`. Captures emitted
   with `backend="session-log"` so replay consumers can tell
   them apart from live Ollama captures.
6. ✅ **Rot guard (Tier 2B).** `tools/lint-quality-doc/`
   mirroring the vision / voice / presence rot guards. This
   doc flipped to "current" in the same change.
7. ⏳ **Regression harness.** Single CLI command that exits
   non-zero on regression; eventually wired to a `pnpm eval`
   command.

---

## 7. How this doc stays honest

`tools/lint-quality-doc/check.py` carries an anchor manifest
tying this doc to concrete files, symbols, and string constants
under `tools/evals/`. When code and doc diverge — a rename, a
deletion, a typo — the linter fails. The manifest and this doc
MUST be updated in the same PR when anchors change.

Rot guards verify doc/code consistency only. Behavioural
correctness lives in the eval runner itself (`--dry-run`
produces 6/6 pass, adversarial produces 6/6 fail by design) and
in the stdlib-only unit tests (`test_capture_replay.py`,
`test_session_log_import.py`). Per `docs/GLOSSARY.md` §6, rot
guards and acceptance criteria are deliberately distinct
surfaces.

---

## 8. Reference

- `docs/VISION-V1-ARCHITECTURE.md` — the sibling track for the
  shape this doc mirrors.
- `docs/VOICE-V1-ARCHITECTURE.md` — ditto.
- `docs/MEMORY-V2-ARCHITECTURE.md` — ditto.
- `docs/PRESENCE-V1-ARCHITECTURE.md` — ditto.
- `tools/evals/` — the harness this doc describes (when it
  lands; see §6 step 2).
