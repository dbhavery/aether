# Phase 3A — Retrieval Rank-Function Calibration at Scale

**Session:** 2026-04-25 autonomous (Don asleep)
**Phase:** 3A per HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md §3A
**Branch:** `dev`
**Production code touched:** none (calibration-only)

---

## 1. TL;DR

The production retrieval rank function (cosine desc, recency tiebreak,
truncate to max_items — see `apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context`)
holds **recall@5 = 87.5%** at 842-passage scale but recall@1 falls to
**69.4%**, materially below the 95% recall@1 baseline measured on the
150-passage Block 5 harness from 2026-04-24.

Per the procedure decision logic (recall@1 < 90%), this triggers an
ADR proposal. **ADR-0010 is drafted as Proposed** sketching a
recency-weighted combine — Don ratifies on return.

Honest caveat surfaced by the miss-pattern analysis: a recency-weighted
combine is unlikely to be the right fix on its own. The misses are
within-thread-specificity failures, not recency-bias failures. The ADR
captures both possibilities and proposes the experiment.

---

## 2. Setup

| Knob | Value | Source |
| --- | --- | --- |
| Embedding model | `bge-m3` (Flame default) | ADR-0007 D7 |
| Generator model | `gemma4:e4b` | ADR-0003 |
| Threads | 60 | `gen_synthetic_corpus.py` `N_THREADS` |
| Turns / thread | 10–18 (random) | `TURNS_MIN/MAX` |
| Total turns generated | 848 | corpus jsonl |
| Total turns embedded | 842 | 6 NaN-skipped (U+FFFD payload) |
| Cross-thread reference rate | 0.20 | `CROSS_REF_RATE` |
| Ground-truth reference pairs | 72 | injected by generator |
| Bench rank function | `(score desc, ts_ms desc, truncate)` mirror | `bench_recall.py::production_rank` |
| Candidate filter | exclude same-thread rows | mimics multi-session retrieval |

The corpus is committed at `planning/session_2026-04-25/synthetic_corpus.jsonl`
(313 KB) and the embedded form at `synthetic_corpus_embedded.jsonl`
(11.4 MB — under the 50 MB gitignore threshold per the handoff).

The generator NaN-skipped 6 of 848 rows when `bge-m3` returned
`json: unsupported value: NaN` for inputs containing the U+FFFD
replacement character (gemma4:e4b's en-dash output round-tripping
through Windows cp1252 produced these). Documenting because the same
sanitization pattern (`text.replace('�', ' ')`) belongs in the
production embedding path before the next backfill iteration if the
real corpus carries any of these.

---

## 3. Results

### 3.1 At-scale recall numbers

```json
{
  "model": "bge-m3",
  "corpus_size": 842,
  "query_count": 72,
  "recall_at_1": 0.6944,
  "recall_at_3": 0.8333,
  "recall_at_5": 0.8750,
  "recall_at_10": 0.9028,
  "recall_at_20": 0.9583,
  "mrr": 0.7755,
  "mean_reciprocal_target_rank": 0.8092,
  "complete_misses": 3,
  "rank_function": "cosine_desc__then_timestamp_ms_desc__truncate(max_items)"
}
```

### 3.2 Delta vs the 150-passage Block 5 baseline (`05_long_context.json`)

| Metric | Baseline (150) | At scale (842) | Delta |
| --- | --- | --- | --- |
| recall@1 | 0.95 | 0.694 | **−25.6 pp** |
| recall@3 | 1.00 | 0.833 | −16.7 pp |
| recall@5 | 1.00 | 0.875 | −12.5 pp |
| recall@10 | 1.00 | 0.903 | −9.7 pp |
| MRR | 0.975 | 0.776 | **−20.4 pp** |

### 3.3 Decision-logic threshold

| Trigger | Threshold | Observed | Triggered? |
| --- | --- | --- | --- |
| recall@1 drops below 90% | 0.90 | 0.694 | **YES** |
| MRR drops > 5% | (0.975 − 0.05) = 0.925 | 0.776 | **YES** |

→ **ADR-0010 must be drafted (Proposed).** Done in
`docs/adr/ADR-0010-rank-function-recency-weighted-combine.md`.

---

## 4. Miss-pattern analysis (what would actually fix this?)

The handoff suggests "recency-weighted combine" as the candidate ADR.
Inspection of the 22 missed-at-1 cases tells a more nuanced story.

### 4.1 Sample miss A — wrong-thread distractors win

```
QUERY (t57_4, personal-fitness):
"Given how obsessed I was with weight reduction and specialized,
efficient gear for my backpacking trip, I'm thinking about applying
that same mindset to my weights — are there any highly optimized,
lightweight..."

EXPECTED (t59_11, backpacking-gear): "For a 25°F rating, look into
mummy-style quilts made from hydrophobic down..."

TOP-5 ACTUAL:
  rank 1: t59_0  score=0.692  (correct THREAD, wrong TURN — generic intro)
  rank 2: t59_13 score=0.676  (correct THREAD, wrong TURN — different topic)
  rank 3: t19_10 score=0.608  (different thread, off-topic)
  rank 4: t58_16 score=0.592
  rank 5: t59_16 score=0.589  (correct THREAD, wrong TURN)
```

