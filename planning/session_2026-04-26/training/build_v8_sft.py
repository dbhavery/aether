"""V8 data prep: multi-turn-format SFT with LARGER windows (8-12 turns).

Sibling of build_v6_multiturn_sft.py. Same logic, larger windows. Tests
"is the rhythm signal richer with longer windows?" alongside V8's
higher-rank LoRA experiment.

Output: data/sft_train_v8.jsonl (~25k multi-turn windows, 8-12 turns)
        data/sft_eval_v8.jsonl
"""
from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SRC = DATA / "normalized_train_v4.jsonl"
OUT_TRAIN = DATA / "sft_train_v8.jsonl"
OUT_EVAL = DATA / "sft_eval_v8.jsonl"

TARGET_TOTAL = 25000
EVAL_FRACTION = 0.02
MIN_TURNS = 8
MAX_TURNS = 12
MIN_TURN_LEN = 2
MAX_TURN_LEN = 280
SEED = 314159
PER_SOURCE_CAP = 5500

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def normalize_speaker(s: str) -> str:
    s = (s or "").strip().upper()
    if s in ("A", "USER"):
        return "A"
    if s in ("B", "ASSISTANT"):
        return "B"
    return "?"


def main() -> int:
    rng = random.Random(SEED)
    print(f"reading {SRC}")
    by_source: dict[str, list] = {}
    n_total = 0
    with SRC.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_total += 1
            src = obj.get("source", "?")
            turns = obj.get("turns") or []
            clean = []
            ok = True
            for t in turns:
                sp = normalize_speaker(t.get("speaker", ""))
                txt = (t.get("text") or "").strip()
                if sp not in ("A", "B"):
                    ok = False
                    break
                if not (MIN_TURN_LEN <= len(txt) <= MAX_TURN_LEN):
                    continue
                clean.append({"speaker": sp, "text": txt})
            if not ok or len(clean) < MIN_TURNS:
                continue
            by_source.setdefault(src, []).append(clean)
    print(f"  total convos: {n_total}, usable per-source (>=8 turns):")
    for k, v in sorted(by_source.items(), key=lambda x: -len(x[1])):
        print(f"    {k}: {len(v)}")

    windows: list[dict] = []
    for src, convos in by_source.items():
        rng.shuffle(convos)
        per_src = []
        for conv in convos:
            if len(per_src) >= PER_SOURCE_CAP:
                break
            n = len(conv)
            window_size = rng.randint(MIN_TURNS, min(MAX_TURNS, n))
            max_start = n - window_size
            if max_start < 0:
                continue
            valid_starts = [i for i in range(max_start + 1) if conv[i]["speaker"] == "A"]
            if not valid_starts:
                continue
            start = rng.choice(valid_starts)
            window = conv[start:start + window_size]
            if window[-1]["speaker"] == "A":
                window = window[:-1]
            if len(window) < MIN_TURNS:
                continue
            per_src.append({"source": src, "turns": window})
        windows.extend(per_src)
        print(f"  built {len(per_src)} windows from {src}")

    print(f"  total windows: {len(windows)}")
    rng.shuffle(windows)
    if len(windows) > TARGET_TOTAL:
        windows = windows[:TARGET_TOTAL]
    print(f"  capped to {len(windows)}")

    n_eval = int(len(windows) * EVAL_FRACTION)
    eval_set = windows[:n_eval]
    train_set = windows[n_eval:]
    print(f"  train {len(train_set)} / eval {len(eval_set)}")

    def to_chat(window):
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in window["turns"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        return msgs

    def write(rows, path):
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                obj = {"messages": to_chat(r), "source": r.get("source", "?")}
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        print(f"  wrote {path}")

    write(train_set, OUT_TRAIN)
    write(eval_set, OUT_EVAL)

    from collections import Counter
    counter = Counter(w["source"] for w in train_set)
    print("  train source distribution:")
    for k, v in counter.most_common():
        print(f"    {k}: {v} ({100*v/len(train_set):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
