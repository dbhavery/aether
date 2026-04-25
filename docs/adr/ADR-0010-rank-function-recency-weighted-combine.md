# ADR-0010: Rank-function evolution beyond cosine + recency-tiebreak

- **Status:** **Proposed** (drafted 2026-04-25 in the autonomous Phase 3A session per `HANDOFF_2026-04-25_NEXT_AUTONOMOUS_SESSION.md` §3A trigger logic — recall@1 dropped 25.6 pp below the 150-passage baseline at 842-passage scale, crossing the 90% threshold AND the >5% MRR threshold).
- **Date:** 2026-04-25
- **Deciders:** Don ratifies. Claude proposes based on the Phase 3A calibration data in `planning/session_2026-04-25/RETRIEVAL_CALIBRATION_REPORT.md`.
- **Supersedes:** nothing (this would augment, not replace, the rank function).
- **Superseded by:** nothing yet.
- **Related:** `docs/adr/ADR-0005-retrieval-wiring.md` (defines the production rank function this ADR proposes evolving), `docs/adr/ADR-0007-embeddings-onboarding.md` D7 §Tuning notes (the embedding-side knobs already in place), `planning/session_2026-04-25/RETRIEVAL_CALIBRATION_REPORT.md` (the empirical trigger).

## Context

The production rank function in `apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context` Phase 4 is:

```rust
// Phase 4 — rank: score desc, recency desc, truncate to max_items.
resolved.sort_by(|a, b| match b.score.partial_cmp(&a.score) {
    Some(Ordering::Equal) | None => b.timestamp_ms.cmp(&a.timestamp_ms),
    Some(ord) => ord,
});
resolved.truncate(max_items);
```

That is: pure cosine descending, with `timestamp_ms` descending as a tiebreak (newer wins ties), then truncate.

This held flawlessly at the 150-passage micro-corpus from validation Block 5 (`05_long_context.json`): bge-m3 scored **recall@1 = 0.95, MRR = 0.975**.

The Phase 3A 2026-04-25 calibration ran the same rank function against an 842-passage synthetic corpus (60 conversation threads, 72 cross-thread reference pairs as ground truth). Results:

| Metric | 150-passage baseline | 842-passage at scale | Delta |
| --- | --- | --- | --- |
| recall@1 | 0.95 | 0.694 | **−25.6 pp** |
| recall@3 | 1.00 | 0.833 | −16.7 pp |
| recall@5 | 1.00 | 0.875 | −12.5 pp |
| recall@10 | 1.00 | 0.903 | −9.7 pp |
| MRR | 0.975 | 0.776 | **−20.4 pp** |

Both decision triggers in the Phase 3A procedure fired (recall@1 < 90% AND MRR drop > 5%), so this ADR is mandatory.

### Miss-pattern analysis (matters for the Decision)

Inspection of 22 missed-at-1 cases shows the dominant failure mode is **within-thread top-1 confusion**: the rank function correctly identifies the right *thread* (often 3+ of the top-5 hits come from the correct thread) but selects topic-establishing or thematic mid-thread turns instead of the specific referenced turn. Sample miss:

```
QUERY: "Given how obsessed I was with weight reduction and specialized
gear for my backpacking trip, ..." (referencing a backpacking-gear turn)

EXPECTED: t59_11 — "For a 25°F rating, look into mummy-style quilts..."

TOP-5: t59_0 (0.692), t59_13 (0.676), t19_10 (0.608), t58_16 (0.592),
       t59_16 (0.589)
```

3 of top-5 are from the right thread; the right-thread top-ranked turn is the conversation opener, not the target. This is **not a recency-bias failure**. Recency tiebreak doesn't fire here — none of the scores tie.

A second pattern: the bge-m3 cosine signal sometimes flips entirely to the wrong thread when the query's surface phrasing matches an unrelated topic better than the reference thread (sample miss B in the calibration report).

These patterns matter because they constrain which fixes are actually in scope.

## Decisions

### 1. Two competing options to evaluate; pick one before changing `retrieval.rs`.

The handoff suggested "recency-weighted combine" reflexively. The Phase 3A miss patterns show the dominant failure isn't recency — it's within-thread specificity. So the ADR proposes **two options**, recommends a focused experiment session before the change lands, and explicitly leaves the decision open.

#### Option A — Recency-weighted combine (cheap, modest expected impact)

Replace the strict-tiebreak rank with a weighted combine:

```text
final_score(row) = α · cosine(query, row) + (1 − α) · recency_decay(row.timestamp_ms, now)
```

where `recency_decay` is a half-life function (e.g. `exp(-Δt / τ)` with τ = 7 days) normalized to `[0, 1]`. Suggested starting `α = 0.85` based on the cosine vs recency signal-strength ratio in the Block 5 baseline.

Pros:
- Implementable in one PR, ~30 LOC. No new dependencies.
- Holds the existing cosine-dominant behaviour for fresh content.
- Cheap at query time (one extra arithmetic per candidate).
- Measurable: re-run `bench_recall.py` against the same corpus.

Cons:
- The Phase 3A misses are **not recency-driven**. Expected lift is modest (5-10 pp recall@1 in the best case; possibly negative if the recency component dominates).
- Adds a configuration knob (`α`, `τ`) that becomes a tier-tunable.
- Doesn't address within-thread specificity, the actual dominant failure mode.

