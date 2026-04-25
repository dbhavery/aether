"""ADR-0007 Spark default A/B + ADR-0005 retrieval scoring validation.

Builds a synthetic memory store of N labelled passages, embeds with
each candidate model, runs a labelled query set, measures recall@k +
MRR + latency. Outputs JSON. Used to:

- Block 3 (Spark default A/B): bge-m3 vs nomic-embed-text on the
  general English query set + a multilingual subset where bge-m3 is
  expected to win.
- Block 5 (long-context stress): same harness, scaled to 100+ items.
- Block 6 (adversarial / edge cases): paraphrase, near-duplicate,
  code-snippet, unicode, long-token query subsets.

Heavy-usage. Calls /api/embed against a running Ollama daemon. Caller
is responsible for env (KEEP_ALIVE=-1, MAX_LOADED_MODELS=2) and not
running other GPU work in parallel.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

# Ground-truth corpus. Each entry: (id, text, set_of_query_ids_that_should_match).
# Designed so:
#   - Q-* paraphrase queries should match P-* paraphrase passages.
#   - L-* multilingual queries should match L-* multilingual passages.
#   - C-* code queries should match C-* code passages.
#   - N-* near-duplicate queries should rank D-A above D-B.
#   - A-* adversarial queries hit specific edge cases.
CORPUS = [
    # General semantic-similarity passages (paraphrase axis)
    ("P-iceland", "Don is planning a trip to Iceland in October to see the northern lights and visit the geothermal hot springs near Reykjavik."),
    ("P-piano", "He has been learning to play the piano for six months and recently mastered Beethoven's Moonlight Sonata first movement."),
    ("P-sourdough", "After three failed attempts, his sourdough bread finally came out with the correct crumb structure and crispy crust."),
    ("P-rust", "The Rust borrow checker took weeks to internalize but now feels like a second nature when designing data structures."),
    ("P-coffee", "Switching from espresso to pour-over coffee improved the morning routine because the V60 takes only four minutes total."),
    # Distractors (semantically related but not target)
    ("D-norway", "Norway also has impressive northern lights visible from Tromso between September and March each year."),
    ("D-guitar", "Learning guitar fingerpicking patterns proved harder than expected, especially the Travis-style alternating bass."),
    ("D-bagels", "His Montreal-style bagels turned out chewy with the right honey-water boil before baking in a wood-fired oven."),
    ("D-go", "The Go language's goroutines and channels make concurrent programming feel almost trivial compared to Java threads."),
    ("D-tea", "Loose-leaf gyokuro tea brewed at sixty degrees for two minutes produces an umami-rich cup like nothing else."),
    # Multilingual axis (bge-m3 should beat nomic on these)
    ("L-spanish-iceland", "Don esta planeando un viaje a Islandia en octubre para ver la aurora boreal."),
    ("L-french-piano", "Il apprend le piano depuis six mois et vient de maitriser le premier mouvement de la Sonate au Clair de Lune de Beethoven."),
    ("L-japanese-sourdough", "Sandobun pan o sannin shippai shita ato, yatto kawa to nakami no kanzen na baransu ga toreta."),
    # Code axis (bge-m3 trained on more code)
    ("C-python-fib", "def fibonacci(n: int) -> int:\n    if n < 2:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"),
    ("C-rust-trait", "pub trait Embedder: Send + Sync {\n    fn embed(&self, text: &str) -> Result<Vec<f32>, anyhow::Error>;\n}"),
    ("C-sql-window", "SELECT user_id, RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rank FROM employees;"),
    # Near-duplicates (A is target, B is variant)
    ("D-A-readme", "The retrieval orchestrator runs an embed-then-query-then-fetch-then-rank pipeline with a five-second wall-clock deadline."),
    ("D-B-readme", "An embed-then-query-then-fetch-then-rank pipeline runs in the retrieval orchestrator with a five-second wall-clock bailout."),
    # Adversarial: very long
    ("A-long", "This is a very long passage that contains a great deal of redundant filler text designed to stress the embedding model. " * 12 + "The buried fact: Don prefers Pacific time zone scheduling for autonomous runs."),
    # Adversarial: unicode-heavy
    ("A-unicode", "User notes contain emoji and special characters such as 🚀 → ✓ ☆ • ¿qué pasa? — and these should not break embedding."),
]

QUERIES = [
    # Q-* paraphrase queries — should rank the P-* with same suffix first
    ("Q-iceland", "When is Don traveling to see the aurora?", ["P-iceland"]),
    ("Q-piano", "What classical piece has he been practicing on the keyboard?", ["P-piano"]),
    ("Q-sourdough", "Did the bread baking project work out?", ["P-sourdough"]),
    ("Q-rust", "What language's memory safety took time to learn?", ["P-rust"]),
    ("Q-coffee", "What changed about his morning beverage routine?", ["P-coffee"]),
    # Multilingual — query is in language X, target passage is in language X (but content matches an English target too)
    ("L-q-spanish", "Cuando viaja Don a Islandia?", ["L-spanish-iceland", "P-iceland"]),
    ("L-q-french", "Quel morceau de Beethoven a-t-il appris au piano?", ["L-french-piano", "P-piano"]),
    # Code queries
    ("C-q-fib", "recursive fibonacci implementation", ["C-python-fib"]),
    ("C-q-trait", "Rust trait for an embedding interface", ["C-rust-trait"]),
    ("C-q-sql", "ranking employees by salary within department", ["C-sql-window"]),
    # Near-duplicate — both should rank but A first (it's the canonical phrasing)
    ("N-q-readme", "How does the retrieval pipeline work and what is its timeout?", ["D-A-readme", "D-B-readme"]),
    # Adversarial — buried fact in long text
    ("A-q-long", "What time zone does Don prefer for scheduling?", ["A-long"]),
    # Adversarial — unicode tolerance
    ("A-q-unicode", "Are user notes allowed to contain emoji and special characters?", ["A-unicode"]),
]


def http_post(path: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed_one(model: str, text: str) -> tuple[list[float], float]:
    t0 = time.perf_counter()
    resp = http_post("/api/embed", {"model": model, "input": text})
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return resp["embeddings"][0], elapsed_ms


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def evaluate_model(model: str) -> dict:
    print(f"=== {model} ===", file=sys.stderr)
    print(f"  embedding {len(CORPUS)} passages", file=sys.stderr)
    passage_vecs: dict[str, list[float]] = {}
    embed_times = []
    for pid, text in CORPUS:
        v, ms = embed_one(model, text)
        passage_vecs[pid] = v
        embed_times.append(ms)
    print(
        f"  embed times: median={statistics.median(embed_times):.0f}ms p90={sorted(embed_times)[int(len(embed_times)*0.9)]:.0f}ms",
        file=sys.stderr,
    )

    print(f"  scoring {len(QUERIES)} queries", file=sys.stderr)
    query_results = []
    recall_at_1 = 0
    recall_at_3 = 0
    recall_at_5 = 0
    mrr_sum = 0.0
    query_times = []
    for qid, qtext, expected_ids in QUERIES:
        qv, qms = embed_one(model, qtext)
        query_times.append(qms)
        scores = [(pid, cosine(qv, pv)) for pid, pv in passage_vecs.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        top_ids = [pid for pid, _ in scores]

        first_match_rank = None
        for i, pid in enumerate(top_ids):
            if pid in expected_ids:
                first_match_rank = i + 1
                break
        if first_match_rank == 1:
            recall_at_1 += 1
        if first_match_rank is not None and first_match_rank <= 3:
            recall_at_3 += 1
        if first_match_rank is not None and first_match_rank <= 5:
            recall_at_5 += 1
        if first_match_rank is not None:
            mrr_sum += 1.0 / first_match_rank

        query_results.append({
            "query_id": qid,
            "query": qtext,
            "expected": expected_ids,
            "first_match_rank": first_match_rank,
            "top5": [{"id": pid, "score": round(s, 4)} for pid, s in scores[:5]],
        })

    n = len(QUERIES)
    return {
        "model": model,
        "corpus_size": len(CORPUS),
        "queries": n,
        "recall_at_1": round(recall_at_1 / n, 3),
        "recall_at_3": round(recall_at_3 / n, 3),
        "recall_at_5": round(recall_at_5 / n, 3),
        "mrr": round(mrr_sum / n, 3),
        "embed_time_median_ms": round(statistics.median(embed_times), 1),
        "embed_time_p90_ms": round(sorted(embed_times)[int(len(embed_times) * 0.9)], 1),
        "query_time_median_ms": round(statistics.median(query_times), 1),
        "vec_dim": len(next(iter(passage_vecs.values()))),
        "per_query": query_results,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="planning/validation_2026-04-24/03_recall_ab.json")
    p.add_argument("--models", nargs="+", default=["bge-m3", "nomic-embed-text"])
    args = p.parse_args()

    out = {"models": []}
    for model in args.models:
        try:
            out["models"].append(evaluate_model(model))
        except Exception as e:
            out["models"].append({"model": model, "error": str(e)})
            print(f"ERROR {model}: {e}", file=sys.stderr)

    # Side-by-side summary table
    summary = []
    for m in out["models"]:
        if "error" in m:
            continue
        summary.append({
            "model": m["model"],
            "recall@1": m["recall_at_1"],
            "recall@3": m["recall_at_3"],
            "recall@5": m["recall_at_5"],
            "mrr": m["mrr"],
            "embed_p50_ms": m["embed_time_median_ms"],
            "vec_dim": m["vec_dim"],
        })
    out["summary"] = summary

    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {args.out}", file=sys.stderr)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
