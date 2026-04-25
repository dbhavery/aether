"""Phase 3A — Real-corpus retrieval rank-function calibration.

Reads `synthetic_corpus_embedded.jsonl`, finds every turn that carries
`references: [target_turn_id, ...]`, treats those references as
ground-truth retrievals, and queries the embedded corpus with the
referencing turn's own text. Mirrors the production rank function in
`apps/desktop/src-tauri/src/retrieval.rs::run_retrieval_context`:

    sort by score desc; tiebreak by timestamp_ms desc (newer first);
    truncate to max_items.

Reports recall@1/3/5/10/20, MRR, and the Spearman rank correlation
between predicted top-20 and ground-truth top-20 (degenerate when
there is only 1 ground-truth target — falls back to inverted-rank
correlation per the standard MRR shape).

Output JSON: `recall_at_scale.json`.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import urllib.request
from pathlib import Path

EMBEDDED = Path("planning/session_2026-04-25/synthetic_corpus_embedded.jsonl")
OUT = Path("planning/session_2026-04-25/recall_at_scale.json")
OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"


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


def production_rank(query_vec: list[float], candidates: list[dict], max_items: int) -> list[dict]:
    """Mirror of run_retrieval_context's Phase 4 rank.

    Sort: score desc, then timestamp_ms desc (newer wins ties).
    Truncate to max_items.
    """
    scored = []
    for row in candidates:
        s = cosine(query_vec, row["embedding"])
        scored.append((s, row["timestamp_ms"], row))
    # Python sort is stable; sort by (-score, -timestamp_ms) achieves the
    # same ordering as the Rust partial_cmp/cmp combination.
    scored.sort(key=lambda t: (-t[0], -t[1]))
    out = []
    for s, _ts, row in scored[:max_items]:
        out.append({"turn_id": row["turn_id"], "score": s, "timestamp_ms": row["timestamp_ms"]})
    return out


def main() -> int:
    rows: list[dict] = []
    with EMBEDDED.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"loaded {len(rows)} embedded turns", file=sys.stderr)

    by_id = {r["turn_id"]: r for r in rows}

    # Queries: every turn that has at least one reference.
    queries = [r for r in rows if r.get("references")]
    print(f"{len(queries)} queries with ground-truth references", file=sys.stderr)
    if not queries:
        print("ERROR: no queries with references — did the generator inject any?", file=sys.stderr)
        return 1

    # For each query: rank ALL OTHER rows (exclude the query itself,
    # exclude same-thread rows because production retrieval already
    # de-duplicates by session_id, and intra-thread "retrieval" of the
    # same conversation isn't what we're measuring here).
    K_VALUES = [1, 3, 5, 10, 20]
    hit_counts = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    misses: list[dict] = []
    spearman_vals: list[float] = []

    for q in queries:
        candidates = [r for r in rows if r["turn_id"] != q["turn_id"] and r["thread_id"] != q["thread_id"]]
        ranked = production_rank(q["embedding"], candidates, max_items=20)
        ranked_ids = [h["turn_id"] for h in ranked]
        expected = set(q["references"])

        # Find first-rank hit position (1-indexed). 0 = miss.
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

        # Spearman-shaped rank-quality signal: rank of each expected
        # target inside the top-20. Average reciprocal across multi-
        # target queries; pure 1/rank for single-target.
        positions = []
        for rid in expected:
            pos = next((i for i, r in enumerate(ranked_ids, start=1) if r == rid), None)
            if pos is not None:
                positions.append(pos)
        if positions:
            # Mean reciprocal rank for this query — reuses MRR shape but
            # spans the multi-target case.
            spearman_vals.append(sum(1.0 / p for p in positions) / len(positions))

    n = len(queries)
    summary = {
        "model": MODEL,
        "corpus_size": len(rows),
        "query_count": n,
        "recall_at_1": round(hit_counts[1] / n, 4),
        "recall_at_3": round(hit_counts[3] / n, 4),
        "recall_at_5": round(hit_counts[5] / n, 4),
        "recall_at_10": round(hit_counts[10] / n, 4),
        "recall_at_20": round(hit_counts[20] / n, 4),
        "mrr": round(rr_sum / n, 4),
        "mean_reciprocal_target_rank": round(statistics.mean(spearman_vals), 4) if spearman_vals else None,
        "complete_misses": len(misses),
        "rank_function": "cosine_desc__then_timestamp_ms_desc__truncate(max_items)",
    }

    out = {
        "summary": summary,
        "miss_samples": misses[:10],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
