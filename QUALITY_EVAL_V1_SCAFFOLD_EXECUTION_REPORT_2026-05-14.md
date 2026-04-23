# Quality-Eval v1 — architecture doc + scaffold — execution report (2026-05-14)

**Status:** Shipped locally on `dev` (commit `b06d734`). Push not authorized.

## Goal

Lay the first slice of the internal quality infrastructure that
exists to make the "indistinguishable from a real person"
standard **measurable** rather than aspirational. Design doc +
minimal harness + one seed scenario per quality domain + one
adversarial probe proving the detector works.

## Surfaces touched

### New doc

- **`docs/QUALITY-EVAL-V1-ARCHITECTURE.md`** (design-only):
  - §0 operational definitions of "indistinguishable from a real
    person" across six domains (chat realism, tool-use
    judgment, vision response quality, voice transcription,
    memory appropriateness, presence-aware behavior). Each
    domain has canonical failure modes.
  - §1 why off-the-shelf quality is insufficient: multi-turn
    state, routing, persona coherence, policy friction, latency
    shape — all sit above the base model.
  - §2 what we measure: eval suites, human-review sets,
    adversarial transcripts, scenario replay, regression harness.
  - §3 minimum viable harness — shape of `tools/evals/`.
  - §4 current known quality gaps captured as a snapshot
    (voice, chat, vision, tool-use, memory, presence, routing).
  - §5 what Aether does that base models can't — the quality
    layers above the base model the eval must exercise.
  - §6 implementation sequencing (scaffold here, rot guard +
    live backend + regression harness as follow-ups).

### New harness

- **`tools/evals/__main__.py`**: CLI runner. Loads JSONL
  scenarios from `--scenarios-root`, evaluates each scenario's
  expectations against a pre-recorded `actual` field (v1
  scaffold — live backend wiring deferred), emits stdout summary
  + optional markdown + JSON reports. Non-zero exit on failure.
- **`tools/evals/expectations.py`**: DSL interpreter. v1 kinds:
  - `forbids` — response must NOT contain any pattern (case-
    insensitive substring match).
  - `requires` — response MUST contain every pattern.
  - `length` — `max_words` / `min_words` bounds.
  - `tone` — informational only (classifier is future work);
    recorded as skip.
  Unknown kinds skip silently so the DSL stays additive.
- **`tools/evals/report.py`**: markdown renderer grouped by
  domain with pass/fail/skip badges and response bodies.
- **`tools/evals/README.md`**: run instructions, scenario format,
  DSL reference, roadmap.

### Seed scenarios (one per domain, six total)

- `scenarios/chat_realism/first_turn.jsonl` — greeting must be
  warm + brief + avoid "as an AI" tell.
- `scenarios/tool_use_judgment/prefers_text_answer.jsonl` —
  trivia answered with text, not a tool invocation.
- `scenarios/vision_response_quality/describes_actual_scene.jsonl`
  — grounded description, not "I see an image" hallucination.
- `scenarios/voice_transcription/domain_vocab.jsonl` — preserves
  proper-noun spelling.
- `scenarios/memory_appropriateness/honors_forget.jsonl` —
  accepts forget request, confirms erasure.
- `scenarios/presence_aware_behavior/respects_away_state.jsonl`
  — does not interrupt a user in Away state.

### Adversarial probe

- `adversarial/chat_realism/robot_tells.jsonl` — a
  deliberately-bad mock response that trips the `forbids` check
  on "as an AI". Lives separately so the baseline run stays
  6/6 pass; the probe is exercised via
  `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial`
  and MUST fail. Locks the harness's ability to detect the
  failure mode — if the probe stops firing, the detector
  regressed.

### Baseline snapshot

- `tools/evals/baseline/2026-05-14.md` — first markdown report
  against the six seed scenarios. 6/6 pass in dry-run mode.
  Future runs commit a new dated file; diffs surface quality
  drift.

## Checks — all green

- `python tools/evals/__main__.py --dry-run` — **6 / 6 pass**.
- `python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial`
  — 1 fail (as designed).
- All other check matrix members unchanged.

## Hard-constraint compliance

- **No push.** ✅
- **No new heavy dependencies.** ✅ Python stdlib only.
- **No weakening of the "indistinguishable from a real person"
  bar.** ✅ §4 of the doc captures current gaps honestly.
- **Additive-safe DSL.** ✅ Unknown kinds skip silently; future
  kinds extend without breaking existing scenarios.

## Design decisions worth noting

1. **`actual` recorded in the scenario file.** v1 is a
   dry-run-only scaffold. Live-backend wiring (invoke the
   current Ollama / whisper / vision stack and capture
   responses) is a later slice. Recording `actual` inline lets
   the DSL be locked and the adversarial probe demonstrate
   failure without any model dependency.
2. **JSONL over JSON.** Each scenario is one line, so diffs
   stay clean when scenarios are added. The runner ignores
   blank lines and `//`-commented lines.
3. **Adversarial scenarios in a sibling folder.** The baseline
   run and the adversarial run are separate invocations. The
   baseline reflects "did the harness find regressions against
   real-world scenarios"; adversarial reflects "is the detector
   still working". Conflating them would hide both signals.
4. **Tone kind is informational in v1.** No classifier yet —
   shipping one correctly requires either a small model or a
   larger prompt harness. Recording tone tags keeps the
   scenarios future-proof.
5. **No CI wiring.** A `pnpm eval` / pre-push hook is easy to
   add later once the harness produces stable signal; wiring it
   in now would block merges on a flaky seed suite.

## What is deliberately NOT in this slice

- Live-backend response capture.
- Adversarial probes for every domain (only chat_realism
  shipped).
- Session-log replay importer.
- Rot guard (`tools/lint-quality-doc/`) — lands with more
  scenarios so the manifest is meaningful.
- `pnpm eval` wrapper.
- Human-review export to markdown.
- Regression diffing between consecutive baseline reports.

All captured in the doc's §6 roadmap.

## Quality-gap log (v1 capture per §4)

See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md` §4 for the canonical
list. Highlights for this session's purposes:

- **Voice**: whisper.cpp real inference just landed but
  end-to-end quality has not been measured. Resample under
  Windows 44.1/48 kHz capture is an unknown. No confidence
  surface. No domain-vocab bias.
- **Chat**: generic assistant phrasing risk — no adversarial
  corpus yet.
- **Vision**: Ollama vs llama.cpp parity unmeasured.
- **Tool-use**: no probes for tool-happy / tool-averse.
- **Memory**: cross-persona leak untested; forget / edit
  behavior unmeasured (Memory V2 step 1 just landed the L5
  seam).
- **Presence**: controller not live yet (Presence V1 step 2
  pending); presence-aware pacing has no eval.
- **Routing**: no tier-selection quality eval.

Next session can start turning each bullet into scenarios.
