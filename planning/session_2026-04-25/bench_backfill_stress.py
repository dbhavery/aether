"""Phase 3B (autonomous session 2026-04-25) — sustained backfill stress test.

Validates the ADR-0007 D7 50 ms per-row pacing-pause defense at sustained
scale. The 2026-04-24 Block 9 throughput bench measured 50 rows; D7's
"Tuning notes" projected 1000-row totals from that small sample. This run
issues 1000 real bge-m3 embed calls under the production backfill module's
exact pacing (50 ms `std::thread::sleep` between rows; see
`apps/desktop/src-tauri/src/backfill.rs::DEFAULT_PER_ROW_PAUSE_MS`).

Why Option B (this script) and not Option A (Tauri integration test):
- The full Tauri integration test would require constructing AppState
  (which Phase 4C is currently editing), seeding a Durable history via the
  in-memory store, mocking the policy engine for L5 gate Allow, and
  emitting events that exercise the spawn_blocking dispatch. That's >300
  LOC of test harness for a measurement Option B captures more cleanly:
  the backfill loop IS just `provider.embed(content) + sleep(50ms)` per
  row, and the policy gate is a one-shot at job start.
- Phase 4D's async backfill landed minutes ago; touching `apps/desktop/
  src-tauri/src/main.rs` to register Arc<AppState> for an integration test
  risks colliding with Phase 4C's parallel work in the same crate.
- Per the Phase 3B prompt: "If this is too involved, skip the live shell
  and just hammer the embed endpoint directly with the same pacing the
  backfill module uses (50ms between calls per ADR-0007 D7)."

What this measures:
- End-to-end wall-clock for 1000 real bge-m3 embeds at 50 ms pacing.
- Throughput stability — per-second and per-100-row windows.
- VRAM creep via `nvidia-smi` snapshots every ~10 s.
- Failure injection awareness — every Ollama HTTP failure is logged but
  does not abort the run (mirrors backfill module's `bump_failures`).
- Pacing-pause backoff trigger — if Ollama starts 500ing, throttle 50 ms
  → 100 ms and document.

What this does NOT measure (Option A would have):
- The L5 policy gate's actual evaluate cost.
- spawn_blocking dispatch latency.
- BackfillProgress mutex contention under live event emission.
- Real EmbeddingStore upsert latency (the FlatFile store flushes per
  upsert; this bench skips that storage write entirely).

Output:
- `planning/session_2026-04-25/backfill_stress_results.json` — full
  timeline + per-row latencies + VRAM snapshots + summary stats.
- `planning/session_2026-04-25/BACKFILL_STRESS_REPORT.md` — separate
  narrative report.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"
ROW_COUNT = 1000
PACE_MS_DEFAULT = 50  # mirror backfill::DEFAULT_PER_ROW_PAUSE_MS
PACE_MS_BACKOFF = 100  # if 500s appear, throttle here
VRAM_SNAPSHOT_EVERY_S = 10.0
RESULTS_PATH = Path("planning/session_2026-04-25/backfill_stress_results.json")

# Synthetic-but-realistic memory rows. We rotate through ~50 unique
# templates with a sequence suffix to generate 1000 distinct strings.
# Backfill embeds whatever content the durable history holds; the
# important property is variety, not source authenticity.
TEMPLATES = [
    "I'm planning a trip to {} in October.",
    "What did I say about {} yesterday?",
    "The retrieval orchestrator runs embed -> query -> fetch -> rank for {}.",
    "Cosine similarity measures the angle between two {} vectors.",
    "Aether is a local-first AI companion focused on {}.",
    "After three failed attempts, my {} finally worked.",
    "The Rust borrow checker took weeks but feels intuitive when {}.",
    "Switching to pour-over {} improved my morning routine.",
    "Beethoven's {} took six months to learn.",
    "Norway also has impressive northern lights from {}.",
    "Loose-leaf {} brewed at sixty degrees produces an umami-rich cup.",
    "The Go language's goroutines and channels make {} feel trivial.",
    "His Montreal-style {} turned out chewy with a honey-water boil.",
    "Learning guitar fingerpicking patterns proved harder than {}.",
    "The V60 pour-over takes only four minutes total for {}.",
    "I want to remember to call the {} next Tuesday.",
    "Last week's planning session covered {} and dependencies.",
    "The new keyboard arrived but the spacebar feels softer than {}.",
    "I should review the {} course materials before next session.",
    "The Tailscale VPN config needs updating for the {} device.",
    "Today I learned that wgpu's max_buffer_size is not the same as {}.",
    "My favorite book this year has been {}.",
    "The garden tomatoes are finally ripening after the {} spring.",
    "I prefer Pacific time zone scheduling for {} runs.",
    "The library budget for {} subscriptions doubled this fiscal year.",
    "Cold-brew coffee made with a 1:8 ratio steeped overnight is {}.",
    "The standing desk converter improved my {} posture dramatically.",
    "I should test the failover plan for the {} this weekend.",
    "Rust async traits stabilized in 1.75 and made {} cleaner.",
    "The kettlebell swings hurt less when {} strength improved.",
    "Mom's birthday is on the 14th and I haven't picked {} yet.",
    "The new espresso machine takes 12 minutes to fully warm up for {}.",
    "I want to read the {} sequel this winter.",
    "The bonsai tree responded well to the indoor {} adjustment.",
    "I should check oil and tire pressure before the {} trip.",
    "Last month's grocery bill exceeded the {} by 23 percent.",
    "The new headphones cancel low frequencies very effectively in {}.",
    "I want to try the new {} place downtown this weekend.",
    "The vintage camera lens finally arrived after six weeks {}.",
    "I should call my sister this weekend to catch up about {}.",
    "The deck stain dried unevenly because of the {} spike.",
    "I learned to make {} from scratch and the bronze die makes a difference.",
    "The garden bed needs new mulch before the first {}.",
    "I should reorder the printer ink before {} runs completely dry.",
    "My niece wants a {}-themed birthday party next month.",
    "The composter needs turning every three days for optimal {}.",
    "I should set aside time to organize the {} backup this Saturday.",
    "The bread machine recipe needs more {} by about half a teaspoon.",
    "I want to learn to identify the constellations visible in {}.",
    "The bicycle chain needs {} before the next long ride.",
]
FILLERS = [
    "Iceland", "memory recall", "retrieval", "embedding", "presence",
    "sourdough", "borrow checker", "coffee", "Moonlight Sonata",
    "Tromso", "gyokuro tea", "concurrency", "bagels", "expected",
    "pour-over", "dentist", "Q3 roadmap", "expected", "Anthropic",
    "new", "VRAM", "The Three-Body Problem", "cool", "autonomous",
    "digital", "best", "back", "home server", "code", "grip",
    "a gift", "espresso", "Three-Body Problem", "humidity", "road",
    "budget", "noise cancellation", "ramen", "shipping", "her move",
    "humidity", "pasta", "frost", "it", "dinosaur", "decomposition",
    "photo", "salt", "October", "lubricating",
]


def make_row(i: int) -> str:
    template = TEMPLATES[i % len(TEMPLATES)]
    filler = FILLERS[(i // len(TEMPLATES)) % len(FILLERS)]
    return f"[seq {i}] " + template.format(filler)


def http_post(path: str, body: dict, timeout: float = 60.0) -> tuple[int, dict | str]:
    """POST to Ollama. Returns (http_status, parsed_body_or_error_text).

    Mirrors the failure-tolerant shape of backfill.rs: HTTP errors are
    counted, not fatal. We still parse the body when possible so the
    caller can see Ollama's error string.
    """
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status, json.loads(r.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        return (e.code, err_body)
    except Exception as e:  # network, timeout, etc
        return (-1, str(e))


def vram_snapshot() -> dict:
    """Run nvidia-smi. Returns dict of used_mib/total_mib. -1 on failure."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        parts = out.strip().split(",")
        return {"used_mib": int(parts[0].strip()), "total_mib": int(parts[1].strip())}
    except Exception as e:
        return {"used_mib": -1, "total_mib": -1, "error": str(e)}


