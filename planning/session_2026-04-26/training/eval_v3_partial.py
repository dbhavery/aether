"""Quick eval: score v3 checkpoint-3000 against the v2 discriminator.

Tests the hypothesis: "v3 partial training already saturates the
v2 (gemma4-trained) discriminator." If yes, the discriminator is the
eval bottleneck and finishing v3 won't tell us anything new.

Reuses:
- v2 discriminator: checkpoints_v2/discriminator_distilbert/final
- v3 base model + checkpoint-3000 LoRA
- v2 eval_prompts.jsonl  (or rebuild from v3 normalized eval — using v2 for 1:1 comparability)
- gemma4:e4b baseline outputs already in eval_v2/baseline_outputs.jsonl

Output: eval_v3/scores_partial_3000.json
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V2 = ROOT / "checkpoints_v2"
CKPT_V3 = ROOT / "checkpoints_v3"
EVAL_V3 = ROOT / "eval_v3"
EVAL_V3.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
LORA_DIR = CKPT_V3 / "qwen25_3b_human_lora_v3" / "final_partial_3000"
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
    from peft import PeftModel

    print(f"loading base + LoRA from {LORA_DIR}")
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
    model = PeftModel.from_pretrained(base, str(LORA_DIR))
    model.eval()
    print("model ready")

    finetuned_outs = []
    t0 = time.time()
    for i, p in enumerate(eval_prompts):
        if i % 25 == 0:
            print(f"  v3-partial gen {i}/{len(eval_prompts)} ({time.time()-t0:.0f}s)")
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
        finetuned_outs.append(text)
    print(f"  {len(finetuned_outs)} v3-partial outputs in {time.time()-t0:.0f}s")
    (EVAL_V3 / "v3_partial_3000_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(finetuned_outs)),
        encoding="utf-8",
    )

    del model, base
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

    v3_partial_rate = score_set([o for o in finetuned_outs if o])
    # Reuse already-computed v2 baseline gemma4 + v2 finetuned scores
    v2_scores = json.loads((ROOT / "eval_v2" / "scores.json").read_text(encoding="utf-8"))
    payload = {
        "n_eval_prompts": len(eval_prompts),
        "baseline_gemma4_human_rate": v2_scores["baseline_human_rate"],
        "v2_finetuned_human_rate": v2_scores["finetuned_human_rate"],
        "v3_partial_3000_human_rate": v3_partial_rate,
        "delta_v3p_vs_baseline": v3_partial_rate - v2_scores["baseline_human_rate"],
        "delta_v3p_vs_v2": v3_partial_rate - v2_scores["finetuned_human_rate"],
    }
    print(f"\n=== Results ===")
    print(json.dumps(payload, indent=2))
    (EVAL_V3 / "scores_partial_3000.json").write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {EVAL_V3 / 'scores_partial_3000.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
