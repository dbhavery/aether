# Real-Corpus Retrieval Bench — Findings

**Date:** 2026-04-26
**Bench:** `planning/session_2026-04-26/bench_real_corpus.py`
**Output:** `planning/session_2026-04-26/real_corpus_recall.json`
**Corpus:** Lex Fridman Podcast ep 4 (Yoshua Bengio - Deep Learning),
417 Whisper segments, sourced from `nmac/lex_fridman_podcast` HF dataset.
**Model:** `bge-m3:latest` via local Ollama (FA=false).

---

## TL;DR

ADR-0011 deferral is more justified than the original handoff suggested.
Plan C ("measure on a real transcript before deciding") executed cleanly,
but produced a **negative result about the methodology, not the model**:
structural-lexical-reuse ground truth fundamentally disagrees with what
a competent semantic retriever does on real human conversation.
Whatever number we'd compute for cross-encoder rerank lift on this corpus
would be measured against an adversarial yardstick.

## Headline numbers

| Filter | Queries | recall@5 | recall@10 | recall@20 | MRR |
|---|---|---|---|---|---|
| Unigram, gap≥5, any length | 365 | 28.8% | 41.4% | 57.5% | 0.176 |
| Bigram, gap≥10, ≥12 words | 45 | 33.3% | 44.4% | 48.9% | 0.198 |

For context: random retrieval baseline at recall@5 with 416 candidates
and ~1.5 targets per query is ≈ 1.8%. **bge-m3 is ~18-28× better than
random** under either filter. The model is doing real work; the
*metric* is the problem.

## What's really happening

Inspection of complete-miss samples reveals a consistent pattern across
both runs: bge-m3 retrieves turns that are **more semantically relevant
than the "ground truth" turn**, but the ground truth insists on the
literal first occurrence of the repeated phrase.

### Example 1 — query mentions "rule based"

> "in a rule based system, you also need to disentangle the
> mechanisms that relate those"

**Ground truth wants:** earliest turn containing the bigram `(rule, based)`.

**bge-m3 retrieved (top 3):**
1. *"…rules that are disentangled from each other…"* (0.66)
2. *"…not just the variables that are disentangled from each other"* (0.64)
3. *"…factorized and separated, disentangled, then you would avoid…"* (0.61)

The retriever found three turns about rule-disentanglement — which is
exactly what the query is about. The ground truth would only credit
recall if it surfaced the literal first mention of "rule based,"
regardless of whether that earlier turn was on-topic.

### Example 2 — query mentions "relationships between"

> "the relationships between the variables, those high level semantic
> variables. They're not going"

**Ground truth wants:** earliest turn containing `(relationships, between)`.

**bge-m3 retrieved:** three turns specifically about variable
inter-dependencies and high-level representations. Topic-correct.
Penalized as a miss because none happened to contain the literal phrase.

## Why this matters for ADR-0011

The handoff's recommendation was: **"defer ADR-0011 until real-transcript
recall is measured. If recall@5 holds at >90%, defer is right. If it
craters, ADR-0011 is urgent."**

This bench reveals that recommendation can't actually be executed as
written:

1. **Real-transcript recall measurement requires real-transcript
   ground truth.** Structural-lexical-reuse — the only fully automatic
   ground-truth method available — is biased *against* good semantic
   retrieval. A model that retrieves on lexical surface alone would
   score *higher* than a model that retrieves on semantic relevance.
   That makes the metric useless for comparing rerank strategies.

2. **The synthetic-corpus +2.8pp number for the cross-encoder is an
   artifact of crisp synthetic ground truth, not a property of
   bge-m3 vs. cross-encoder behavior on real conversation.** The
   synthetic corpus *constructed* queries to have a single
   semantically-correct earlier target; real conversations have a
   distributed, ambiguous, often-multi-target relevance landscape
   where the cross-encoder may help, hurt, or be neutral — and we
   can't tell which without semantically-judged ground truth.

3. **The right path forward for ADR-0011 is downstream-task signal,
   not retrieval-recall benchmarks.** Examples:
   - Does the assistant correctly recall a specific committed fact
     when asked about it later? (Binary, dialog-derivable.)
   - Does the assistant synthesize correctly across multiple past
     turns when the user references a multi-turn thread?
   - Do users correct the assistant less often after retrieval lands?
     (Tier:changed signal already exists; correlate with retrieval
     confidence.)

   None of these require ground-truth (query, target) pairs. All
   require Aether to be in real use, which is the actual blocker.

## What this bench *is* useful for

Despite the methodology problem, the bench is keep-able as:

- A **lower-bound sanity check**: if a future embedding-model swap
  drops lexical-reuse recall@5 below ~20% on this corpus, that's a
  red flag — the new model has lost basic word-level retrieval
  ability. Useful as a regression alarm, not as a quality gate.

- A **negative-result reference**: when the next person proposes
  measuring retrieval on real corpus via lexical heuristics, this
  artifact is the receipt for "we tried; ground truth is the wall."

## Recommended ADR-0011 update

The current ADR-0010 §"Production wiring deferred" language reads
"deferred until Aether has real conversation data to measure against."
That's not strong enough — even with real conversation data, the
measurement is undefined.

Suggested replacement language for the next ADR-0011 draft:
> "Cross-encoder rerank production wiring blocked until a downstream-
> task quality signal exists that doesn't depend on (query, target)
> ground-truth pairs. Pure retrieval-recall benchmarks on real
> conversation are not informative because automatic ground-truth
> labeling (lexical reuse) systematically penalizes good semantic
> retrieval. Synthetic-corpus benchmarks are not informative because
> they construct the ground truth they then measure against."

## Files

- `bench_real_corpus.py` — bench script, parameterized by ground-truth
  filter (USE_BIGRAMS, MIN_DF, MAX_DF, MIN_GAP, MIN_QUERY_WORDS).
- `real_corpus_recall.json` — last run's structured output (currently
  the bigram/strict-filter run).
- `lexfridman.parquet` — 36 MB Lexicap dump from HF dataset
  `nmac/lex_fridman_podcast` (gitignored — see below).

## Repo hygiene

The 36 MB parquet is added to `.gitignore` — too large to commit,
re-downloadable via `curl -sL -o lexfridman.parquet https://huggingface.co/api/datasets/nmac/lex_fridman_podcast/parquet/default/train/0.parquet`
which is documented at the top of the bench script. The
`real_corpus_recall.json` IS committed — it's the artifact this
bench produces.
