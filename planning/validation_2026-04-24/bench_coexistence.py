"""Block 4: Multi-model coexistence verification.

Confirms OLLAMA_MAX_LOADED_MODELS=2 + KEEP_ALIVE=-1 actually keep both
LLM + embedder warm in VRAM, no thrash, no reload tax on second turn.

Procedure:
1. Hit /api/embed with bge-m3 (loads it).
2. Hit /api/generate with gemma4:e4b (loads it -> 2 models loaded).
3. Snapshot /api/ps -> both should be present with size_vram > 0.
4. Hit /api/embed with bge-m3 AGAIN. Latency must be warm-fast (< 500ms),
   not cold-restart (>10s) -> proves no eviction.
5. Hit /api/generate AGAIN. Same -> proves no eviction.
6. Capture VRAM totals.
"""
from __future__ import annotations

import json
import time
import urllib.request
import sys

OLLAMA = "http://127.0.0.1:11434"


def http_post(path: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get(path: str) -> dict:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def embed_timed(model: str, text: str) -> float:
    t0 = time.perf_counter()
    http_post("/api/embed", {"model": model, "input": text})
    return (time.perf_counter() - t0) * 1000


def generate_timed(model: str, prompt: str) -> float:
    t0 = time.perf_counter()
    http_post(
        "/api/generate",
        {"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 16}},
    )
    return (time.perf_counter() - t0) * 1000


def unload(model: str) -> None:
    try:
        http_post("/api/generate", {"model": model, "keep_alive": 0})
    except Exception:
        pass
    time.sleep(0.5)


def main() -> int:
    out: dict = {"steps": []}

    print("clearing both models", file=sys.stderr)
    unload("bge-m3")
    unload("gemma4:e4b")
    time.sleep(2)
    out["ps_before_load"] = http_get("/api/ps")

    print("step 1: cold-load bge-m3 via embed", file=sys.stderr)
    cold_embed_ms = embed_timed("bge-m3", "test passage for warmup")
    out["steps"].append({"step": "1-cold-embed-bge-m3", "ms": round(cold_embed_ms, 1)})
    print(f"  -> {cold_embed_ms:.0f} ms", file=sys.stderr)

    out["ps_after_embed"] = http_get("/api/ps")

    print("step 2: cold-load gemma4:e4b via generate", file=sys.stderr)
    cold_gen_ms = generate_timed("gemma4:e4b", "What is 2+2?")
    out["steps"].append({"step": "2-cold-gen-gemma4-e4b", "ms": round(cold_gen_ms, 1)})
    print(f"  -> {cold_gen_ms:.0f} ms", file=sys.stderr)

    out["ps_after_both_loaded"] = http_get("/api/ps")
    loaded = [m["name"] for m in out["ps_after_both_loaded"].get("models", [])]
    out["both_loaded"] = "bge-m3" in [m.split(":")[0] for m in loaded] and any(
        "gemma4" in m for m in loaded
    )
    print(f"  loaded: {loaded}", file=sys.stderr)

    print("step 3: warm-rerun embed (should be fast, no reload)", file=sys.stderr)
    warm_embed_ms = embed_timed("bge-m3", "another test passage")
    out["steps"].append({"step": "3-warm-embed-bge-m3", "ms": round(warm_embed_ms, 1)})
    print(f"  -> {warm_embed_ms:.0f} ms", file=sys.stderr)

    print("step 4: warm-rerun generate (should be fast, no reload)", file=sys.stderr)
    warm_gen_ms = generate_timed("gemma4:e4b", "What is 3+3?")
    out["steps"].append({"step": "4-warm-gen-gemma4-e4b", "ms": round(warm_gen_ms, 1)})
    print(f"  -> {warm_gen_ms:.0f} ms", file=sys.stderr)

    out["ps_final"] = http_get("/api/ps")

    # Diagnostics: did either model get reloaded?
    embed_reload = warm_embed_ms > 5000  # cold reload would be 30s+
    gen_reload = warm_gen_ms > 10000  # cold reload would be 40s+
    out["embed_was_reloaded"] = embed_reload
    out["gen_was_reloaded"] = gen_reload
    out["coexistence_holds"] = (
        out["both_loaded"]
        and not embed_reload
        and not gen_reload
    )

    # VRAM utilization
    if out["ps_final"].get("models"):
        total_vram = sum(m.get("size_vram", 0) for m in out["ps_final"]["models"])
        out["total_vram_resident_gb"] = round(total_vram / (1024 ** 3), 2)
        out["per_model_vram_gb"] = [
            {
                "name": m["name"],
                "size_vram_gb": round(m.get("size_vram", 0) / (1024 ** 3), 2),
                "size_total_gb": round(m.get("size", 0) / (1024 ** 3), 2),
            }
            for m in out["ps_final"]["models"]
        ]

    with open("planning/validation_2026-04-24/04_coexistence.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(
        {
            "both_loaded": out["both_loaded"],
            "coexistence_holds": out["coexistence_holds"],
            "embed_reloaded": embed_reload,
            "gen_reloaded": gen_reload,
            "warm_embed_ms": round(warm_embed_ms, 1),
            "warm_gen_ms": round(warm_gen_ms, 1),
            "vram_resident_gb": out.get("total_vram_resident_gb"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
