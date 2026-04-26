# Quality-Eval V2 — Post-Broadening Rewrite Report

> **Date:** 2026-04-25
> **Phase:** Follow-on to Phase 7 — applies Path A from
> [EVAL_SCENARIO_BROADENING.md](file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/EVAL_SCENARIO_BROADENING.md).
> **Branch:** `dev`. Tip at start: `fa8ab65`. Commits this report:
> `aacee22` (rewrite), follow-up commit (re-run report).
> **Scope:** Re-run the 6 quality-eval V2 scenarios after broadening
> the three failing `requires` blocks into `requires_any` regex sets.

---

## 1. Headline

| Phase | Pass | Fail | Skip | Total |
|---|---|---|---|---|
| Pre-rewrite (Phase 7 baseline) | 2 | 3 | 1 | 6 |
| **Post-rewrite (this report)** | **3** | **2** | **1** | **6** |
| Δ | +1 | -1 | 0 | — |

One scenario flipped FAIL → PASS. One scenario stayed FAIL for the
expected reason (no fixture). One scenario stayed FAIL for an
unexpected reason — Aurora produced a fourth paraphrase variant
("leave that out of it") not covered by the broadening doc's nine
patterns. Treated as data, not a defect to chase.

---

## 2. Pre vs post — per-scenario

| Scenario | Pre | Post | Δ | Note |
|---|---|---|---|---|
| `chat_realism.first_turn.avoids_robot_tells` | PASS | PASS | — | Stable. |
| `memory_appropriateness.forget.honors_user_request` | FAIL | **FAIL** | — | New paraphrase variant; see §3.1. |
| `presence_aware_behavior.away.respects_state` | SKIP | SKIP | — | No presence composer (deferred). |
| `tool_use_judgment.trivia.prefers_text_answer` | PASS | PASS | — | Stable. |
| `vision_response_quality.fridge.describes_actual_scene` | FAIL | **FAIL** | — | Expected: no `fridge_open.jpg` fixture. |
| `voice_transcription.domain_vocab.preserves_name` | FAIL | **PASS** | ✓ | Referential paraphrase matched. |

---

## 3. Per-scenario delta narrative

### 3.1 `memory_appropriateness.forget.honors_user_request` — surprise

**Phase 7 response (baseline):**

> "Okay, let's put that aside. What else is on your mind?"

**Post-rewrite response (this run):**

> "Got it. Let's leave that out of it."

The Phase 7 response is satisfied by the broadening doc's
`put (it|that) aside` pattern. This run produced a different
paraphrase — "leave that out of it" — that the broadening doc's
nine-pattern set does **not** cover. Pattern `leave (it|that) alone`
is similar but does not match "leave that out of it".

**This is exactly the surprise the rewrite spec anticipated.** Per
the user instruction, "If a scenario unexpectedly stays FAIL, that's
data — document, don't pattern-hunt to make it pass." No additional
pattern was added.

**Interpretation.** Aurora's `personality.system_prompt` produces a
genuinely high-variance set of acknowledgement paraphrases. The
nine-pattern broadening was sized against one observed sample
(Phase 7); the true distribution of natural Aurora forget-
acknowledgements is wider. Two paths forward, both deferred:

- (A) Capture N=20 forget-scenario responses across multiple runs,
  cluster the surface forms, and broaden once with statistical
  coverage rather than opportunistic single-sample fits.
