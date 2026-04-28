"""V4-02: normalize new corpora + build sft_train_v4.jsonl with §4.4 rebalanced mix.

Inputs:
  data/normalized_train_v3.jsonl  (existing v3 corpora, normalized)
  data/lex_fridman_chunked/conversations.jsonl  (V4-01 output)
  data/ordinary_screenplays/   (HF dataset, 138 scenes)

Output:
  data/normalized_train_v4.jsonl  (combined normalized pool)
  data/sft_train_v4.jsonl         (rebalanced + SFT-formatted)
  data/sft_eval_v4.jsonl          (held-out eval split)

Stratification target (~55k SFT pairs for ~5h budget at observed pace):
  cornell_movie:    20%
  daily_dialog:     15%
  yt_podcast:       12%   (replaces 'lex_fridman intellectual' since lex re-mine is small)
  reddit_casual:    10%
  blended_skill:    10%
  topical_chat:      8%
  oasst2:            5%
  ordinary_screenplays: 5%
  lex_fridman:       5%
  stemm_podcast:     5%   (was over-represented; capped)
  soda:              4%
  empathetic:        1%   (NC license — eval-only ideally; small training share)
"""
from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

V3_NORM = DATA / "normalized_train_v3.jsonl"
LEX_FILE = DATA / "lex_fridman_chunked" / "conversations.jsonl"
SCREENPLAYS_DIR = DATA / "ordinary_screenplays"

OUT_NORM = DATA / "normalized_train_v4.jsonl"
OUT_TRAIN = DATA / "sft_train_v4.jsonl"
OUT_EVAL = DATA / "sft_eval_v4.jsonl"

TARGET_TOTAL = 55000
EVAL_FRACTION = 0.02  # 1100 eval samples

MIX_PCT = {
    "cornell_movie": 0.20,
    "daily_dialog": 0.15,
    "yt_podcast": 0.12,
    "reddit_casual": 0.10,
    "blended_skill": 0.10,
    "topical_chat": 0.08,
    "oasst2": 0.05,
    "ordinary_screenplays": 0.05,
    "lex_fridman": 0.05,
    "stemm_podcast": 0.05,
    "soda": 0.04,
    "empathetic": 0.01,
}

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)

MIN_CTX = 2
MAX_CTX = 6
MIN_TURN_LEN = 2
MAX_TURN_LEN = 320
SEED = 31415


def load_v3_normalized():
    rows = []
    with V3_NORM.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"  v3 normalized: {len(rows)} convos")
    return rows


def load_lex():
    if not LEX_FILE.exists():
        return []
    rows = []
    with LEX_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"  lex_fridman: {len(rows)} convos")
    return rows


def load_screenplays():
    """Each scene's `dialog` -> normalized turns."""
    if not (SCREENPLAYS_DIR / "dataset_info.json").exists():
        return []
    from datasets import load_from_disk
    ds = load_from_disk(str(SCREENPLAYS_DIR))
    out = []
    convo_id = 0
    for row in ds:
        dialog = row.get("dialog") or []
        if len(dialog) < MIN_CTX + 1:
            continue
        # Map speaker names to A/B by alternation
        speakers = []
        last_sp = None
        seen = {}
        for d in dialog:
            sp_name = (d.get("speaker") or "?").strip().upper()
            if sp_name not in seen:
                seen[sp_name] = "AB"[len(seen) % 2]
            speakers.append(seen[sp_name])
        # Build turns; collapse consecutive same-speaker into one turn
        turns = []
        for i, d in enumerate(dialog):
            sp = speakers[i]
            text = " ".join(d.get("lines") or []).strip()
            if not text:
                continue
            if not turns or turns[-1]["speaker"] != sp:
                turns.append({"speaker": sp, "text": text})
            else:
                turns[-1]["text"] = (turns[-1]["text"] + " " + text).strip()
        # Validate
        clean = []
        for t in turns:
            if MIN_TURN_LEN <= len(t["text"]) <= MAX_TURN_LEN:
                clean.append(t)
            else:
                # Skip oversized — break the run
                if len(clean) >= MIN_CTX + 1:
                    out.append({
                        "source": "ordinary_screenplays",
                        "conversation_id": f"ordinary_screenplays.{convo_id}",
                        "turns": list(clean),
                    })
                    convo_id += 1
                clean = []
        if len(clean) >= MIN_CTX + 1:
            out.append({
                "source": "ordinary_screenplays",
                "conversation_id": f"ordinary_screenplays.{convo_id}",
                "turns": clean,
            })
            convo_id += 1
    print(f"  ordinary_screenplays: {len(out)} convos")
    return out


