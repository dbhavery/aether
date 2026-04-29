"""V9 quick eval — held-out PPL + WildChat only.

Trimmed from full V8 eval (which also runs 25-seed multi-turn self-test
through the V4 multi-discriminator). For the V9 sweep we want fast
comparable signal across 3 variants — each variant gets ~50 min eval
instead of 70-90 min, total sweep eval ~2.5 hr instead of 4+ hr.

Pass variant slug as argv[1]: 'v9a' | 'v9b' | 'v9c'.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

VARIANT_TO_CONFIG = {
    "v9a": {
        "base": "Qwen/Qwen2.5-3B-Instruct",
        "ckpt_subpath": "checkpoints_v9a/qwen25_3b_human_lora_v9a/final",
        "max_len": 1024,
    },
    "v9b": {
        "base": "Qwen/Qwen2.5-3B-Instruct",
        "ckpt_subpath": "checkpoints_v9b/qwen25_3b_human_lora_v9b/final",
        "max_len": 1024,
    },
    "v9c": {
        "base": "Qwen/Qwen2.5-7B-Instruct",
        "ckpt_subpath": "checkpoints_v9c/qwen25_7b_human_lora_v9c/final",
        "max_len": 768,
    },
}

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOGS = ROOT / "logs_v9_sweep"
LOGS.mkdir(parents=True, exist_ok=True)

EVAL_HELDOUT = DATA / "sft_eval_v6.jsonl"      # held-out conversations
EVAL_WILDCHAT = ROOT / "eval_v4" / "wildchat_holdout_prompts.jsonl"  # canonical WildChat holdout used by V4-V8 evals

N_HELDOUT = 200
N_WILDCHAT = 200
MAX_NEW_TOKENS = 80


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in VARIANT_TO_CONFIG:
        print(f"usage: {sys.argv[0]} <v9a|v9b|v9c>")
        return 2
    variant = sys.argv[1]
    cfg = VARIANT_TO_CONFIG[variant]
    done_flag = LOGS / f"phase_{variant}_eval.done"
    if done_flag.exists():
        print(f"[{variant}-eval] already done; skipping")
        return 0

    ckpt = ROOT / cfg["ckpt_subpath"]
    if not ckpt.exists():
        print(f"[{variant}-eval] FATAL: checkpoint missing at {ckpt}")
        return 2

    print(f"[{variant}-eval] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel

    out_dir = ROOT / f"eval_{variant}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{variant}-eval] loading {cfg['base']} + {ckpt}")
    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(cfg["base"], trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        cfg["base"], quantization_config=bnb_cfg, device_map="auto",
        trust_remote_code=True, attn_implementation="sdpa",
    )
    model = PeftModel.from_pretrained(base, str(ckpt))
    model.eval()

    # ---- 1) held-out perplexity ----
    print(f"[{variant}-eval] held-out PPL ({N_HELDOUT})")
    heldout = []
    with EVAL_HELDOUT.open("r", encoding="utf-8") as f:
        for line in f:
            heldout.append(json.loads(line))
            if len(heldout) >= N_HELDOUT:
                break

    losses = []
    t0 = time.time()
    with torch.no_grad():
        for i, ex in enumerate(heldout):
            if i % 50 == 0:
                print(f"  [heldout] {i}/{len(heldout)} ({time.time()-t0:.0f}s)")
            msgs = ex["messages"]
            text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
            inp = tok(text, return_tensors="pt", truncation=True, max_length=cfg["max_len"]).to(model.device)
            if inp.input_ids.shape[1] < 2:
                continue
            out = model(**inp, labels=inp.input_ids)
            losses.append(float(out.loss))
    import math
    mean_loss = sum(losses) / max(len(losses), 1)
    ppl = math.exp(mean_loss)
    print(f"[{variant}-eval] held-out loss={mean_loss:.4f} ppl={ppl:.3f}")

    # ---- 2) WildChat generation pass (qualitative — record only) ----
    SYSTEM = (
        "You are continuing a casual conversation between two people. "
        "Reply naturally as the other speaker — short, human, no AI mannerisms. "
        "Match the tone, register, and length of the dialog you've been shown."
    )
    print(f"[{variant}-eval] WildChat generations ({N_WILDCHAT})")
    wildchat = []
    if EVAL_WILDCHAT.exists():
        with EVAL_WILDCHAT.open("r", encoding="utf-8") as f:
            for line in f:
                wildchat.append(json.loads(line))
                if len(wildchat) >= N_WILDCHAT:
                    break

    gens = []
    t0 = time.time()
    for i, ex in enumerate(wildchat):
        if i % 25 == 0:
            print(f"  [wildchat] {i}/{len(wildchat)} ({time.time()-t0:.0f}s)")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in ex.get("context", []):
            role = "user" if t.get("speaker") == "A" else "assistant"
            msgs.append({"role": role, "content": t.get("text", "")})
        s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt", truncation=True, max_length=cfg["max_len"]).to(model.device)
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=MAX_NEW_TOKENS, do_sample=True,
                              top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        text = tok.decode(o[0][inp.input_ids.shape[1]:], skip_special_tokens=True).strip()
        gens.append({"id": ex.get("id", i), "generation": text})

    (out_dir / f"{variant}_wildchat_generations.jsonl").write_text(
        "\n".join(json.dumps(g) for g in gens) + "\n", encoding="utf-8"
    )

    summary = {
        "variant": variant,
        "ckpt": str(ckpt),
        "heldout_n": len(losses),
        "heldout_loss": mean_loss,
        "heldout_ppl": ppl,
        "wildchat_n": len(gens),
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out_dir / f"{variant}_eval_results.json").write_text(json.dumps(summary, indent=2))
    print(f"[{variant}-eval] summary: {json.dumps(summary)}")
    done_flag.touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