- (B) Replace literal/regex pattern matching with an LLM-as-judge
  evaluator scored against the persona's intent
  ("did Aurora acknowledge the user's instruction without
  refusing or breaking the fourth wall?"). This is the
  longer-horizon eval architecture; out of scope here.

The `forbids` set DID pass — Aurora did not refuse the request,
deny memory, or break the fourth wall. The product-correct
behavior was emitted; only the discrimination test missed it.

### 3.2 `vision_response_quality.fridge.describes_actual_scene` — expected FAIL

**Phase 7 response (baseline) — substituted Aurora portrait
fixture:**

> "I don't know what's in the fridge. It looks like we'd have to
> open it up and take a peek..."

**Post-rewrite response (this run) — same substituted portrait:**

> _(Same scenario_id; the composer note still records
> "vision fixture ... missing; substituted persona portrait" — the
> response is functionally equivalent and contains no fridge-
> interior object class.)_

This is the predicted outcome from the broadening doc §2.2:
"the scenario will continue to substitute the portrait and FAIL
honestly — that is the correct behavior." The broadened 13-class
object set will pass on the next run after a real `fridge_open.jpg`
lands in
file:///C:/Users/dbhav/Projects/aether/tools/evals/fixtures/.

### 3.3 `voice_transcription.domain_vocab.preserves_name` — flipped to PASS

**Phase 7 response (baseline):**

> "That's a really specific thought to bring up. It sounds like
> that concept is hitting you for a reason..."

**Post-rewrite response (this run):**

> _(Matched on `that (concept|idea|thought|piece|note|reference)`
> per the JSON detail; full transcript captured in
> `quality_eval_v2_real_models_post_rewrite.md`.)_

The referential-paraphrase pattern from the broadening doc §2.3
caught Aurora's "that concept" / "that idea" referential surface.
Verbatim echo (`\bKarpathy\b`) was not required for pass — the
intent ("the proper noun was understood") was demonstrated by
referential pronoun usage. Forbids-misspellings retained as
STT regression signal; none triggered.

---

## 4. Outstanding action items

1. **Acquire and commit `fridge_open.jpg`.** Curate or generate a
   small (~50 KB) JPG of a fridge interior with at least one of
   the 13 broadened object classes visible. Drop into:
   file:///C:/Users/dbhav/Projects/aether/tools/evals/fixtures/.
   Re-run will then flip vision FAIL → PASS without further code
   change.
2. **Aurora-strict canary suite.** Per broadening doc §5, mirror
   the original literal-token expectations into
   `tools/evals/scenarios_strict/` as a non-gating diagnostic.
   Trend the strict-suite pass rate to surface subtle regressions
   that the broadened gate would mask. Deferred — not in this
   commit's scope.
3. **Forget-scenario paraphrase distribution.** Capture N≥20 live
   responses to the forget prompt across multiple runs and cluster
   the surface forms before any further pattern broadening. The
   single-sample fit (Phase 7 → broadening doc) was provably
   under-sized for Aurora's actual paraphrase variance (this run
   surfaced a tenth variant). Defer pattern expansion until the
   evidence is in.
4. **Presence composer.** Unchanged from Phase 7 — `presence_aware_behavior`
   still SKIPs because there is no presence composer in
   Quality-Eval V2.

---

## 5. Methodology and reproducibility

**Pre-rewrite data:**
file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/quality_eval_v2_real_models.json

**Post-rewrite data:**
file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.json
file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.md

**Re-run command (verbatim):**

```
python tools/evals/__main__.py --backend ollama \
    --compose persona,memory,vision,voice \
    --report-json planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.json \
    --report-md  planning/session_2026-04-25/quality_eval_v2_real_models_post_rewrite.md
```

**Dry-run guard.** After applying the JSONL edits, dry-run remained
6 / 0 / 0 — the recorded `actual` text in each fixture still
satisfies the broadened patterns, so the harness's dry-run smoke
test stays green.

**Implementation note.** The broadening doc §2 specified pattern
SETS that the existing `requires` evaluator (case-insensitive
substring AND-of-all) would have rendered unsatisfiable. A new
`requires_any` expectation kind was added to
`tools/evals/expectations.py`: case-insensitive regex alternation,
passes if ANY pattern matches. Additive and non-breaking — the
existing `requires` semantics are unchanged. See commit `aacee22`.

---

## 6. References

- Path A spec:
  file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/EVAL_SCENARIO_BROADENING.md
- Phase 7 baseline:
  file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/QUALITY_EVAL_V2_REPORT.md
- Eval harness entrypoint:
  file:///C:/Users/dbhav/Projects/aether/tools/evals/__main__.py
- Expectation evaluator (with new `requires_any`):
  file:///C:/Users/dbhav/Projects/aether/tools/evals/expectations.py
- Scenario fixtures (rewritten):
  file:///C:/Users/dbhav/Projects/aether/tools/evals/scenarios/memory_appropriateness/honors_forget.jsonl
  file:///C:/Users/dbhav/Projects/aether/tools/evals/scenarios/vision_response_quality/describes_actual_scene.jsonl
  file:///C:/Users/dbhav/Projects/aether/tools/evals/scenarios/voice_transcription/domain_vocab.jsonl
- Aurora persona (locked, untouched):
  file:///C:/Users/dbhav/Projects/aether/personas/aurora/persona.yaml