def build_sft_pair(turns: list[dict]) -> list[dict]:
    """From a conversation, produce (context, target) pairs at every speaker-A → speaker-B boundary."""
    pairs = []
    for i in range(MIN_CTX, len(turns)):
        if turns[i]["speaker"] != "B":
            continue
        if turns[i - 1]["speaker"] != "A":
            continue
        ctx = turns[max(0, i - MAX_CTX): i]
        if len(ctx) < MIN_CTX:
            continue
        target = turns[i]["text"].strip()
        if not (MIN_TURN_LEN <= len(target) <= MAX_TURN_LEN):
            continue
        pairs.append({"context": ctx, "target": target})
    return pairs


def to_chat_messages(pair: dict) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    for t in pair["context"]:
        role = "user" if t["speaker"] == "A" else "assistant"
        msgs.append({"role": role, "content": t["text"]})
    msgs.append({"role": "assistant", "content": pair["target"]})
    return msgs


def main() -> int:
    rng = random.Random(SEED)

    # ---- 1. Combine normalized convos
    pool = []
    pool += load_v3_normalized()
    pool += load_lex()
    pool += load_screenplays()
    print(f"  combined pool: {len(pool)} convos")

    # Write combined normalized file
    with OUT_NORM.open("w", encoding="utf-8") as f:
        for r in pool:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  wrote {OUT_NORM}")

    # ---- 2. Index by source, build SFT pairs per source
    src_pairs: dict[str, list[dict]] = {}
    for c in pool:
        src = c.get("source", "?")
        turns = c.get("turns") or []
        # Validate turns shape
        clean = []
        for t in turns:
            sp = (t.get("speaker") or "").strip().upper()
            if sp not in ("A", "B"):
                clean = []
                break
            txt = (t.get("text") or "").strip()
            if not (MIN_TURN_LEN <= len(txt) <= MAX_TURN_LEN):
                continue
            clean.append({"speaker": sp, "text": txt})
        if len(clean) < MIN_CTX + 1:
            continue
        for p in build_sft_pair(clean):
            p["source"] = src
            src_pairs.setdefault(src, []).append(p)

    print("  SFT-pair candidates per source:")
    for k, v in sorted(src_pairs.items(), key=lambda x: -len(x[1])):
        print(f"    {k}: {len(v)}")

    # ---- 3. Stratify by MIX_PCT
    chosen = []
    for src, pct in MIX_PCT.items():
        target = int(TARGET_TOTAL * pct)
        avail = src_pairs.get(src, [])
        if not avail:
            print(f"    [warn] no pairs for {src}, skipping")
            continue
        rng.shuffle(avail)
        take = min(target, len(avail))
        chosen.extend(avail[:take])
        print(f"    {src}: target {target}, took {take} of {len(avail)}")

    # Top up with anything else if budget allows
    if len(chosen) < TARGET_TOTAL:
        leftover = []
        for src, items in src_pairs.items():
            if src in MIX_PCT:
                # already drew from this; remaining items are fine to use
                used = int(TARGET_TOTAL * MIX_PCT[src])
                leftover.extend(items[used:])
            else:
                leftover.extend(items)
        rng.shuffle(leftover)
        need = TARGET_TOTAL - len(chosen)
        chosen.extend(leftover[:need])
        print(f"  topped up with {min(need, len(leftover))} leftover pairs")

    rng.shuffle(chosen)
    print(f"  final SFT pairs: {len(chosen)}")

    # ---- 4. Eval split
    n_eval = int(len(chosen) * EVAL_FRACTION)
    eval_set = chosen[:n_eval]
    train_set = chosen[n_eval:]
    print(f"  train {len(train_set)} / eval {len(eval_set)}")

    # ---- 5. Format as chat-formatted SFT (target plus context).
    # Trainer expects {"messages": [...]} or a "text" field.
    def write_sft(rows, path):
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                obj = {"messages": to_chat_messages(r), "source": r.get("source", "?")}
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        print(f"  wrote {path}")

    write_sft(train_set, OUT_TRAIN)
    write_sft(eval_set, OUT_EVAL)

    # Source distribution of final train
    src_count: dict[str, int] = {}
    for r in train_set:
        src_count[r.get("source", "?")] = src_count.get(r.get("source", "?"), 0) + 1
    print("  train source distribution:")
    for k, v in sorted(src_count.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v} ({100*v/len(train_set):.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
