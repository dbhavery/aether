"""STEP 3: re-eval all candidate models against the multi-model discriminator.

Scores the existing 200-sample held-out outputs:
  - eval_v2/finetuned_outputs.jsonl       (V2 fine-tuned)
  - eval_v3/v3_partial_3000_outputs.jsonl (V3-partial)
  - eval_v3/raw_base_outputs.jsonl        (raw Qwen2.5-3B-Instruct)
  - eval_v2/baseline_outputs.jsonl        (gemma4:e4b)

against checkpoints_v4/discriminator_multi/final.

Also reports per-AI-source recall: for each source in
discrim_prompts.jsonl, how often does the discriminator correctly
flag that source's outputs as AI? (Sanity that the new discriminator
isn't biased toward one model.)

Saves to eval_v3/scores_multi_discrim.json.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V2 = ROOT / "eval_v2"
EVAL_V3 = ROOT / "eval_v3"
EVAL_V4 = ROOT / "eval_v4"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"

CANDIDATES = [
    ("v2_finetuned", EVAL_V2 / "finetuned_outputs.jsonl"),
    ("v3_partial", EVAL_V3 / "v3_partial_3000_outputs.jsonl"),
    ("raw_base", EVAL_V3 / "raw_base_outputs.jsonl"),
    ("gemma4_baseline", EVAL_V2 / "baseline_outputs.jsonl"),
]

# In-distribution generation files (for per-source AI-detection rate)
IN_DIST = [
    ("gemma4", EVAL_V4 / "gen_gemma4.jsonl"),
    ("qwen3", EVAL_V4 / "gen_qwen3.jsonl"),
    ("base", EVAL_V4 / "gen_base.jsonl"),
    ("v2", EVAL_V4 / "gen_v2.jsonl"),
    ("v3", EVAL_V4 / "gen_v3.jsonl"),
]

POS = EVAL_V4 / "human_positives.jsonl"


def load_outputs(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            t = obj.get("output", "").strip()
            if t:
                out.append(t)
    return out


def load_outputs_with_source(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            t = obj.get("output", "").strip()
            if t:
                out.append((obj.get("source", "?"), t))
    return out


def main() -> int:
    print("ensuring Ollama is dead before loading transformers")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    from transformers import pipeline
    print(f"loading discriminator from {DISCRIM_DIR}")
    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    def human_rate(texts: list[str]) -> dict:
        if not texts:
            return {"n": 0, "human_rate": None}
        preds = clf(texts, truncation=True, padding=True,
                    max_length=128, batch_size=64)
        n_human = 0
        confidences = []
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
            h = scores.get("LABEL_1", 0.0)
            a = scores.get("LABEL_0", 0.0)
            confidences.append(h)
            if h > a:
                n_human += 1
        return {
            "n": len(texts),
            "human_rate": n_human / len(texts),
            "avg_human_confidence": sum(confidences) / len(confidences),
        }

    print("\n=== held-out 200-sample candidate scoring ===")
    candidate_scores = {}
    for label, path in CANDIDATES:
        outs = load_outputs(path)
        candidate_scores[label] = human_rate(outs)
        print(f"  {label}: {candidate_scores[label]}")

    # Per-source AI-detection rate (uses in-distribution generation files
    # — these are the same prompts the discriminator was trained on, so
    # this is a sanity check, not held-out generalization).
    print("\n=== in-distribution per-source detection rates ===")
    in_dist_scores = {}
    for label, path in IN_DIST:
        outs = load_outputs_with_source(path)
        # Hold out last 1/5 to mimic "unseen" — discriminator trained on
        # all but eval split; can't perfectly reconstruct that split here,
        # so report aggregate rate plus per-source breakdown.
        all_texts = [t for _, t in outs]
        rate = human_rate(all_texts)
        per_src: dict[str, dict] = {}
        by_src: dict[str, list[str]] = {}
        for s, t in outs:
            by_src.setdefault(s, []).append(t)
        for s, ts in by_src.items():
            per_src[s] = human_rate(ts)
        in_dist_scores[label] = {"overall": rate, "per_source": per_src}
        print(f"  [{label}] overall human-rate={rate.get('human_rate')}  "
              f"(lower = discriminator correctly catches as AI)")

    # Human positives baseline (should score high)
    pos_outs = [r["output"] for r in
                (json.loads(line) for line in POS.open("r", encoding="utf-8") if line.strip())
                if r.get("output", "").strip()]
    pos_score = human_rate(pos_outs[:2000])
    print(f"\n  human positives sanity: {pos_score}")

    payload = {
        "discriminator_path": str(DISCRIM_DIR),
        "candidate_scores": candidate_scores,
        "in_distribution_per_source": in_dist_scores,
        "human_positives_sanity": pos_score,
        "interpretation": (
            "human_rate is the fraction classified as human. For AI sources, "
            "LOWER = better discriminator (it correctly flags them). For the "
            "human-positives line, HIGHER = better."
        ),
    }
    out_path = EVAL_V3 / "scores_multi_discrim.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
