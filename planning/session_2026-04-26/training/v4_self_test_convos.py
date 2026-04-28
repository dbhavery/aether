"""V4-05: self-test multi-turn conversations.

Since real human panel testing isn't available, run V4 in extended
multi-turn conversations to surface failure modes that snippet-level
eval can't see:
  - Looping
  - Breaking character / AI-tells emerging in later turns
  - Topic drift
  - Register collapse (long-context regression to chitchat)

Pairs V4 with itself across 8 turns from each of N seed prompts.
Saves transcripts and discriminator scores for each turn position.

Output: eval_v4/self_test_transcripts.jsonl + self_test_summary.json
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

CKPT_V4 = ROOT / "checkpoints_v4" / "qwen25_3b_human_lora_v4" / "final"
DISCRIM_DIR = ROOT / "checkpoints_v4" / "discriminator_multi" / "final"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"

N_SEEDS = 25
TURNS_PER_CONVO = 8

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)


def main() -> int:
    EVAL_V4.mkdir(parents=True, exist_ok=True)
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
    print(f"  {len(seeds)} seed prompts")

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
    model = PeftModel.from_pretrained(base, str(CKPT_V4))
    model.eval()
    print("V4 ready")

    def gen_next(turns: list[dict], next_speaker: str) -> str:
        msgs = [{"role": "system", "content": SYSTEM}]
        # In our chat format, A=user, B=assistant. To make V4 generate
        # as next_speaker, the conversation history must end with the
        # other speaker. Since chat templates only support user/assistant
        # alternation, we always present A as user and B as assistant.
        # If next_speaker is A (user), V4 plays user; if B, V4 plays assistant.
        # Simpler: alternate roles strictly so the model never gets confused.
        for t in turns:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        # If next_speaker is A and last in turns is A (shouldn't happen), append empty user; etc.
        # Use add_generation_prompt to get the assistant continuation, then re-label.
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
        # ctx ends with A; generate 8 alternating turns
        history = list(ctx)
        for ti in range(TURNS_PER_CONVO):
            # Determine speaker: alternate from last; ensure pattern
            last_sp = history[-1]["speaker"] if history else "B"
            next_sp = "B" if last_sp == "A" else "A"
            # We need to feed V4 the conversation as user/assistant, where
            # the LAST message is "user" so V4 generates "assistant".
            # If next_sp = B and last_sp = A, that's natural (A=user → B=assistant).
            # If next_sp = A and last_sp = B, we have to flip the role mapping
            # for this single generation: invert by swapping speakers in history.
            if next_sp == "A":
                # Swap: A↔B for the chat template so model continues as 'A'
                tmp = [{"speaker": "B" if t["speaker"] == "A" else "A", "text": t["text"]}
                       for t in history]
                gen = gen_next(tmp, "A")
            else:
                gen = gen_next(history, "B")
            history.append({"speaker": next_sp, "text": gen.strip()})
        transcripts.append({
            "seed_idx": si,
            "seed_context": ctx,
            "full_transcript": history,
        })
    print(f"  done {len(transcripts)} transcripts in {time.time()-t0:.0f}s")

    out_jsonl = EVAL_V4 / "self_test_transcripts.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for t in transcripts:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"  wrote {out_jsonl}")

    del model, base
    torch.cuda.empty_cache()

    # Score each generated turn against the multi-discriminator,
    # broken down by turn-position (turn 1 is the first generated turn,
    # etc.) — surfaces register collapse over depth.
    print(f"loading discriminator from {DISCRIM_DIR}")
    clf = pipeline("text-classification", model=str(DISCRIM_DIR),
                   tokenizer=str(DISCRIM_DIR), device=0, top_k=None)

    by_turn_pos: dict[int, list[str]] = {}
    for t in transcripts:
        ctx_len = len(t["seed_context"])
        full = t["full_transcript"]
        for pos, turn in enumerate(full[ctx_len:], start=1):
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
        "n_seeds": len(transcripts),
        "turns_per_convo": TURNS_PER_CONVO,
        "by_turn_position": {
            f"turn_{pos}": human_rate(texts)
            for pos, texts in sorted(by_turn_pos.items())
        },
        "all_generated_turns": human_rate(
            [t["text"] for tr in transcripts for t in tr["full_transcript"][len(tr["seed_context"]):]]
        ),
    }
    out_summary = EVAL_V4 / "self_test_summary.json"
    out_summary.write_text(json.dumps(summary, indent=2))
    print(f"  wrote {out_summary}")
    print("\n=== Self-test summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
