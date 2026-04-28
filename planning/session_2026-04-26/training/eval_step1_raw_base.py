"""STEP 1 (sanity): score raw Qwen2.5-3B-Instruct (no LoRA) against v2 discriminator.

If raw base already scores ~100% it confirms the v2 discriminator is just a
"is gemma4 / not gemma4" classifier and the fine-tuning isn't doing useful
work by this metric.

Adapted from eval_v3_partial.py — the only change is skipping the
PeftModel.from_pretrained step.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CKPT_V2 = ROOT / "checkpoints_v2"
EVAL_V3 = ROOT / "eval_v3"
EVAL_V3.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
DISCRIM_DIR = CKPT_V2 / "discriminator_distilbert" / "final"

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def main() -> int:
    print("loading eval prompts (reusing v2 prompts for 1:1 comparability)")
    eval_prompts = []
    with (ROOT / "eval_v2" / "eval_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                eval_prompts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"  {len(eval_prompts)} eval prompts loaded")

    print("ensuring Ollama is dead before loading transformers (free VRAM)")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, pipeline)

    print(f"loading raw base {BASE_MODEL} (no LoRA)")
    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb_cfg, device_map="auto",
        trust_remote_code=True, attn_implementation="sdpa",
    )
    model.eval()
    print("model ready")

    base_outs = []
    t0 = time.time()
    for i, p in enumerate(eval_prompts):
        if i % 25 == 0:
            print(f"  raw-base gen {i}/{len(eval_prompts)} ({time.time()-t0:.0f}s)")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        prompt_str = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_str, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outs = model.generate(**inputs, max_new_tokens=80, do_sample=True,
                                  top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        text = tok.decode(outs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        base_outs.append(text)
    print(f"  {len(base_outs)} raw-base outputs in {time.time()-t0:.0f}s")
    (EVAL_V3 / "raw_base_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(base_outs)),
        encoding="utf-8",
    )

    del model
    torch.cuda.empty_cache()

    print(f"loading discriminator from {DISCRIM_DIR}")
    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    def score_set(texts):
        preds = clf(texts, truncation=True, padding=True, max_length=128, batch_size=32)
        n_human = 0
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
            if scores.get("LABEL_1", 0) > scores.get("LABEL_0", 0):
                n_human += 1
        return n_human / len(texts) if texts else 0.0

    raw_rate = score_set([o for o in base_outs if o])
    v2_scores = json.loads((ROOT / "eval_v2" / "scores.json").read_text(encoding="utf-8"))
    payload = {
        "n_eval_prompts": len(eval_prompts),
        "n_nonempty_outputs": sum(1 for o in base_outs if o),
        "baseline_gemma4_human_rate": v2_scores["baseline_human_rate"],
        "v2_finetuned_human_rate": v2_scores["finetuned_human_rate"],
        "raw_base_human_rate": raw_rate,
        "delta_raw_vs_baseline": raw_rate - v2_scores["baseline_human_rate"],
        "delta_raw_vs_v2": raw_rate - v2_scores["finetuned_human_rate"],
    }
    print(f"\n=== STEP 1 Results ===")
    print(json.dumps(payload, indent=2))
    (EVAL_V3 / "scores_raw_base.json").write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {EVAL_V3 / 'scores_raw_base.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
