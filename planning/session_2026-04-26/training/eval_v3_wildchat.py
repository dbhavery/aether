"""Score V3-partial against WildChat held-outs (was missed in prelaunch eval).

Apples-to-apples vs V4_wildchat_score=0.235.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V4 = ROOT / "eval_v4"
EVAL_V3 = ROOT / "eval_v3"
CKPT_V3 = ROOT / "checkpoints_v3" / "qwen25_3b_human_lora_v3" / "final_partial_3000"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def main():
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    prompts = []
    with (EVAL_V4 / "wildchat_holdout_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                prompts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    prompts = prompts[:200]
    print(f"  {len(prompts)} WildChat prompts")

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, pipeline)
    from peft import PeftModel
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
    model = PeftModel.from_pretrained(base, str(CKPT_V3))
    model.eval()
    print("V3-partial loaded")

    outs = []
    t0 = time.time()
    for i, p in enumerate(prompts):
        if i % 25 == 0:
            print(f"  {i}/{len(prompts)} ({time.time()-t0:.0f}s)")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        prompt_str = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_str, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=80, do_sample=True,
                                  top_p=0.9, temperature=0.8,
                                  pad_token_id=tok.pad_token_id)
        text = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        outs.append(text)
    print(f"  done {len(outs)} in {time.time()-t0:.0f}s")

    (EVAL_V3 / "v3_partial_wildchat_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(outs)),
        encoding="utf-8",
    )

    del model, base
    torch.cuda.empty_cache()

    print(f"loading discriminator from {DISCRIM_DIR}")
    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)
    non_empty = [t for t in outs if t]
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

    payload = {
        "n": len(non_empty),
        "human_rate": n_human / len(non_empty),
        "avg_human_confidence": sum(confs) / len(confs),
    }
    print("V3-partial WildChat:", json.dumps(payload, indent=2))
    (EVAL_V3 / "v3_partial_wildchat_score.json").write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
