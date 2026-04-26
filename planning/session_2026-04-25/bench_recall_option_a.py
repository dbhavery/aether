"""Phase 3A — Option A bench: recency-weighted combine.

Mirrors `apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context`
Phase 4 with the ADR-0010 Option A combined score:

    final_score = cosine + α * recency_decay(ts)
    recency_decay(ts) = exp(-(now - ts) / τ)  clamped to [0, 1]

with α = RECENCY_WEIGHT_ALPHA = 0.1 and τ = 7 days, matching the Rust
constants. Sort by final_score desc, with raw timestamp_ms desc as the
deterministic tiebreak (vanishingly rare in f32).

`now` is the maximum timestamp observed in the corpus. The synthetic
corpus uses ascending timestamps starting 2026-11-14 and spans ~14 days,
so this pins "now" at the end of the corpus and lets recency decay over
the corpus interior — exactly what Option A is designed to exploit.

Output JSON: `recall_at_scale_option_a.json`. Schema mirrors
`recall_at_scale.json`.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

EMBEDDED = Path("planning/session_2026-04-25/synthetic_corpus_embedded.jsonl")
OUT = Path("planning/session_2026-04-25/recall_at_scale_option_a.json")
MODEL = "bge-m3"

# Mirror retrieval.rs constants byte-for-byte.
RECENCY_WEIGHT_ALPHA = 0.1
RECENCY_HALF_LIFE_MS = 7 * 24 * 60 * 60 * 1000  # 7 days in ms


def cosine(a: list[float], b: list[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def recency_decay(row_ts_ms: int, now_ms: int) -> float:
    """Mirror of retrieval.rs::recency_decay."""
    if row_ts_ms >= now_ms:
        return 1.0
    delta = now_ms - row_ts_ms
    if RECENCY_HALF_LIFE_MS <= 0:
        return 0.0
    return math.exp(-delta / RECENCY_HALF_LIFE_MS)


def option_a_rank(
    query_vec: list[float],
    candidates: list[dict],
    now_ms: int,
    max_items: int,
) -> list[dict]:
    """Mirror of run_retrieval_context Phase 4 under ADR-0010 Option A."""
    scored = []
    for row in candidates:
        cos = cosine(query_vec, row["embedding"])
        rec = recency_decay(row["timestamp_ms"], now_ms)
        combined = cos + RECENCY_WEIGHT_ALPHA * rec
        scored.append((combined, row["timestamp_ms"], cos, row))
    # Sort by combined desc, then ts desc (deterministic tiebreak).
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [
        {
            "turn_id": row["turn_id"],
            "score": cos,
            "combined_score": combined,
            "timestamp_ms": row["timestamp_ms"],
        }
        for combined, _ts, cos, row in scored[:max_items]
    ]


def main() -> int:
    rows: list[dict] = []
    with EMBEDDED.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"loaded {len(rows)} embedded turns", file=sys.stderr)

    by_id = {r["turn_id"]: r for r in rows}
    now_ms = max(r["timestamp_ms"] for r in rows)
    print(f"now_ms (max corpus timestamp) = {now_ms}", file=sys.stderr)

    queries = [r for r in rows if r.get("references")]
    print(f"{len(queries)} queries with references", file=sys.stderr)
    if not queries:
        print("ERROR: no queries with references", file=sys.stderr)
        return 1

    K_VALUES = [1, 3, 5, 10, 20]
    hit_counts = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    misses: list[dict] = []
    spearman_vals: list[float] = []

    for q in queries:
        candidates = [
            r for r in rows
            if r["turn_id"] != q["turn_id"] and r["thread_id"] != q["thread_id"]
        ]
        ranked = option_a_rank(q["embedding"], candidates, now_ms, max_items=20)
        ranked_ids = [h["turn_id"] for h in ranked]
        expected = set(q["references"])

        first_pos = 0
        for i, rid in enumerate(ranked_ids, start=1):
            if rid in expected:
                first_pos = i
                break
        for k in K_VALUES:
            if 0 < first_pos <= k:
                hit_counts[k] += 1
        if first_pos > 0:
            rr_sum += 1.0 / first_pos
        else:
            misses.append({
                "query_turn_id": q["turn_id"],
                "expected": list(expected),
                "top5": ranked[:5],
            })

        positions = []
        for rid in expected:
            pos = next((i for i, r in enumerate(ranked_ids, start=1) if r == rid), None)
            if pos is not None:
                positions.append(pos)
        if positions:
            spearman_vals.append(sum(1.0 / p for p in positions) / len(positions))

    n = len(queries)
    summary = {
        "model": MODEL,
        "variant": "option_a__recency_weighted_combine",
        "alpha": RECENCY_WEIGHT_ALPHA,
        "half_life_days": 7,
        "corpus_size": len(rows),
        "query_count": n,
        "now_ms": now_ms,
        "recall_at_1": round(hit_counts[1] / n, 4),
        "recall_at_3": round(hit_counts[3] / n, 4),
        "recall_at_5": round(hit_counts[5] / n, 4),
        "recall_at_10": round(hit_counts[10] / n, 4),
        "recall_at_20": round(hit_counts[20] / n, 4),
        "mrr": round(rr_sum / n, 4),
        "mean_reciprocal_target_rank": round(statistics.mean(spearman_vals), 4) if spearman_vals else None,
        "complete_misses": len(misses),
        "rank_function": "cosine + alpha*exp(-dt/tau)__then_timestamp_ms_desc__truncate(max_items)",
    }

    out = {"summary": summary, "miss_samples": misses[:10]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
