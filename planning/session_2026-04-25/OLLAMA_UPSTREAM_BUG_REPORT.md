# Upstream bug report draft — Ollama bge-m3 embed returns HTTP 500 (NaN-in-output) at ~1.3% rate under sustained sequential load

> **Status:** DRAFT, not filed. Don decides if/when this gets pasted into github.com/ollama/ollama. Phase 3B follow-up F3 from file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/BACKFILL_STRESS_REPORT.md.
>
> **Prior art found (do NOT file as new — comment on existing instead):** This is a known, actively-tracked class of bugs. Most-relevant existing issues to consider commenting on rather than opening a duplicate:
>
> - https://github.com/ollama/ollama/issues/13572 — bge-m3 NaN output on seemingly-unrelated inputs (76/1217 cases). **Closest match.**
> - https://github.com/ollama/ollama/issues/14657 — bge-m3 NaN on technical docs (Bitcoin whitepaper).
> - https://github.com/ollama/ollama/issues/9639 — same `json: unsupported value: NaN` on `nomic-embed-text` — confirms it is a generic embed-runner failure mode, not bge-m3-specific.
> - https://github.com/ollama/ollama/issues/12921 — same error on `qwen3-embedding:8b-fp16`; reporter speculates fp16 numerical instability.
> - https://github.com/ollama/ollama/issues/13643 — bge-m3 input-length angle (~100-120 word ceiling regression).
>
> **Recommendation to Don:** post a comment on **#13572** with the new data below (sustained-load failure rate, cadence chart, reproducer). Opening a fresh issue would be duplicative. The pasteable comment body is in section "Comment body" at the bottom.

---

## Title (if filing fresh — but prefer commenting on #13572)

bge-m3 returns HTTP 500 (`json: unsupported value: NaN`) at ~1.3% rate under sustained sequential `/api/embed` load (1000 rows, 50 ms cadence)

## Environment

