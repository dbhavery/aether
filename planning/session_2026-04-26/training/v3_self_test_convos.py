"""V3-partial self-test multi-turn — apples-to-apples baseline for V4 self-test."""
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
CKPT_V3 = ROOT / "checkpoints_v3" / "qwen25_3b_human_lora_v3" / "final_partial_3000"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

N_SEEDS = 25
TURNS_PER_CONVO = 8

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def main():
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    seeds = []
    with (EVAL_V2 / "eval_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                seeds.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    seeds = seeds[:N_SEEDS]

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

    def gen_next(history, next_sp):
        if next_sp == "A":
            tmp = [{"speaker": "B" if t["speaker"] == "A" else "A", "text": t["text"]}
                   for t in history]
            history = tmp
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in history:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        prompt_str = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_str, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outs = model.generate(**inputs, max_new_tokens=80, do_sample=True,
                                  top_p=0.9, temperature=0.85,
                                  pad_token_id=tok.pad_token_id)
        return tok.decode(outs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    transcripts = []
    t0 = time.time()
    for si, seed in enumerate(seeds):
        if si % 5 == 0:
            print(f"  seed {si}/{len(seeds)} ({time.time()-t0:.0f}s)")
        ctx = list(seed["context"])
        history = list(ctx)
        for ti in range(TURNS_PER_CONVO):
            last_sp = history[-1]["speaker"] if history else "B"
            next_sp = "B" if last_sp == "A" else "A"
            gen = gen_next(history, next_sp)
            history.append({"speaker": next_sp, "text": gen.strip()})
        transcripts.append({"seed_idx": si, "seed_context": ctx, "full_transcript": history})
    print(f"  done {len(transcripts)} in {time.time()-t0:.0f}s")

    out_jsonl = EVAL_V3 / "v3_partial_self_test_transcripts.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for t in transcripts:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    del model, base
    torch.cuda.empty_cache()

    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    by_turn_pos = {}
    for t in transcripts:
        ctx_len = len(t["seed_context"])
        for pos, turn in enumerate(t["full_transcript"][ctx_len:], start=1):
            by_turn_pos.setdefault(pos, []).append(turn["text"])

    def human_rate(texts):
        non_empty = [t for t in texts if t]
        if not non_empty:
            return None
        preds = clf(non_empty, truncation=True, padding=True,
                    max_length=128, batch_size=64)
        n_human = 0
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
            if scores.get("LABEL_1", 0) > scores.get("LABEL_0", 0):
                n_human += 1
        return {"n": len(non_empty), "human_rate": n_human / len(non_empty)}

    summary = {
        "model": "v3-partial",
        "n_seeds": len(transcripts),
        "turns_per_convo": TURNS_PER_CONVO,
        "by_turn_position": {f"turn_{p}": human_rate(t) for p, t in sorted(by_turn_pos.items())},
        "all_generated_turns": human_rate(
            [t["text"] for tr in transcripts for t in tr["full_transcript"][len(tr["seed_context"]):]]
        ),
    }
    out = EVAL_V3 / "v3_partial_self_test_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print("V3 self-test:", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