The system is correctly identifying the right *thread* (3 of top-5 are
from t59) but the cosine similarity to the specific referenced turn
(`t59_11`) is lower than to the topic-establishing turns. Recency
tiebreak doesn't help here — none of the scores are tied.

### 4.2 Sample miss B — within-thread specificity failure

```
QUERY (t46_16, retirement-portfolio):
"Thinking back to the croissant process, where I mentioned that the
adjustments were more impactful than changing the flour, I wonder if
we should focus more on optimizing the withdrawal sequence..."

EXPECTED (t13_17, croissant-lamination): "No, the standard European
loaf flour with its high protein count should be sufficient. The
process adjustments are more impactful than a flour switch."

TOP-5 ACTUAL: top hit is t33_4 (different thread entirely — score 0.621)
```

Here the bench query carries explicit semantic anchors ("croissant
process", "adjustments more impactful than flour") that should make
this a strong cosine match, but bge-m3 dilutes the signal across
candidates. A recency-weighted combine offers no leverage on this case.

### 4.3 What the miss patterns actually suggest

1. **Within-thread top-1 confusion is the dominant failure mode.** When
   the user references a specific past turn, the rank function often
   surfaces the topic-establishing intro turn or a thematic mid-thread
   turn instead of the specific referenced turn. Recency cannot
   distinguish these.
2. **Pure-cosine ceiling at 1024d.** bge-m3 at 1024d is performing
   at-or-near its semantic-discrimination ceiling for this corpus
   profile. Re-rerank with a cross-encoder or a chunk-aware late-
   interaction model (ColBERT-style, or bge-reranker-v2) would likely
   push within-thread top-1 substantially.
3. **Recency could help for the *opposite* problem.** The synthetic
   corpus has ascending timestamps, so recency tiebreak has been firing
   monotonically by thread index. In real Aether usage, the user's
   referent is often the *most recent* mention of a topic — a recency
   *weight* (not just a tiebreak) might genuinely help when two
   semantically similar candidates compete. But this corpus does not
   prove that case; it simulates a single-pass uniform timeline.

### 4.4 Honest recommendation to Don

Rather than land a recency-weighted combine reflexively, ADR-0010 is
drafted as **Proposed with two competing options**:

- **Option A** — recency-weighted combine: `final_score = α·cosine + (1−α)·recency_decay(t)`. Cheap. Likely modest impact (5-10 pp recall@1 in the best case).
- **Option B** — re-ranker pass: top-20 from bge-m3 → cross-encoder (bge-reranker-v2-m3) re-rank → top-N. Adds ~50-100ms p50 per query but should push within-thread top-1 toward 90%+.

Recommend Don ratifies the experiment, not the implementation. A focused
session can run both options against this corpus before committing to
the change in `retrieval.rs`.

---

## 5. Reproducibility

```bash
# Generate corpus (writes synthetic_corpus.jsonl)
python planning/session_2026-04-25/gen_synthetic_corpus.py

# Embed (writes synthetic_corpus_embedded.jsonl, ~2-3 min)
python planning/session_2026-04-25/embed_corpus.py

# Bench (writes recall_at_scale.json, <30s)
python planning/session_2026-04-25/bench_recall.py
```

`gen_synthetic_corpus.py` uses fixed seed 20260425 for thread topic
selection; gemma4:e4b generation is non-deterministic so the corpus
content varies run-to-run but the structural shape (60 threads, ~850
turns, ~70 reference pairs) is stable.

---

## 6. Files

- `planning/session_2026-04-25/gen_synthetic_corpus.py` — generator
- `planning/session_2026-04-25/synthetic_corpus.jsonl` — 848 turns
- `planning/session_2026-04-25/embed_corpus.py` — embedder + sanitizer
- `planning/session_2026-04-25/synthetic_corpus_embedded.jsonl` — 842 rows × 1024d
- `planning/session_2026-04-25/bench_recall.py` — calibration bench
- `planning/session_2026-04-25/recall_at_scale.json` — measured numbers
- `docs/adr/ADR-0010-rank-function-recency-weighted-combine.md` — Proposed

---

## 7. Decision summary (logged as D-007 in DECISIONS_LOG.md)

- **Triggered the ADR threshold:** recall@1 dropped 25.6 pp below baseline at 842-passage scale.
- **Drafted ADR-0010 as Proposed** with two competing options (recency-weighted combine vs cross-encoder re-rank). Don ratifies on return.
- **Did NOT modify `retrieval.rs`** — calibration only per Phase 3A constraints.
- **Did NOT modify ADR-0007 D7 §Tuning notes** — the calibration produced an ADR, not a tuning addendum, so D7 stays as-is.

(end of report)
