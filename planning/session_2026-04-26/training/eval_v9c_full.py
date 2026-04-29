"""V9c full eval — apples-to-apples with V4–V8 (multi-turn discriminator).

Same structure as eval_v8.py, but for V9c (Qwen2.5-7B + rank-32 LoRA).
Produces the WildChat human-rate number directly comparable to V6's
28% — the metric the V*-arc has been tracked on.

Held-out PPL was already shipped in eval_v9_quick.py; this run focuses
on the discriminator-scored signals (held-out human-rate, WildChat
human-rate, multi-turn self-test by position).

Wallclock estimate (RTX 3090 Ti, 7B 4-bit inference):
  Held-out gen   (200 prompts):                   ~25 min
  WildChat gen   (200 prompts):                   ~25 min
  Self-test gen  (25 seeds × 8 turns = 200 gens): ~25 min
  Discriminator scoring (DistilBERT, fast):       ~5 min
  ─────────────────────────────────────────────
  TOTAL                                            ~80–90 min unattended

Resumable: writes phase_eval.done flag in logs_v9c_full/. Re-running
after a partial crash skips the run if the flag exists. (Granular
mid-run resumability would need per-stage flags — deferred; the run
is short enough that a clean re-run is acceptable.)

Output: eval_v9c_full/{v9c_full_eval_results.json, v9c_full_*.jsonl,
                      v9c_full_self_test_transcripts.jsonl}
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
EVAL_V9C_FULL = ROOT / "eval_v9c_full"
EVAL_V9C_FULL.mkdir(parents=True, exist_ok=True)

CKPT_V9C = ROOT / "checkpoints_v9c" / "qwen25_7b_human_lora_v9c" / "final"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)

N_HELDOUT = 200
N_WILDCHAT = 200
N_SELFTEST_SEEDS = 25
TURNS_PER_CONVO = 8
LOGS = ROOT / "logs_v9c_full"
LOGS.mkdir(parents=True, exist_ok=True)
DONE_FLAG = LOGS / "phase_eval.done"


def gen(prompts, model, tok, label):
    import torch
    out = []
    t0 = time.time()
    for i, p in enumerate(prompts):
        if i % 25 == 0:
            print(f"  [{label}] {i}/{len(prompts)} ({time.time()-t0:.0f}s)", flush=True)
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt", truncation=True, max_length=1024).to(model.device)
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=80, do_sample=True,
                              top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        out.append(tok.decode(o[0][inp.input_ids.shape[1]:], skip_special_tokens=True).strip())
    print(f"  [{label}] done {len(out)} in {time.time()-t0:.0f}s", flush=True)
    return out


def main() -> int:
    if DONE_FLAG.exists():
        print("[v9c-full-eval] already done; skipping")
        return 0
    if not CKPT_V9C.exists():
        print(f"[v9c-full-eval] FATAL: V9c checkpoint missing at {CKPT_V9C}")
        return 2
    if not DISCRIM_DIR.exists():
        print(f"[v9c-full-eval] FATAL: V4 multi-discriminator missing at {DISCRIM_DIR}")
        return 2

    print("[v9c-full-eval] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    # Load eval prompts (same files V4–V8 used).
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

    print(f"[v9c-full-eval] loaded {len(heldout)} heldout, {len(wildchat)} wildchat, {len(seeds)} seeds")

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, pipeline)
    from peft import PeftModel

    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
    print(f"[v9c-full-eval] loading {BASE_MODEL} (4-bit)")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb_cfg, device_map="auto",
        trust_remote_code=True, attn_implementation="sdpa",
    )
    print(f"[v9c-full-eval] applying V9c LoRA from {CKPT_V9C}")
    model = PeftModel.from_pretrained(base, str(CKPT_V9C))
    model.eval()
    print("[v9c-full-eval] V9c ready")

    h = gen(heldout, model, tok, "v9c_heldout")
    w = gen(wildchat, model, tok, "v9c_wildchat")

    def gen_next(history, next_sp):
        if next_sp == "A":
            history = [{"speaker": "B" if t["speaker"] == "A" else "A", "text": t["text"]}
                       for t in history]
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in history:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        s = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp = tok(s, return_tensors="pt", truncation=True, max_length=1024).to(model.device)
        with torch.no_grad():
            o = model.generate(**inp, max_new_tokens=80, do_sample=True,
                              top_p=0.9, temperature=0.85, pad_token_id=tok.pad_token_id)
        return tok.decode(o[0][inp.input_ids.shape[1]:], skip_special_tokens=True).strip()

    print("\n=== self-test ===")
    transcripts = []
    t0 = time.time()
    for si, seed in enumerate(seeds):
        if si % 5 == 0:
            print(f"  seed {si}/{len(seeds)} ({time.time()-t0:.0f}s)", flush=True)
        ctx = list(seed["context"])
        history = list(ctx)
        for ti in range(TURNS_PER_CONVO):
            last_sp = history[-1]["speaker"] if history else "B"
            next_sp = "B" if last_sp == "A" else "A"
            history.append({"speaker": next_sp, "text": gen_next(history, next_sp).strip()})
        transcripts.append({"seed_idx": si, "seed_context": ctx, "full_transcript": history})

    (EVAL_V9C_FULL / "v9c_full_heldout_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(h)),
        encoding="utf-8",
    )
    (EVAL_V9C_FULL / "v9c_full_wildchat_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(w)),
        encoding="utf-8",
    )
    (EVAL_V9C_FULL / "v9c_full_self_test_transcripts.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in transcripts),
        encoding="utf-8",
    )

    del model, base
    torch.cuda.empty_cache()

    print("[v9c-full-eval] loading V4 multi-discriminator")
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
        "variant": "v9c_full",
        "checkpoint": str(CKPT_V9C),
        "base_model": BASE_MODEL,
        "v9c_heldout_score": score(h),
        "v9c_wildchat_score": score(w),
        "v9c_self_test_summary": {
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
            "v7_heldout": 0.195, "v7_wildchat": 0.235, "v7_selftest_avg": 0.340,
            "v8_heldout": 0.240, "v8_wildchat": 0.205, "v8_selftest_avg": 0.195,
            "human_ceiling_sanity": 0.871,
        },
    }
    (EVAL_V9C_FULL / "v9c_full_eval_results.json").write_text(json.dumps(payload, indent=2))
    print("\n=== V9c full results ===")
    print(json.dumps(payload, indent=2))
    DONE_FLAG.touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
