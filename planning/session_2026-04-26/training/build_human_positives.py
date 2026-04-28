"""STEP 2D: sample ~10000 human positive examples from v3 corpora.

Pulls real human turns (text-only, no speaker labels) from the v3
normalized eval pool, stratified across sources so the discriminator
learns "human in general" not one register.

Saves to eval_v4/human_positives.jsonl with the same schema as the
generated outputs: {source, output}.
"""
from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "normalized_eval_v3.jsonl"
OUT = ROOT / "eval_v4" / "human_positives.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)

TARGET = 10000
PER_SOURCE_CAP = 1500
MIN_LEN = 4
MAX_LEN = 280
SEED = 4242


def main() -> int:
    rng = random.Random(SEED)
    pool: dict[str, list[dict]] = {}
    with SRC.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = obj.get("source", "?")
            for t in obj.get("turns", []):
                txt = (t.get("text") or "").strip()
                if not txt or len(txt) < MIN_LEN or len(txt) > MAX_LEN:
                    continue
                pool.setdefault(src, []).append({"source": src, "output": txt})

    print("  candidate human turns per source:")
    for k, v in sorted(pool.items(), key=lambda x: -len(x[1])):
        print(f"    {k}: {len(v)}")

    chosen: list[dict] = []
    for src, items in pool.items():
        rng.shuffle(items)
        take = min(PER_SOURCE_CAP, len(items))
        chosen.extend(items[:take])
        print(f"  took {take} from {src}")

    rng.shuffle(chosen)
    chosen = chosen[:TARGET]
    print(f"  total: {len(chosen)}")

    with OUT.open("w", encoding="utf-8") as f:
        for r in chosen:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
