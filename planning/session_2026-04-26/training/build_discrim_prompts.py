"""STEP 2A: build a ~3000-prompt pool for multi-source AI generation.

Samples conversations from normalized_eval_v3.jsonl, takes the last
3-5 turns as context ending with speaker 'A' (so the model replies
as 'B'). Saves to eval_v4/discrim_prompts.jsonl.
"""
from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "normalized_eval_v3.jsonl"
OUT_DIR = ROOT / "eval_v4"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "discrim_prompts.jsonl"

TARGET = 3000
MIN_CTX = 3
MAX_CTX = 5
MIN_TURN_LEN = 2
MAX_TURN_LEN = 280
SEED = 1729


def normalize_speaker(s: str) -> str:
    s = (s or "").strip().upper()
    if s in ("A", "USER"):
        return "A"
    if s in ("B", "ASSISTANT"):
        return "B"
    return s[:1] if s else "?"


def main() -> int:
    rng = random.Random(SEED)
    candidates: list[dict] = []
    with SRC.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            turns = obj.get("turns") or []
            if len(turns) < MIN_CTX + 1:
                continue
            cleaned = []
            for t in turns:
                txt = (t.get("text") or "").strip()
                sp = normalize_speaker(t.get("speaker", ""))
                if not txt or len(txt) < MIN_TURN_LEN or len(txt) > MAX_TURN_LEN:
                    cleaned = []
                    break
                if sp not in ("A", "B"):
                    cleaned = []
                    break
                cleaned.append({"speaker": sp, "text": txt})
            if not cleaned or len(cleaned) < MIN_CTX + 1:
                continue
            candidates.append({"source": obj.get("source", "?"), "turns": cleaned})

    print(f"  found {len(candidates)} candidate conversations")
    if len(candidates) < TARGET * 2:
        print(f"  WARNING: only {len(candidates)} clean candidates (~{TARGET*2} desired)")
    rng.shuffle(candidates)

    # Stratify lightly by source so one corpus doesn't dominate.
    by_source: dict[str, list[dict]] = {}
    for c in candidates:
        by_source.setdefault(c["source"], []).append(c)
    print("  per-source counts:")
    for k, v in sorted(by_source.items(), key=lambda x: -len(x[1])):
        print(f"    {k}: {len(v)}")

    # Round-robin draw across sources up to TARGET.
    queues = [list(v) for v in by_source.values()]
    out: list[dict] = []
    while len(out) < TARGET and any(queues):
        for q in queues:
            if not q:
                continue
            conv = q.pop()
            n_ctx = rng.randint(MIN_CTX, min(MAX_CTX, len(conv["turns"]) - 1))
            # Ensure last context turn is speaker A
            for end in range(n_ctx, min(MAX_CTX, len(conv["turns"]) - 1) + 1):
                ctx = conv["turns"][:end]
                if ctx and ctx[-1]["speaker"] == "A":
                    out.append({"context": ctx, "source": conv["source"]})
                    break
            if len(out) >= TARGET:
                break

    print(f"  built {len(out)} prompts (target {TARGET})")
    with OUT.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")

    # Print source distribution of final pool
    src_counts: dict[str, int] = {}
    for r in out:
        src_counts[r["source"]] = src_counts.get(r["source"], 0) + 1
    print("  final source distribution:")
    for k, v in sorted(src_counts.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
