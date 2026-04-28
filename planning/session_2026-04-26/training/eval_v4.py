"""V4-04: eval V4 against multi-discriminator (held-out 200 + WildChat held-outs).

Scoring:
  1. Generate 200 outputs from V4 on eval_v2/eval_prompts.jsonl
     (1:1 comparison to V2 21.5% / V3-partial 26.5% / raw base 6.5%).
  2. Generate 200 outputs from V4 on WildChat held-out prompts
     (genuinely unseen distribution).
  3. Score both against checkpoints_v4/discriminator_multi/final.

Output: eval_v4/v4_eval_results.json + per-set JSONL outputs.
"""
from __future__ import annotations
import json
import os
import sys
import time
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V4 = ROOT / "eval_v4"
EVAL_V2 = ROOT / "eval_v2"
DATA = ROOT / "data"

CKPT_V3 = ROOT / "checkpoints_v3" / "qwen25_3b_human_lora_v3" / "final_partial_3000"
CKPT_V4 = ROOT / "checkpoints_v4" / "qwen25_3b_human_lora_v4" / "final"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

WILDCHAT_DIR = DATA / "wildchat"

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)

N_HELDOUT = 200
N_WILDCHAT = 200
SEED = 9999


def build_wildchat_prompts(n: int) -> list[dict]:
    """Build held-out prompt set from WildChat."""
    out_path = EVAL_V4 / "wildchat_holdout_prompts.jsonl"
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            existing = [json.loads(l) for l in f if l.strip()]
        if len(existing) >= n:
            print(f"  reusing {len(existing)} WildChat prompts at {out_path}")
            return existing[:n]

    print("  loading WildChat from disk...")
    from datasets import load_from_disk
    ds = load_from_disk(str(WILDCHAT_DIR))["train"]
    rng = random.Random(SEED)
    indices = list(range(min(50000, len(ds))))
    rng.shuffle(indices)

    prompts = []
    for idx in indices:
        if len(prompts) >= n:
            break
        row = ds[idx]
        if row.get("language") != "English":
            continue
        if row.get("toxic"):
            continue
        conv = row.get("conversation") or []
        if len(conv) < 3:
            continue
        # Build alternating A/B from user/assistant turns
        turns = []
        for t in conv[:8]:
            role = t.get("role", "")
            content = (t.get("content") or "").strip()
            if not content or len(content) > 280:
                continue
            sp = "A" if role == "user" else "B"
            turns.append({"speaker": sp, "text": content})
        # Need >=3 turns ending with A
        if len(turns) < 3:
            continue
        # Take last 3-5 turns ending with A
        for end in range(min(5, len(turns)), 2, -1):
            ctx = turns[:end]
            if ctx and ctx[-1]["speaker"] == "A":
                prompts.append({"context": ctx, "source": "wildchat"})
                break

    print(f"  built {len(prompts)} WildChat prompts")
    with out_path.open("w", encoding="utf-8") as f:
        for p in prompts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return prompts[:n]


def generate(prompts: list[dict], model, tok, label: str) -> list[str]:
    import torch
    out = []
    t0 = time.time()
    for i, p in enumerate(prompts):
        if i % 25 == 0:
            print(f"  [{label}] {i}/{len(prompts)} ({time.time()-t0:.0f}s)")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        prompt_str = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_str, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outs = model.generate(**inputs, max_new_tokens=80, do_sample=True,
                                  top_p=0.9, temperature=0.8,
                                  pad_token_id=tok.pad_token_id)
        text = tok.decode(outs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        out.append(text)
    print(f"  [{label}] done {len(out)} in {time.time()-t0:.0f}s")
    return out


def main() -> int:
    EVAL_V4.mkdir(parents=True, exist_ok=True)
    print("ensuring Ollama dead")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    if not CKPT_V4.exists():
        print(f"ERROR: V4 checkpoint not found at {CKPT_V4}")
        return 1

    # Load eval prompts
    print("loading eval prompts (v2-style held-out)")
    heldout = []
    with (EVAL_V2 / "eval_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                heldout.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    heldout = heldout[:N_HELDOUT]
    print(f"  {len(heldout)} held-out prompts")

    print("building WildChat held-outs")
    wildchat = build_wildchat_prompts(N_WILDCHAT)

    # Load V4
    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, pipeline)
    from peft import PeftModel

    print(f"loading {BASE_MODEL} + V4 LoRA")
    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb_cfg, device_map="auto",
        trust_remote_code=True, attn_implementation="sdpa",
    )
    model = PeftModel.from_pretrained(base, str(CKPT_V4))
    model.eval()
    print("V4 model ready")

    heldout_outs = generate(heldout, model, tok, "v4_heldout")
    wildchat_outs = generate(wildchat, model, tok, "v4_wildchat")

    # Save raw outputs
    (EVAL_V4 / "v4_heldout_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(heldout_outs)),
        encoding="utf-8",
    )
    (EVAL_V4 / "v4_wildchat_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o,
                              "source": wildchat[i].get("source", "?")})
                  for i, o in enumerate(wildchat_outs)),
        encoding="utf-8",
    )

    del model, base
    torch.cuda.empty_cache()

    print(f"loading multi-discriminator from {DISCRIM_DIR}")
    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    def score_set(texts):
        non_empty = [t for t in texts if t]
        if not non_empty:
            return {"n": 0, "human_rate": None}
        preds = clf(non_empty, truncation=True, padding=True,
                    max_length=128, batch_size=64)
        n_human = 0
        confs = []
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
            h = scores.get("LABEL_1", 0.0)
            confs.append(h)
            if h > scores.get("LABEL_0", 0.0):
                n_human += 1
        return {
            "n": len(non_empty),
            "human_rate": n_human / len(non_empty),
            "avg_human_confidence": sum(confs) / len(confs),
        }

    heldout_score = score_set(heldout_outs)
    wildchat_score = score_set(wildchat_outs)

    payload = {
        "v4_heldout_score": heldout_score,
        "v4_wildchat_score": wildchat_score,
        "comparison_baseline": {
            "raw_base_heldout": 0.065,
            "v2_heldout": 0.215,
            "v3_partial_heldout": 0.265,
            "gemma4_heldout": 0.010,
            "human_ceiling_sanity": 0.871,
        },
    }
    (EVAL_V4 / "v4_eval_results.json").write_text(json.dumps(payload, indent=2))
    print("\n=== V4 results ===")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
