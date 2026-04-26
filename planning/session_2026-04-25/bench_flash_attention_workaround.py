"""Mini-bench: re-embed the 13 Phase 3B failed rows under OLLAMA_FLASH_ATTENTION=false.

Reuses the make_row() generator from bench_backfill_stress.py to reconstruct
the exact same input strings (deterministic — pure index function).

5 attempts per row × 13 rows = 65 embed calls. ~30s wall-clock.

Output: planning/session_2026-04-25/flash_attention_workaround_results.json
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bench_backfill_stress import make_row  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"
FAILED_ROWS = [20, 70, 120, 170, 220, 270, 370, 470, 620, 670, 720, 770, 870]
ATTEMPTS_PER_ROW = 5
PACE_MS = 50
RESULTS_PATH = Path(__file__).parent / "flash_attention_workaround_results.json"


def embed(text: str) -> tuple[int, str]:
    body = json.dumps({"model": MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return (r.status, "ok")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        return (e.code, err_body[:300])
    except Exception as e:
        return (-1, str(e))


def main() -> int:
    # Warmup — load bge-m3.
    print("warmup...", file=sys.stderr)
    embed("warmup")

    results = []
    total_attempts = 0
    total_500s = 0
    for row_idx in FAILED_ROWS:
        text = make_row(row_idx)
        per_row = {"row_idx": row_idx, "text": text, "attempts": []}
        for a in range(ATTEMPTS_PER_ROW):
            t0 = time.perf_counter()
            status, err = embed(text)
            dt_ms = (time.perf_counter() - t0) * 1000
            per_row["attempts"].append(
                {"attempt": a, "status": status, "ms": round(dt_ms, 1), "err": err if status != 200 else ""}
            )
            total_attempts += 1
            if status >= 500 or status < 0:
                total_500s += 1
            print(f"  row {row_idx} attempt {a}: {status} ({dt_ms:.0f}ms)", file=sys.stderr)
            time.sleep(PACE_MS / 1000)
        results.append(per_row)

    summary = {
        "model": MODEL,
        "ollama_env": "OLLAMA_FLASH_ATTENTION=false",
        "failed_rows_tested": FAILED_ROWS,
        "attempts_per_row": ATTEMPTS_PER_ROW,
        "total_attempts": total_attempts,
        "total_failures": total_500s,
        "failure_rate_pct": round(100 * total_500s / total_attempts, 3),
        "per_row": results,
    }

    with RESULTS_PATH.open("w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps({k: v for k, v in summary.items() if k != "per_row"}, indent=2))
    print(f"\nfull results: {RESULTS_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
