"""Phase 3A — Option B bench: cross-encoder re-rank pass.

Two-stage pipeline:

  1. bge-m3 cosine retrieves top-20 from the embedded corpus
     (excluding same-thread rows, mirroring the production retrieval
     filter).
  2. BAAI/bge-reranker-v2-m3 (CrossEncoder) re-scores every
     (query_text, candidate_text) pair and re-sorts by rerank score
     desc. Recency tiebreak retained for determinism.

Measured against the same 842-passage corpus and 72 reference-pair
queries used by `bench_recall.py` (baseline) and
`bench_recall_option_a.py` (Option A). Output JSON:
`recall_at_scale_option_b.json`. Schema mirrors the others.

The rerank call routes through the persistent `hf_embed_helper`
subprocess (`tools/hf_embed_helper/embed.py`) so the model loads once
and is amortised across all 72 queries — ~10s cold load, then
~50-200ms per batch of 20 pairs.
"""
from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

EMBEDDED = Path("planning/session_2026-04-25/synthetic_corpus_embedded.jsonl")
OUT = Path("planning/session_2026-04-25/recall_at_scale_option_b.json")
HELPER = Path("tools/hf_embed_helper/embed.py")
EMBED_MODEL = "bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
TOP_N_FOR_RERANK = 20  # cosine first-pass cap


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


def cosine_top_n(query_vec: list[float], candidates: list[dict], n: int) -> list[dict]:
    """First-pass cosine retrieval — same shape as baseline production_rank."""
    scored = []
    for row in candidates:
        s = cosine(query_vec, row["embedding"])
        scored.append((s, row["timestamp_ms"], row))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [
        {"turn_id": row["turn_id"], "score": s, "timestamp_ms": row["timestamp_ms"], "text": row["text"]}
        for s, _ts, row in scored[:n]
    ]


class HelperClient:
    """Thin wrapper around the persistent hf_embed_helper subprocess.

    One process per bench run; the rerank model is loaded on the first
    `rerank` call and cached for the lifetime of the process.
    """

    def __init__(self, helper_path: Path) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(helper_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # noisy torch warnings + load logs
            text=True,
            bufsize=1,
            encoding="utf-8",
        )

    def rerank(self, model: str, query: str, candidates: list[str]) -> list[float]:
        req = {"op": "rerank", "model": model, "query": query, "candidates": candidates}
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("hf_embed_helper closed stdout unexpectedly")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(f"rerank failed: {resp}")
        return resp["scores"]

    def close(self) -> None:
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main() -> int:
    rows: list[dict] = []
    with EMBEDDED.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"loaded {len(rows)} embedded turns", file=sys.stderr)

    queries = [r for r in rows if r.get("references")]
    print(f"{len(queries)} queries with references", file=sys.stderr)
    if not queries:
        print("ERROR: no queries with references", file=sys.stderr)
        return 1

    helper = HelperClient(HELPER)
    print(f"started helper (rerank model loads on first request)", file=sys.stderr)

    K_VALUES = [1, 3, 5, 10, 20]
    hit_counts = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    misses: list[dict] = []
    spearman_vals: list[float] = []

    try:
        for q_idx, q in enumerate(queries):
            candidates = [
                r for r in rows
                if r["turn_id"] != q["turn_id"] and r["thread_id"] != q["thread_id"]
            ]
            # Stage 1: cosine top-N.
            stage1 = cosine_top_n(q["embedding"], candidates, n=TOP_N_FOR_RERANK)
            # Stage 2: cross-encoder re-rank.
            cand_texts = [c["text"] for c in stage1]
            rerank_scores = helper.rerank(RERANK_MODEL, q["text"], cand_texts)
            stage2 = [
                {
                    "turn_id": c["turn_id"],
                    "cosine": c["score"],
                    "rerank_score": rs,
                    "timestamp_ms": c["timestamp_ms"],
                }
                for c, rs in zip(stage1, rerank_scores)
            ]
            # Sort by rerank score desc, recency tiebreak.
            stage2.sort(key=lambda h: (-h["rerank_score"], -h["timestamp_ms"]))
            ranked_ids = [h["turn_id"] for h in stage2]
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
                    "top5": stage2[:5],
                })

            positions = []
            for rid in expected:
                pos = next((i for i, r in enumerate(ranked_ids, start=1) if r == rid), None)
                if pos is not None:
                    positions.append(pos)
            if positions:
                spearman_vals.append(sum(1.0 / p for p in positions) / len(positions))

            if (q_idx + 1) % 10 == 0:
                print(f"  processed {q_idx + 1}/{len(queries)} queries", file=sys.stderr)
    finally:
        helper.close()

    n = len(queries)
    summary = {
        "embed_model": EMBED_MODEL,
        "rerank_model": RERANK_MODEL,
        "variant": "option_b__cross_encoder_rerank",
        "top_n_for_rerank": TOP_N_FOR_RERANK,
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
        "rank_function": "cosine_top20__then_cross_encoder_rerank__then_timestamp_ms_desc__truncate(max_items)",
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