def warmup_model() -> None:
    """One throwaway embed so the first measured call isn't a cold-load."""
    print(f"warmup: loading {MODEL}...", file=sys.stderr)
    code, _ = http_post("/api/embed", {"model": MODEL, "input": "warmup"})
    print(f"warmup: code {code}", file=sys.stderr)


def run_stress() -> dict:
    print(
        f"=== sustained backfill stress: {ROW_COUNT} rows × {MODEL} × "
        f"{PACE_MS_DEFAULT} ms pacing ===",
        file=sys.stderr,
    )
    warmup_model()

    pace_ms = PACE_MS_DEFAULT
    pace_s = pace_ms / 1000.0
    per_row_ms: list[float] = []
    per_row_status: list[int] = []
    failures = 0
    failure_log: list[dict] = []
    vram_timeline: list[dict] = []
    pace_changes: list[dict] = []

    last_vram_at = 0.0
    t_start = time.perf_counter()

    # Initial VRAM snapshot.
    vram_timeline.append({"t_s": 0.0, "row_idx": 0, **vram_snapshot()})

    for i in range(ROW_COUNT):
        row = make_row(i)
        t0 = time.perf_counter()
        status, body = http_post("/api/embed", {"model": MODEL, "input": row})
        dt_ms = (time.perf_counter() - t0) * 1000
        per_row_ms.append(dt_ms)
        per_row_status.append(status)

        if status != 200:
            failures += 1
            failure_log.append(
                {
                    "row_idx": i,
                    "status": status,
                    "elapsed_s": round(time.perf_counter() - t_start, 2),
                    "body_excerpt": (body if isinstance(body, str) else "")[:200],
                }
            )
            # If Ollama starts 500ing, throttle. ADR-0007 D7 noted this
            # exact failure mode at row 4-5 of rapid-fire embed.
            if status >= 500 and pace_ms == PACE_MS_DEFAULT:
                pace_ms = PACE_MS_BACKOFF
                pace_s = pace_ms / 1000.0
                pace_changes.append(
                    {
                        "row_idx": i,
                        "old_pace_ms": PACE_MS_DEFAULT,
                        "new_pace_ms": PACE_MS_BACKOFF,
                        "reason": f"HTTP {status} from Ollama",
                    }
                )
                print(
                    f"  row {i}: HTTP {status} — backing off {PACE_MS_DEFAULT} → {PACE_MS_BACKOFF} ms",
                    file=sys.stderr,
                )

        # Periodic VRAM snapshot + progress print.
        elapsed = time.perf_counter() - t_start
        if elapsed - last_vram_at >= VRAM_SNAPSHOT_EVERY_S:
            snap = vram_snapshot()
            vram_timeline.append({"t_s": round(elapsed, 2), "row_idx": i, **snap})
            last_vram_at = elapsed
            recent_mean = statistics.mean(per_row_ms[-50:])
            print(
                f"  row {i+1}/{ROW_COUNT}  t={elapsed:.1f}s  "
                f"recent50_mean={recent_mean:.0f}ms  vram={snap['used_mib']}MiB",
                file=sys.stderr,
            )

        time.sleep(pace_s)

    total_s = time.perf_counter() - t_start
    # Final VRAM snapshot.
    vram_timeline.append({"t_s": round(total_s, 2), "row_idx": ROW_COUNT - 1, **vram_snapshot()})

    # Per-100-row windows for throughput-drift analysis.
    windows = []
    for w in range(0, ROW_COUNT, 100):
        chunk = per_row_ms[w : w + 100]
        if not chunk:
            continue
        windows.append(
            {
                "window_start": w,
                "window_end": w + len(chunk) - 1,
                "rows": len(chunk),
                "mean_ms": round(statistics.mean(chunk), 1),
                "median_ms": round(statistics.median(chunk), 1),
                "stddev_ms": round(statistics.pstdev(chunk), 1),
                "min_ms": round(min(chunk), 1),
                "max_ms": round(max(chunk), 1),
            }
        )

    sorted_times = sorted(per_row_ms)
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[int(len(sorted_times) * 0.99)]

    vram_used = [s["used_mib"] for s in vram_timeline if s.get("used_mib", -1) >= 0]
    vram_creep = (max(vram_used) - min(vram_used)) if vram_used else -1

    return {
        "model": MODEL,
        "row_count": ROW_COUNT,
        "pace_ms_initial": PACE_MS_DEFAULT,
        "pace_ms_final": pace_ms,
        "pace_changes": pace_changes,
        "total_seconds": round(total_s, 2),
        "total_minutes": round(total_s / 60, 2),
        "rows_per_second": round(ROW_COUNT / total_s, 3),
        "failures": failures,
        "failure_rate_pct": round(100 * failures / ROW_COUNT, 3),
        "failure_log": failure_log,
        "per_row_mean_ms": round(statistics.mean(per_row_ms), 1),
        "per_row_median_ms": round(statistics.median(per_row_ms), 1),
        "per_row_stddev_ms": round(statistics.pstdev(per_row_ms), 1),
        "per_row_p95_ms": round(p95, 1),
        "per_row_p99_ms": round(p99, 1),
        "per_row_min_ms": round(min(per_row_ms), 1),
        "per_row_max_ms": round(max(per_row_ms), 1),
        "first_100_mean_ms": round(statistics.mean(per_row_ms[:100]), 1),
        "last_100_mean_ms": round(statistics.mean(per_row_ms[-100:]), 1),
        "throughput_drift_pct": round(
            100
            * (statistics.mean(per_row_ms[-100:]) - statistics.mean(per_row_ms[:100]))
            / statistics.mean(per_row_ms[:100]),
            2,
        ),
        "windows_100": windows,
        "vram_timeline": vram_timeline,
        "vram_min_mib": min(vram_used) if vram_used else -1,
        "vram_max_mib": max(vram_used) if vram_used else -1,
        "vram_creep_mib": vram_creep,
        "per_row_status_counts": {
            str(code): per_row_status.count(code) for code in set(per_row_status)
        },
    }


def main() -> int:
    result = run_stress()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ("vram_timeline", "windows_100", "failure_log")}, indent=2))
    print(f"\nfull results: {RESULTS_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
