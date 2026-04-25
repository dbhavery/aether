"""ADR-0007 D7 latency table validation harness.

Measures cold-start + warm latency for embedding + LLM models against a
running Ollama daemon. Outputs JSON for the validation report.

Usage:
    python bench_latency.py [--out PATH]

Heavy-usage protocol: model loads + real embed/generate calls. Caller
is responsible for env (`OLLAMA_KEEP_ALIVE=-1` etc.) and not running
in parallel with other GPU work.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
import urllib.error

OLLAMA = "http://127.0.0.1:11434"

EMBED_MODELS = ["bge-m3", "nomic-embed-text"]
LLM_MODELS = ["gemma4:e4b"]
SAMPLE_TEXTS = [
    "I'm planning a trip to Iceland in October to see the northern lights.",
    "What did I say about Iceland?",
    "Aether is a local-first AI companion.",
    "Cosine similarity measures the angle between two vectors.",
    "The retrieval orchestrator runs embed -> query -> fetch -> rank.",
]


def http_post(path: str, body: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get(path: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def unload_model(model: str) -> None:
    """Force-unload a model so the next call is a true cold start."""
    try:
        http_post("/api/generate", {"model": model, "keep_alive": 0}, timeout=30)
    except Exception:
        pass  # generate on an embedding model errors but still unloads
    # Verify unloaded via /api/ps
    time.sleep(1.0)


def measure_embed(model: str, text: str) -> tuple[float, int]:
    t0 = time.perf_counter()
    resp = http_post("/api/embed", {"model": model, "input": text}, timeout=120)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    dim = len(resp["embeddings"][0]) if "embeddings" in resp else 0
    return elapsed_ms, dim


def measure_generate_first_token(model: str, prompt: str) -> tuple[float, float, int]:
    """Returns (full_response_ms, first_chunk_ms, response_token_count)."""
    body = {"model": model, "prompt": prompt, "stream": True, "options": {"num_predict": 64}}
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    first_ms = None
    tok_count = 0
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r:
            if first_ms is None:
                first_ms = (time.perf_counter() - t0) * 1000
            try:
                chunk = json.loads(line.decode("utf-8"))
                if "response" in chunk:
                    tok_count += 1
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue
    full_ms = (time.perf_counter() - t0) * 1000
    return full_ms, first_ms or full_ms, tok_count


def bench_embed_model(model: str) -> dict:
    """Cold-start + N warm runs for an embedding model."""
    print(f"  -> unloading {model}", file=sys.stderr)
    unload_model(model)
    print(f"  -> COLD start: {model}", file=sys.stderr)
    cold_ms, dim = measure_embed(model, SAMPLE_TEXTS[0])
    print(f"     cold: {cold_ms:.0f} ms, dim={dim}", file=sys.stderr)
    warm_runs = []
    for i, text in enumerate(SAMPLE_TEXTS):
        ms, _ = measure_embed(model, text)
        warm_runs.append(ms)
        print(f"     warm[{i}]: {ms:.0f} ms", file=sys.stderr)
    return {
        "model": model,
        "cold_start_ms": round(cold_ms, 1),
        "dim": dim,
        "warm_runs_ms": [round(x, 1) for x in warm_runs],
        "warm_p50_ms": round(statistics.median(warm_runs), 1),
        "warm_mean_ms": round(statistics.mean(warm_runs), 1),
        "warm_min_ms": round(min(warm_runs), 1),
        "warm_max_ms": round(max(warm_runs), 1),
    }


def bench_llm_model(model: str) -> dict:
    """Cold-start + N warm runs for an LLM model. Time-to-first-token + full response."""
    print(f"  -> unloading {model}", file=sys.stderr)
    unload_model(model)
    print(f"  -> COLD start: {model}", file=sys.stderr)
    cold_full, cold_first, cold_tok = measure_generate_first_token(model, "What is 2+2?")
    print(f"     cold: full={cold_full:.0f}ms first={cold_first:.0f}ms tokens={cold_tok}", file=sys.stderr)
    warm_runs = []
    for i, text in enumerate(SAMPLE_TEXTS):
        full, first, tok = measure_generate_first_token(model, text)
        warm_runs.append({"full_ms": full, "first_ms": first, "tokens": tok})
        print(f"     warm[{i}]: full={full:.0f}ms first={first:.0f}ms tokens={tok}", file=sys.stderr)
    full_runs = [r["full_ms"] for r in warm_runs]
    first_runs = [r["first_ms"] for r in warm_runs]
    return {
        "model": model,
        "cold_start_full_ms": round(cold_full, 1),
        "cold_start_first_token_ms": round(cold_first, 1),
        "cold_start_tokens": cold_tok,
        "warm_runs": [
            {"full_ms": round(r["full_ms"], 1), "first_ms": round(r["first_ms"], 1), "tokens": r["tokens"]}
            for r in warm_runs
        ],
        "warm_full_p50_ms": round(statistics.median(full_runs), 1),
        "warm_first_p50_ms": round(statistics.median(first_runs), 1),
        "warm_full_mean_ms": round(statistics.mean(full_runs), 1),
    }


def get_ollama_ps() -> dict:
    return http_get("/api/ps")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="planning/validation_2026-04-24/02_latency_table.json")
    args = p.parse_args()

    results = {
        "ollama_version": http_get("/api/version").get("version", "unknown"),
        "models_pulled": [m["name"] for m in http_get("/api/tags").get("models", [])],
        "ps_initial": get_ollama_ps(),
        "embed_results": [],
        "llm_results": [],
    }

    print("=== EMBED MODELS ===", file=sys.stderr)
    for model in EMBED_MODELS:
        try:
            results["embed_results"].append(bench_embed_model(model))
        except Exception as e:
            results["embed_results"].append({"model": model, "error": str(e)})
            print(f"  ERROR {model}: {e}", file=sys.stderr)

    print("=== LLM MODELS ===", file=sys.stderr)
    for model in LLM_MODELS:
        try:
            results["llm_results"].append(bench_llm_model(model))
        except Exception as e:
            results["llm_results"].append({"model": model, "error": str(e)})
            print(f"  ERROR {model}: {e}", file=sys.stderr)

    results["ps_final"] = get_ollama_ps()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
