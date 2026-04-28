"""STEP 2B: generate AI-source negatives from transformers models.

Generates ~2000 outputs each from:
  - raw Qwen2.5-3B-Instruct (no LoRA)
  - V2 fine-tuned (Qwen + V2 LoRA)
  - V3-partial (Qwen + V3 checkpoint-3000 LoRA)

Uses left-padded batched generation for speed. Saves to:
  eval_v4/gen_base.jsonl
  eval_v4/gen_v2.jsonl
  eval_v4/gen_v3.jsonl
"""
from __future__ import annotations
import gc
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V4 = ROOT / "eval_v4"
PROMPTS_FILE = EVAL_V4 / "discrim_prompts.jsonl"

CKPT_V2 = ROOT / "checkpoints_v2" / "qwen25_3b_human_lora" / "final"
CKPT_V3 = ROOT / "checkpoints_v3" / "qwen25_3b_human_lora_v3" / "final_partial_3000"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

N_PER_MODEL = 2000
BATCH_SIZE = 8
MAX_NEW_TOKENS = 80

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def load_prompts():
    rows = []
    with PROMPTS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows[:N_PER_MODEL]


def build_chat(tok, p):
    msgs = [{"role": "system", "content": SYSTEM}]
    for t in p["context"]:
        role = "user" if t["speaker"] == "A" else "assistant"
        msgs.append({"role": role, "content": t["text"]})
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def generate_for(model, tok, prompts, label):
    import torch
    out = []
    t0 = time.time()
    for i in range(0, len(prompts), BATCH_SIZE):
        batch = prompts[i:i + BATCH_SIZE]
        texts = [build_chat(tok, p) for p in batch]
        # Left-pad for causal LM batched generation
        tok.padding_side = "left"
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True,
                  max_length=768).to(model.device)
        with torch.no_grad():
            outs = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS,
                                  do_sample=True, top_p=0.9, temperature=0.8,
                                  pad_token_id=tok.pad_token_id)
        # Strip prompt prefix
        gen_only = outs[:, enc.input_ids.shape[1]:]
        decoded = tok.batch_decode(gen_only, skip_special_tokens=True)
        for p, d in zip(batch, decoded):
            out.append({
                "prompt_idx": p.get("prompt_idx", i),
                "source": p.get("source", "?"),
                "output": d.strip(),
            })
        done = i + len(batch)
        if (done // BATCH_SIZE) % 25 == 0:
            elapsed = time.time() - t0
            rate = done / max(elapsed, 1e-3)
            eta = (len(prompts) - done) / max(rate, 1e-3)
            print(f"  [{label}] {done}/{len(prompts)} in {elapsed:.0f}s "
                  f"({rate:.1f}/s, ETA {eta:.0f}s)")
    print(f"  [{label}] done: {len(out)} in {time.time()-t0:.0f}s")
    return out


def main() -> int:
    print("ensuring Ollama is dead before loading transformers (free VRAM)")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    prompts = load_prompts()
    # Add prompt_idx so we can join later
    for i, p in enumerate(prompts):
        p["prompt_idx"] = i
    print(f"loaded {len(prompts)} prompts")

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig)
    from peft import PeftModel

    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"

    runs = [
        ("base", None, EVAL_V4 / "gen_base.jsonl"),
        ("v2", str(CKPT_V2), EVAL_V4 / "gen_v2.jsonl"),
        ("v3", str(CKPT_V3), EVAL_V4 / "gen_v3.jsonl"),
    ]

    for label, lora_dir, out_path in runs:
        if out_path.exists() and sum(1 for _ in out_path.open(encoding="utf-8")) >= N_PER_MODEL:
            print(f"[{label}] already complete at {out_path}, skipping")
            continue
        print(f"\n=== generating {label} ===")
        print(f"loading base{' + LoRA' if lora_dir else ''}")
        base = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, quantization_config=bnb_cfg, device_map="auto",
            trust_remote_code=True, attn_implementation="sdpa",
        )
        if lora_dir:
            model = PeftModel.from_pretrained(base, lora_dir)
        else:
            model = base
        model.eval()
        rows = generate_for(model, tok, prompts, label)
        with out_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {out_path}")
        del model
        if lora_dir:
            del base
        gc.collect()
        torch.cuda.empty_cache()

    return 0


if __name__ == "__main__":
    sys.exit(main())