#### Option B — Cross-encoder re-rank pass (heavier, likely substantial impact)

Keep bge-m3 as the first-pass embedder; add a cross-encoder re-rank on the top-N candidates:

```text
Phase 4 (new):
  1. cosine top-20 from bge-m3 (current behaviour, no truncate)
  2. re-rank: cross-encoder (e.g. bge-reranker-v2-m3) scores each
     (query, candidate.content) pair
  3. sort by re-rank score desc; recency tiebreak retained
  4. truncate to max_items
```

Pros:
- Cross-encoder pairwise scoring is the established remedy for within-thread specificity failures (top of MTEB reranker leaderboard for retrieval refinement).
- bge-reranker-v2-m3 is available via Ollama / HF and pairs naturally with bge-m3.
- Expected lift: within-thread top-1 likely → 90%+ based on published cross-encoder benchmarks.

Cons:
- Adds ~50-100ms p50 per query (20 cross-encoder forward passes per call).
- Requires loading a 568M-parameter model into VRAM (Flame headroom: comfortable; Spark/Ember tier: needs decision per ADR-0006 §6).
- Bigger surface area: needs an `Reranker` trait, provider plumbing, fallback when reranker unavailable.

#### Option C — Do nothing (deferred; document the decay)

Accept the recall@1 = 0.694 floor and document it as a known limitation in `docs/MEMORY-V2-ARCHITECTURE.md`. Surface the rank confidence in retrieval provenance so users can read "best guess from 3 candidates" instead of "the answer." Address with re-ranker or chunking work in a future milestone.

### 2. Recommended path: run both Option A and Option B against the calibration corpus, then commit.

`bench_recall.py` is already structured to mirror the production rank. Adding an Option-A variant is a 20-line patch; Option B requires loading the reranker model and a slightly bigger patch. A single focused 1-2 hour session can:

1. Implement Option A in the bench, measure delta.
2. Implement Option B in the bench, measure delta.
3. Compare to the Option C status-quo.
4. Pick winner, propose the production change in a follow-up ADR-0011 (or upgrade this ADR's status to Accepted with the chosen option's plumbing).

Don should ratify the *experiment*, not pre-commit to the implementation.

### 3. Reproducibility requirements for whichever option lands.

Whichever option lands in `retrieval.rs` must:

1. Add a unit test in `retrieval.rs` that locks in the new rank ordering on a small synthetic case (mirrors `rank_puts_higher_score_first_and_caps_at_max_items` already in the test module).
2. Re-run `bench_recall.py` on the canonical 842-passage corpus and check the result into `planning/session_2026-04-25/recall_at_scale_after_<option>.json`.
3. Update ADR-0007 D7 §Tuning notes with the new measured recall@1/MRR.
4. Surface a tier-tunable in `Tier` config (`α` and `τ` for Option A; on/off for Option B).

### 4. The `5s wall-clock deadline` in `retrieval.rs` constrains Option B.

ADR-0005 §Decision 5 sets a 5s bailout for the retrieval pipeline. Adding 50-100ms per query for re-rank stays comfortably under that. But if the reranker cold-loads (first call after VRAM eviction), the cold-start penalty can be ~500-1000ms. Plumbing decision: pre-warm the reranker on app startup, or accept first-call latency. Defer this decision to the implementation ADR (ADR-0011).

## Consequences

### If Option A lands:

- One arithmetic change in Phase 4 of `run_retrieval_context`.
- New tier knobs `α: f32` and `τ: Duration` with sensible Flame defaults.
- Expected modest recall@1 lift (5-10 pp); does not solve within-thread specificity.

### If Option B lands:

- New `Reranker` trait in `packages/l4-router` (or a new `packages/l2-rerank` if scoped large).
- Ollama provider plumbing for `bge-reranker-v2-m3`.
- VRAM reservation update in ADR-0006 §6 (Flame: +~600 MB; Spark: deferred).
- Phase 4 of `run_retrieval_context` calls the reranker between the existing fetch and rank steps.
- Expected substantial recall@1 lift (toward 90%+); addresses within-thread specificity directly.

### If Option C (deferred):

- Surface rank confidence in retrieval provenance UI.
- Update `docs/MEMORY-V2-ARCHITECTURE.md` with the recall@1 = 0.694 known limitation at scale.
- Reopen in a future milestone when chunking or hierarchical retrieval is in scope.

### Common to all options:

- The bench (`bench_recall.py`) becomes a permanent regression-protection asset. Re-run on every retrieval-related ADR going forward.

## Open items

1. **Does Don want to ratify the *experiment* (run both options in the bench), or pre-commit to one option now?** Recommend the former.
2. **VRAM budget for Option B's reranker.** ADR-0006 §6 currently allocates ~4 GB for Flame embedders — bge-reranker-v2-m3 is 568M params (~600 MB Q4_K_M). Fits, but takes the Flame embedder pool to ~4.6 GB.
3. **Should the calibration corpus be re-generated to be more "real"?** The current corpus is gemma4:e4b-generated synthetic. Real Aether usage may have a different surface-phrasing distribution. Future Phase 3A2 could replace with anonymized real conversation transcripts once consent + privacy story is settled.
4. **Recency-decay shape (Option A only).** Exponential half-life vs linear vs sigmoid. The choice has measurable impact on the lift; the bench experiment should sweep at least 3 shapes.