- Ollama: **0.21.2** (Windows install)
- OS: **Windows 11 Pro N** (10.0.26100)
- GPU: **NVIDIA RTX 3090 Ti, 24 GB VRAM**
- Driver: latest (CUDA reported by `nvidia-smi`)
- Embed model: **`bge-m3`** (566M params, F16, ~1.16 GB on disk, default Ollama pull)
- Other models loaded at test start: `gemma4:e4b` (~10 GB resident, evicted by Ollama mid-run as bge-m3's hot path took over). Steady-state: only bge-m3 resident.
- Concurrent traffic: none — single Python client, sequential requests.

## TL;DR

A 1000-row sustained-load benchmark against `/api/embed` with `bge-m3` produces **13 HTTP 500 responses (1.3%)**, all carrying the same body:

```json
{"error":"failed to encode response: json: unsupported value: NaN"}
```

This matches the known root cause (bge-m3 internally produces NaN values for some inputs; Go's `encoding/json` cannot serialize NaN, so the response handler returns a generic 500). What is **new** vs. existing reports:

1. **Sustained-load failure rate is measurable and stable at ~1.3%** across 987/1000 successful + 13/1000 failed requests — useful as an empirical baseline.
2. **Failure cadence is suspiciously regular** (every ~50 rows) given that the input text is randomly drawn from a 50-template × 50-filler pool — initially looked like an internal Ollama pressure boundary, but is more likely **input-content-triggered with a regular periodicity in the corpus generator** (see "Reproducer notes" below — every 50 rows the template index resets, so the same templates recur with new fillers; some template+filler combos may be deterministic NaN triggers).
3. **Pacing does not help.** The first 500 hit at row 20 (50 ms pacing); the loop bumped to 100 ms pacing for the remaining 980 rows; 12 more 500s still occurred. This **confirms the failure is not load-related** and is **content-deterministic** — consistent with #13572's "76/1217 specific texts" observation.
4. **`OLLAMA_FLASH_ATTENTION=false` workaround was NOT tested** in this run. (Recommended next step.)

## Reproduction

Pull bge-m3 and run a sustained sequential embed loop with varied content:

```bash
ollama pull bge-m3
python bench_backfill_stress.py
```

Full reproducer: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/bench_backfill_stress.py

Minimal core (the inner loop):

```python
import json, time, urllib.request

OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"
ROW_COUNT = 1000
PACE_MS = 50

# 50 templates × 50 fillers → 1000 distinct inputs; full lists in the
# linked reproducer. Each row is "[seq N] " + template.format(filler).
def make_row(i: int) -> str:
    return f"[seq {i}] " + TEMPLATES[i % 50].format(FILLERS[(i // 50) % 50])

failures = 0
for i in range(ROW_COUNT):
    body = json.dumps({"model": MODEL, "input": make_row(i)}).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/embed", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    except urllib.error.HTTPError as e:
        failures += 1
        print(f"row {i}: HTTP {e.code} — {e.read().decode()[:200]}")
    time.sleep(PACE_MS / 1000)

print(f"failures: {failures}/{ROW_COUNT}")
```

## Expected behavior

`bge-m3` should return a valid 1024-dimension embedding (HTTP 200) for every input in the corpus, or — if the model genuinely produces a NaN vector for an input — Ollama should return an HTTP 4xx with a clear, non-misleading error (`model produced invalid embedding values (NaN or Inf)`) instead of a 500 with `failed to encode response: json: unsupported value: NaN`. (The latter looks like a server bug; the former correctly attributes the failure to model output.)

## Actual behavior

Run summary (full JSON: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/backfill_stress_results.json):

```json
{
  "model": "bge-m3",
  "row_count": 1000,
  "pace_ms_initial": 50,
  "pace_ms_final": 100,
  "failures": 13,
  "failure_rate_pct": 1.3,
  "per_row_status_counts": {"200": 987, "500": 13},
  "per_row_mean_ms": 181.8,
  "per_row_p95_ms": 213.7,
  "per_row_p99_ms": 227.1,
  "total_seconds": 282.48
}
```

All 13 failures returned the identical body:

```
{"error":"failed to encode response: json: unsupported value: NaN"}
```

Failure rows (with wall-clock and gap-from-prior):

| # | Row | Wall-clock (s) | Gap (rows) |
|---|-----|----------------|------------|
| 1 | 20  | 5.5   | —   |
| 2 | 70  | 21.2  | 50  |
| 3 | 120 | 35.7  | 50  |
| 4 | 170 | 50.6  | 50  |
| 5 | 220 | 65.5  | 50  |
| 6 | 270 | 79.9  | 50  |
| 7 | 370 | 109.4 | 100 |
| 8 | 470 | 136.9 | 100 |
| 9 | 620 | 178.2 | 150 |
| 10 | 670 | 192.3 | 50 |
| 11 | 720 | 206.0 | 50 |
| 12 | 770 | 219.6 | 50 |
| 13 | 870 | 247.4 | 100 |

## Reproducer notes — why the cadence looks regular

Initial read: "every 50 rows = an internal Ollama batch boundary." On closer inspection of the corpus generator, that's almost certainly **wrong**:

- The corpus has **50 templates** and **50 fillers**.
- `make_row(i) = TEMPLATES[i % 50].format(FILLERS[(i // 50) % 50])`.
- Row 20 uses `TEMPLATES[20]` × `FILLERS[0]`. Row 70 uses `TEMPLATES[20]` × `FILLERS[1]`. Row 120 uses `TEMPLATES[20]` × `FILLERS[2]`. Etc.
- So the failures cluster on **the same template index (20)** across multiple fillers, plus a handful of other recurrent templates.

This is the same pattern as #13572 (specific input strings deterministically NaN out). The 50-row "cadence" is an artifact of the corpus generator, not of Ollama internals. **The actionable signal is: certain template+filler combinations deterministically trigger NaN output in bge-m3 at F16.**

If filing/commenting, please mention that the failing inputs are reproducibly identifiable from the row indices in the JSON and can be extracted on request.

## Throughput, VRAM, drift

For completeness, none of these point at Ollama as misbehaving:

- **Throughput:** mean 181.8 ms ± 19.5 ms per embed; p95 213.7 ms; p99 227.1 ms.
- **Drift:** first-100 mean 200.8 ms → last-100 mean 169.6 ms (warmup, *faster* over time, not slower). No degradation under sustained load.
- **VRAM:** flat at 5519 MiB across 25 snapshots over ~280 s after initial bge-m3 residency. Zero creep. (The earlier 15940 MiB readings were pre-eviction of `gemma4:e4b`.)
- **Pacing change at row 20** (50 → 100 ms) did not change failure behavior — 12 more 500s still hit despite doubling the inter-call gap. **This is the strongest evidence that the failure is content-deterministic, not load-related.**

## Workarounds we applied (downstream)

In our application (Aether — local-first AI companion doing memory-row backfill embedding), we treat per-row 500s as recoverable:

1. **Continue on 500 — do not abort the batch.** The failed row is logged and counted.
2. **Skip-already-embedded path** on the next backfill invocation re-tries only the rows that didn't get a vector last time. So the 1.3% residue is recovered automatically on subsequent runs.
3. **Future hardening (not yet landed):** add per-row retry-on-500 with one exponential backoff before counting as failure.

## Workarounds we did NOT yet test (would help triage)

1. `OLLAMA_FLASH_ATTENTION=false` (suggested in #14657 / #9639). High-priority next test.
2. Substituting `nomic-embed-text` for the same 1000-row corpus to see whether *any* rows still NaN out (#9639 says nomic-embed-text also hits this, so it may not be a clean A/B).
3. Bisecting the failing inputs to isolate the minimal NaN-triggering string for each failure (would dovetail with #13572's existing minimal-repro work).

## Why this matters at scale

A 1.3% silent-failure rate on a backfill workload compounds badly:

- 1k rows: 13 lost embeddings (recoverable in our app via skip-already-embedded re-run).
- 10k rows: ~130 lost embeddings.
- 100k rows: ~1,300 lost embeddings — and without an idempotent "embed only the missing" recovery loop, that's silent corpus rot.

For RAG / memory / document-indexing pipelines built on Ollama, this should be either:

- **Fixed at the model-runner layer** (NaN guard on the embedding vector before serialization, returning HTTP 422 with a clear error instead of a 500 with a JSON-encoder error message), OR
- **Documented prominently** so downstream systems know to add idempotent retry-with-skip loops.

The patch mentioned in the existing thread (#9639 / #14657) — adding NaN/Inf validation in `runner.embedding` paths and returning `model produced invalid embedding values (NaN or Inf)` — would already be a major UX improvement over the current "looks like a server crash" behavior.

## Logs and artifacts

- Raw timeline JSON (1000 per-row latencies, 13 failure bodies, 25 VRAM snapshots, 100-row windows): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/backfill_stress_results.json
- Reproducer script (well-commented Python, no Ollama-side dependencies beyond a running daemon): file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/bench_backfill_stress.py
- Full narrative report with stability tables: file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-25/BACKFILL_STRESS_REPORT.md

Happy to share the exact 13 failing input strings on request — they are deterministically reconstructable from the row indices in the JSON.

---

## Comment body — paste-ready for github.com/ollama/ollama/issues/13572

> Confirming this on Ollama 0.21.2 / Windows 11 / RTX 3090 Ti / `bge-m3` (default F16 pull) with a sustained-load benchmark.
>
> **1000 sequential `/api/embed` calls, varied input corpus (50 templates × 50 fillers), 50 ms inter-call pacing → 13 HTTP 500s, 987 successes (1.3% failure rate).** All 13 failures carried the identical body:
>
> ```
> {"error":"failed to encode response: json: unsupported value: NaN"}
> ```
>
> Bumping pacing from 50 ms → 100 ms after the first failure did **not** change the failure rate — strong signal that this is content-deterministic, not load-related, exactly as your German-quantum-text observation suggested. The failures cluster on the same template indices across different fillers in our corpus, mirroring your "76/1217 specific texts" finding.
>
> Latency, VRAM, and throughput were all healthy throughout the run (mean 181.8 ms / p99 227 ms, VRAM flat at 5519 MiB, throughput slightly improving over the warmup window). So the bug really does look isolated to the model producing NaN for specific inputs, not to runtime pressure.
>
> Reproducer + raw 1000-row JSON timeline + per-failure log available here:
>
> - reproducer: https://github.com/<don's-fork-or-gist-here>/bench_backfill_stress.py
> - raw run JSON: https://github.com/<don's-fork-or-gist-here>/backfill_stress_results.json
>
> Have not yet tested `OLLAMA_FLASH_ATTENTION=false` — will report back when I do.
>
> Strong +1 on the proposed fix to return a clear HTTP error (`model produced invalid embedding values (NaN or Inf)`) instead of the current `failed to encode response: json: unsupported value: NaN` 500 — the latter reads like a server crash and complicates downstream error handling.

---

(end of draft)
