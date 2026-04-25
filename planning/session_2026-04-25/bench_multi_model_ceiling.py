"""Phase 3C: Multi-model VRAM coexistence ceiling test.

Maps the realistic ceiling on a 24 GB RTX 3090 Ti by progressively
loading models and snapshotting VRAM + /api/ps after each load.

Procedure:
  1. Pre-flight: clear, snapshot baseline VRAM + ps.
  2. Load gemma4:e4b (generator)        keep_alive=30m
  3. Load bge-m3 (embedder)             keep_alive=30m
  4. Load nomic-embed-text (embedder)   keep_alive=30m
  5. Load gemma4:26b (large generator)  keep_alive=30m  -- watch for eviction
  6. If 5 coexists, attempt qwen3:1.7b as 5th model.
  7. Cleanup: keep_alive=0 for all.

Eviction is detected by comparing the post-load /api/ps model set
against the previously-loaded set: any prior model now missing was
evicted to make room.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
OUT_PATH = Path("planning/session_2026-04-25/multi_model_ceiling.json")
VRAM_TOTAL_MB = 24564
ABORT_VRAM_MB = 23000  # safety: don't push past 23 GB used


def http_post(path: str, body: dict, timeout: float = 300.0) -> dict:
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


def nvidia_smi_used_mb() -> int:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        text=True,
    )
    return int(out.strip().splitlines()[0])


def models_resident() -> list[dict]:
    ps = http_get("/api/ps")
    return [
        {
            "name": m["name"],
            "size_vram_mb": round(m.get("size_vram", 0) / (1024 * 1024)),
        }
        for m in ps.get("models", [])
    ]


def unload(model: str) -> None:
    try:
        http_post("/api/generate", {"model": model, "keep_alive": 0}, timeout=30)
    except Exception:
        pass


def snapshot(step: int, action: str, prior_resident: set[str]) -> dict:
    time.sleep(1.5)  # allow ollama to settle ps state
    resident = models_resident()
    resident_names = {m["name"] for m in resident}
    evicted = sorted(prior_resident - resident_names)
    vram_mb = nvidia_smi_used_mb()
    sum_vram_mb = sum(m["size_vram_mb"] for m in resident)
    return {
        "step": step,
        "action": action,
        "vram_used_mb_nvidia_smi": vram_mb,
        "vram_used_mb_ps_sum": sum_vram_mb,
        "models_resident": resident,
        "eviction": evicted or None,
    }


def load_generator(model: str, keep_alive: str = "30m") -> dict | None:
    try:
        return http_post(
            "/api/generate",
            {
                "model": model,
                "prompt": "hello",
                "stream": False,
                "keep_alive": keep_alive,
                "options": {"num_predict": 4},
            },
            timeout=300,
        )
    except Exception as e:
        return {"error": str(e)}


def load_embedder(model: str, keep_alive: str = "30m") -> dict | None:
    try:
        return http_post(
            "/api/embed",
            {"model": model, "input": "hello", "keep_alive": keep_alive},
            timeout=300,
        )
    except Exception as e:
        return {"error": str(e)}


def main() -> int:
    out: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "gpu": "RTX 3090 Ti",
            "vram_total_mb": VRAM_TOTAL_MB,
        },
        "ollama_version": http_get("/api/version").get("version"),
        "events": [],
    }

    # Pre-flight cleanup of any models from prior runs.
    for m in ("gemma4:e4b", "bge-m3", "nomic-embed-text", "gemma4:26b", "qwen3:1.7b"):
        unload(m)
    time.sleep(2)

    out["events"].append(snapshot(0, "baseline (no models loaded)", set()))
    print(f"[0] baseline vram={out['events'][-1]['vram_used_mb_nvidia_smi']} MB", file=sys.stderr)

    plan = [
        ("load gemma4:e4b", "gen", "gemma4:e4b"),
        ("load bge-m3", "embed", "bge-m3"),
        ("load nomic-embed-text", "embed", "nomic-embed-text"),
        ("load qwen3:1.7b (4th small-model probe)", "gen", "qwen3:1.7b"),
        ("load gemma4:26b (large-model coexistence probe)", "gen", "gemma4:26b"),
    ]

    for step_idx, (action, kind, model) in enumerate(plan, start=1):
        prior = {m["name"] for m in models_resident()}
        prior_vram = nvidia_smi_used_mb()
        if prior_vram >= ABORT_VRAM_MB:
            out["events"].append({
                "step": step_idx,
                "action": f"ABORT BEFORE {action}",
                "reason": f"vram pressure {prior_vram} MB >= {ABORT_VRAM_MB} MB threshold",
            })
            print(f"[{step_idx}] aborting; vram={prior_vram}", file=sys.stderr)
            break

        print(f"[{step_idx}] {action} (prior vram={prior_vram} MB)", file=sys.stderr)
        t0 = time.perf_counter()
        result = load_generator(model) if kind == "gen" else load_embedder(model)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)

        snap = snapshot(step_idx, action, prior)
        snap["load_elapsed_ms"] = elapsed_ms
        if isinstance(result, dict) and result.get("error"):
            snap["load_error"] = result["error"]
            print(f"  -> ERROR: {result['error']}", file=sys.stderr)
        else:
            print(
                f"  -> ok in {elapsed_ms} ms, "
                f"vram_now={snap['vram_used_mb_nvidia_smi']} MB, "
                f"resident={[m['name'] for m in snap['models_resident']]}",
                file=sys.stderr,
            )
            if snap["eviction"]:
                print(f"  !! EVICTION: {snap['eviction']}", file=sys.stderr)
        out["events"].append(snap)

        if isinstance(result, dict) and result.get("error"):
            # Hard load failure (likely OOM). Stop the climb.
            break

    # Findings synthesis
    no_eviction_events = [
        e for e in out["events"]
        if e.get("step", 0) > 0
        and not e.get("eviction")
        and not e.get("load_error")
        and "models_resident" in e
    ]
    first_eviction = next(
        (e for e in out["events"] if e.get("eviction")),
        None,
    )
    peak_vram = max(
        (e.get("vram_used_mb_nvidia_smi", 0) for e in out["events"]),
        default=0,
    )
    baseline_vram = out["events"][0].get("vram_used_mb_nvidia_smi", 0)

    out["ceiling_findings"] = {
        "max_models_no_eviction": (
            max((len(e["models_resident"]) for e in no_eviction_events), default=0)
        ),
        "ceiling_vram_mb": peak_vram,
        "first_eviction_at_step": first_eviction["step"] if first_eviction else None,
        "evicted_model": first_eviction["eviction"] if first_eviction else None,
        "baseline_vram_mb": baseline_vram,
        "headroom_above_baseline_mb": peak_vram - baseline_vram,
        "headroom_remaining_mb": VRAM_TOTAL_MB - peak_vram,
    }

    # Cleanup
    print("cleanup: unloading all", file=sys.stderr)
    for m in ("gemma4:e4b", "bge-m3", "nomic-embed-text", "gemma4:26b", "qwen3:1.7b"):
        unload(m)
    time.sleep(2)
    out["post_cleanup_resident"] = models_resident()
    out["post_cleanup_vram_mb"] = nvidia_smi_used_mb()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["ceiling_findings"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
