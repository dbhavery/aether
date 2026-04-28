"""V6 data prep: build multi-turn-format SFT pairs.

Hypothesis: V5's multi-turn regression came from training on (context →
single response) format. This script builds training examples where
each is a full multi-turn conversation, so the model learns to predict
multiple assistant turns within one chat history.

Each example: a window of 4-8 turns from a normalized conversation,
formatted as a complete chat with multiple alternating user/assistant
turns. The standard causal LM loss across the whole sequence trains
the model on the rhythm.

Output: data/sft_train_v6.jsonl (~30k multi-turn windows)
"""
from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SRC = DATA / "normalized_train_v4.jsonl"
OUT_TRAIN = DATA / "sft_train_v6.jsonl"
OUT_EVAL = DATA / "sft_eval_v6.jsonl"

TARGET_TOTAL = 30000
EVAL_FRACTION = 0.02
MIN_TURNS = 4
MAX_TURNS = 8
MIN_TURN_LEN = 2
MAX_TURN_LEN = 280
SEED = 271828

# Per-source caps to balance distribution (same intent as v4 mix)
PER_SOURCE_CAP = 6500

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
    print(f"  total convos: {n_total}, usable per-source:")
    for k, v in sorted(by_source.items(), key=lambda x: -len(x[1])):
        print(f"    {k}: {len(v)}")

    # Build multi-turn windows
    windows: list[dict] = []
    for src, convos in by_source.items():
        rng.shuffle(convos)
        per_src = []
        for conv in convos:
            if len(per_src) >= PER_SOURCE_CAP:
                break
            n = len(conv)
            # Take a window of MIN_TURNS to MAX_TURNS turns starting somewhere
            # that ensures the window starts on speaker A (so the chat template
            # alternates user/assistant correctly)
            window_size = rng.randint(MIN_TURNS, min(MAX_TURNS, n))
            max_start = n - window_size
            if max_start < 0:
                continue
            # Pick a start where turn[start].speaker == "A"
            valid_starts = [i for i in range(max_start + 1) if conv[i]["speaker"] == "A"]
            if not valid_starts:
                continue
            start = rng.choice(valid_starts)
            window = conv[start:start + window_size]
            # Window should alternate A/B and end on a B turn (so the
            # final assistant generation is meaningful as a "completion")
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

    # Source distribution
    from collections import Counter
    counter = Counter(w["source"] for w in train_set)
    print("  train source distribution:")
    for k, v in counter.most_common():
        print(f"    {k}: {v} ({100*v/len(train_set):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
