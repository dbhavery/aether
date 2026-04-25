"""Phase 3A — Embed the synthetic corpus with bge-m3 (Flame default).

Reads `synthetic_corpus.jsonl`, calls Ollama /api/embed for each turn's
text, writes `synthetic_corpus_embedded.jsonl` with an added `embedding`
field.

Pacing: 50ms between calls per ADR-0007 D7 — keeps the embedder happy
when a parallel agent (Phase 3C) is loading other models on the same
GPU. Retries on transient 500 with a 30s backoff.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"
IN_PATH = Path("planning/session_2026-04-25/synthetic_corpus.jsonl")
OUT_PATH = Path("planning/session_2026-04-25/synthetic_corpus_embedded.jsonl")
PACING_MS = 50
MAX_RETRIES = 5


def http_post(path: str, body: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sanitize(text: str) -> str:
    """Strip Unicode replacement characters (U+FFFD) and other control
    junk that bge-m3 occasionally NaNs on. The synthetic corpus contained
    a handful of these from gemma4's en-dash output round-tripping
    through Windows cp1252; rather than re-generate those rows we
    normalize at embed time."""
    # Drop the replacement character outright.
    cleaned = text.replace("�", " ")
    # Collapse any run of whitespace.
    return " ".join(cleaned.split())


def embed(text: str) -> list[float] | None:
    """Returns the embedding, or None if the row is unembeddable
    (persistent NaN response from bge-m3 even after sanitization).
    Transient HTTP errors are retried with a 30s backoff."""
    text = sanitize(text)
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = http_post("/api/embed", {"model": MODEL, "input": text})
            return resp["embeddings"][0]
        except Exception as e:
            msg = str(e)
            # Read the error body if available — Ollama returns the NaN
            # marker in the response body.
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            except Exception:
                pass
            last_err = f"{e}: {body}"
            if "NaN" in body:
                # Permanent for this text; no point retrying.
                print(f"  [skip] embed produced NaN: {text[:60]!r}", file=sys.stderr)
                return None
            print(f"  [retry {attempt+1}] embed failed: {msg}", file=sys.stderr)
            time.sleep(30)
    raise RuntimeError(f"embed failed after {MAX_RETRIES}: {last_err}")


def main() -> int:
    rows = []
    with IN_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"embedding {len(rows)} turns with {MODEL}", file=sys.stderr)

    # Resume support: read any rows already written so a transient 500
    # mid-run (e.g. parallel-agent VRAM pressure) doesn't force a full
    # restart. Append-only on resume.
    already: set[str] = set()
    if OUT_PATH.exists():
        with OUT_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        already.add(json.loads(line)["turn_id"])
                    except Exception:
                        pass
        print(f"resume: {len(already)} rows already embedded", file=sys.stderr)

    t0 = time.perf_counter()
    todo = [r for r in rows if r["turn_id"] not in already]
    print(f"embedding {len(todo)} remaining rows", file=sys.stderr)
    mode = "a" if already else "w"
    with OUT_PATH.open(mode, encoding="utf-8") as f:
        skipped = 0
        for i, row in enumerate(todo):
            v = embed(row["text"])
            if v is None:
                skipped += 1
                continue
            row["embedding"] = v
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 50 == 0:
                elapsed = time.perf_counter() - t0
                rate = (i + 1) / elapsed
                eta = (len(todo) - i - 1) / rate if rate > 0 else 0
                print(f"  {i+1}/{len(todo)} ({rate:.1f}/s, ETA {eta:.0f}s)", file=sys.stderr)
            time.sleep(PACING_MS / 1000.0)

    elapsed = time.perf_counter() - t0
    print(f"\ndone: {len(rows)} embeds in {elapsed:.1f}s ({len(rows)/elapsed:.1f}/s)", file=sys.stderr)
    print(f"wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
