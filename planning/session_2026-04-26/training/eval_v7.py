"""V7 eval: held-out + WildChat + multi-turn self-test against V4 multi-discriminator.

Same shape as eval_v6.py — only the adapter path and comparison row change.
Discriminator is the existing checkpoints_v4/discriminator_multi/final/
(single-turn DistilBERT). Apples-to-apples with V4/V5/V6 numbers.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V2 = ROOT / "eval_v2"
EVAL_V4 = ROOT / "eval_v4"
EVAL_V7 = ROOT / "eval_v7"
EVAL_V7.mkdir(parents=True, exist_ok=True)

CKPT_V7 = ROOT / "checkpoints_v7" / "qwen25_3b_human_lora_v7" / "final"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)

N_HELDOUT = 200
N_WILDCHAT = 200
N_SELFTEST_SEEDS = 25
TURNS_PER_CONVO = 8
LOGS = ROOT / "logs_v7"


def gen(prompts, model, tok, label):
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
        s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt").to(model.device)
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=80, do_sample=True,
                              top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        out.append(tok.decode(o[0][inp.input_ids.shape[1]:], skip_special_tokens=True).strip())
    print(f"  [{label}] done {len(out)} in {time.time()-t0:.0f}s")
    return out


def main():
    if (LOGS / "phase_eval.done").exists():
        print("[v7-eval] already done; skipping")
        return 0
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)
    if not CKPT_V7.exists():
        print(f"ERROR: V7 not found at {CKPT_V7}")
        return 1

    heldout = []
    with (EVAL_V2 / "eval_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                heldout.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    heldout = heldout[:N_HELDOUT]

    wildchat = []
    with (EVAL_V4 / "wildchat_holdout_prompts.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                wildchat.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    wildchat = wildchat[:N_WILDCHAT]
    seeds = heldout[:N_SELFTEST_SEEDS]

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
    model = PeftModel.from_pretrained(base, str(CKPT_V7))
    model.eval()
    print("V7 ready")

    h = gen(heldout, model, tok, "v7_heldout")
    w = gen(wildchat, model, tok, "v7_wildchat")

    def gen_next(history, next_sp):
        if next_sp == "A":
            history = [{"speaker": "B" if t["speaker"] == "A" else "A", "text": t["text"]}
                       for t in history]
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in history:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt").to(model.device)
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=80, do_sample=True,
                              top_p=0.9, temperature=0.85, pad_token_id=tok.pad_token_id)
        return tok.decode(o[0][inp.input_ids.shape[1]:], skip_special_tokens=True).strip()

    print("\n=== self-test ===")
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
            history.append({"speaker": next_sp, "text": gen_next(history, next_sp).strip()})
        transcripts.append({"seed_idx": si, "seed_context": ctx, "full_transcript": history})

    (EVAL_V7 / "v7_heldout_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(h)),
        encoding="utf-8",
    )
    (EVAL_V7 / "v7_wildchat_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(w)),
        encoding="utf-8",
    )
    (EVAL_V7 / "v7_self_test_transcripts.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in transcripts),
        encoding="utf-8",
    )

    del model, base
    torch.cuda.empty_cache()

    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    def score(texts):
        ne = [t for t in texts if t]
        if not ne:
            return {"n": 0, "human_rate": None}
        preds = clf(ne, truncation=True, padding=True, max_length=128, batch_size=64)
        n_h = 0
        confs = []
        for p in preds:
            sc = {x["label"]: x["score"] for x in p}
            confs.append(sc.get("LABEL_1", 0))
            if sc.get("LABEL_1", 0) > sc.get("LABEL_0", 0):
                n_h += 1
        return {"n": len(ne), "human_rate": n_h / len(ne),
                "avg_human_confidence": sum(confs) / len(confs)}

    by_pos = {}
    for t in transcripts:
        cl = len(t["seed_context"])
        for pos, turn in enumerate(t["full_transcript"][cl:], start=1):
            by_pos.setdefault(pos, []).append(turn["text"])

    payload = {
        "v7_heldout_score": score(h),
        "v7_wildchat_score": score(w),
        "v7_self_test_summary": {
            "n_seeds": len(transcripts),
            "turns_per_convo": TURNS_PER_CONVO,
            "by_turn_position": {f"turn_{p}": score(t) for p, t in sorted(by_pos.items())},
            "all_generated_turns": score(
                [t["text"] for tr in transcripts for t in tr["full_transcript"][len(tr["seed_context"]):]]
            ),
        },
        "comparison": {
            "v3_partial_heldout": 0.265, "v3_partial_wildchat": 0.16, "v3_partial_selftest_avg": 0.275,
            "v4_heldout": 0.220, "v4_wildchat": 0.235, "v4_selftest_avg": 0.350,
            "v5_heldout": 0.220, "v5_wildchat": 0.240, "v5_selftest_avg": 0.280,
            "v6_heldout": 0.230, "v6_wildchat": 0.280, "v6_selftest_avg": 0.330,
            "human_ceiling_sanity": 0.871,
        },
    }
    (EVAL_V7 / "v7_eval_results.json").write_text(json.dumps(payload, indent=2))
    print("\n=== V7 results ===")
    print(json.dumps(payload, indent=2))
    (LOGS / "phase_eval.done").touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
