"""Block 9: Backfill throughput estimation for Session B copy.

Session B (per ADR-0007 D5) ships a 'Backfill now (~estimate)' button.
The estimate comes from per-tier latency × N. This measures actual
sustained throughput under realistic conditions so the estimate copy
quotes real numbers.

Procedure:
  1. Generate 50 synthetic memory rows (varied sizes).
  2. Embed sequentially under both bge-m3 (Flame/Forge default) and
     nomic-embed-text (proposed Spark default).
  3. Measure: total wall-clock, per-row mean/p50/p95, ramp behavior
     (first 5 rows vs last 5 rows -> warmup effects).
  4. Project: 100 / 500 / 1000 row backfill ETAs at sustained rate.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

# Realistic memory rows: short conversational utterances, factual
# notes, multi-sentence reflections. 50 items, mixed lengths.
ROWS = [
    "I'm planning a trip to Iceland in October.",
    "What did I say about Iceland yesterday?",
    "The retrieval orchestrator runs embed -> query -> fetch -> rank.",
    "Cosine similarity measures the angle between two vectors.",
    "Aether is a local-first AI companion.",
    "After three failed attempts, my sourdough finally worked.",
    "The Rust borrow checker took weeks but feels intuitive now.",
    "Switching to pour-over coffee improved my morning routine.",
    "Beethoven's Moonlight Sonata first movement took six months to learn.",
    "Norway also has impressive northern lights from Tromso.",
    "Loose-leaf gyokuro tea brewed at sixty degrees produces an umami-rich cup.",
    "The Go language's goroutines and channels make concurrency feel trivial.",
    "His Montreal-style bagels turned out chewy with a honey-water boil.",
    "Learning guitar fingerpicking patterns proved harder than expected.",
    "The V60 pour-over takes only four minutes total.",
    "I want to remember to call the dentist next Tuesday.",
    "Last week's planning session covered the Q3 roadmap and dependencies.",
    "The new keyboard arrived but the spacebar feels softer than expected.",
    "I should review the Anthropic course materials before next session.",
    "The Tailscale VPN config needs updating for the new device.",
    "Today I learned that wgpu's max_buffer_size is not the same as VRAM.",
    "My favorite book this year has been The Three-Body Problem.",
    "The garden tomatoes are finally ripening after the cool spring.",
    "I prefer Pacific time zone scheduling for autonomous runs.",
    "The library budget for digital subscriptions doubled this fiscal year.",
    "Cold-brew coffee made with a 1:8 ratio steeped overnight is best.",
    "The standing desk converter improved my back posture dramatically.",
    "I should test the failover plan for the home server next weekend.",
    "Rust async traits stabilized in 1.75 and made code cleaner.",
    "The kettlebell swings hurt less when grip strength improved.",
    "Mom's birthday is on the 14th and I haven't picked a gift yet.",
    "The new espresso machine takes 12 minutes to fully warm up.",
    "I want to read the Three-Body Problem sequel this winter.",
    "The bonsai tree responded well to the indoor humidity adjustment.",
    "I should check oil and tire pressure before the road trip.",
    "Last month's grocery bill exceeded the budget by 23 percent.",
    "The new headphones cancel low frequencies very effectively.",
    "I want to try the new ramen place downtown this weekend.",
    "The vintage camera lens finally arrived after six weeks shipping.",
    "I should call my sister this weekend to catch up about her move.",
    "The deck stain dried unevenly because of the humidity spike.",
    "I learned to make pasta from scratch and the bronze die makes a difference.",
    "The garden bed needs new mulch before the first frost.",
    "I should reorder the printer ink before it runs completely dry.",
    "My niece wants a dinosaur-themed birthday party next month.",
    "The composter needs turning every three days for optimal decomposition.",
    "I should set aside time to organize the photo backup this Saturday.",
    "The bread machine recipe needs more salt by about half a teaspoon.",
    "I want to learn to identify the constellations visible in October.",
    "The bicycle chain needs lubricating before the next long ride.",
]

assert len(ROWS) == 50, f"want 50 rows, have {len(ROWS)}"


def http_post(path: str, body: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def measure_backfill(model: str) -> dict:
    print(f"=== {model}: backfill {len(ROWS)} rows ===", file=sys.stderr)
    times_ms = []
    t_start = time.perf_counter()
    for i, row in enumerate(ROWS):
        t0 = time.perf_counter()
        http_post("/api/embed", {"model": model, "input": row})
        ms = (time.perf_counter() - t0) * 1000
        times_ms.append(ms)
        if i < 3 or i >= len(ROWS) - 3:
            print(f"  row {i}: {ms:.0f} ms", file=sys.stderr)
    total_s = time.perf_counter() - t_start

    first5 = times_ms[:5]
    last5 = times_ms[-5:]
    sorted_times = sorted(times_ms)

    sustained_per_row_ms = statistics.mean(last5)
    project_100 = sustained_per_row_ms * 100 / 1000
    project_500 = sustained_per_row_ms * 500 / 1000
    project_1000 = sustained_per_row_ms * 1000 / 1000

    return {
        "model": model,
        "rows_embedded": len(ROWS),
        "total_seconds": round(total_s, 2),
        "rows_per_second": round(len(ROWS) / total_s, 2),
        "per_row_mean_ms": round(statistics.mean(times_ms), 1),
        "per_row_median_ms": round(statistics.median(times_ms), 1),
        "per_row_p95_ms": round(sorted_times[int(len(sorted_times) * 0.95)], 1),
        "per_row_min_ms": round(min(times_ms), 1),
        "per_row_max_ms": round(max(times_ms), 1),
        "first5_mean_ms": round(statistics.mean(first5), 1),
        "last5_mean_ms": round(statistics.mean(last5), 1),
        "warmup_factor": round(statistics.mean(first5) / statistics.mean(last5), 2),
        "projected_100_row_backfill_s": round(project_100, 1),
        "projected_500_row_backfill_s": round(project_500, 1),
        "projected_1000_row_backfill_s": round(project_1000, 1),
        "projected_1000_row_backfill_human": (
            f"~{round(project_1000 / 60, 1)} min" if project_1000 > 60
            else f"~{round(project_1000)} sec"
        ),
    }


def main() -> int:
    results = []
    for model in ["bge-m3", "nomic-embed-text"]:
        try:
            results.append(measure_backfill(model))
        except Exception as e:
            results.append({"model": model, "error": str(e)})
            print(f"ERROR {model}: {e}", file=sys.stderr)

    out = {"backfill_throughput": results}
    with open("planning/validation_2026-04-24/08_backfill_throughput.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
