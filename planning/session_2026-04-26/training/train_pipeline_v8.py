"""V8: rank-128 LoRA from BASE on V6's multi-turn data — capacity test.

Hypothesis: V6 reached rank 64 / alpha 128 capacity. If we double rank
(rank 128, alpha 256) trained from base on the same multi-turn data,
we test "is the V*-arc continuation chain leaving capacity on the
table?" If V8 > V6 by ≥5pp, capacity matters for V9+. If V8 ≈ V6,
data is the limit, not capacity.

NOTE — corrected assumption: the next-session prompt described V8 as
"rank-32 from base." Reading the V6 adapter_config.json shows V6 is
already rank 64 (not rank 16 as the prompt assumed). Rank-32 from
base would be a DOWN-rank, not a capacity test. V8 is set to rank
128 to actually test the "capacity" hypothesis. Documented as a
plan deviation in V7_RESULTS §scope-cuts.

Variables vs V6:
  Starting LoRA: NONE (fresh from base)         was V4 continuation
  LoRA rank: 128                                was 64
  LoRA alpha: 256                                was 128
  Optimizer: adamw_8bit                          was adamw_torch
  Steps: 2200 (matches V4's budget)              was 1500

Held constant:
  Base, target_modules, dropout, data, lr, max_len, batch.

Output: checkpoints_v8/qwen25_3b_human_lora_v8/final/
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V8 = ROOT / "checkpoints_v8" / "qwen25_3b_human_lora_v8"
LOGS = ROOT / "logs_v8"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

LORA_R = 128
LORA_ALPHA = 256
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]

MAX_STEPS = 2200
PER_DEVICE_BATCH = 4
GRAD_ACCUM = 4
LR = 1e-4
WARMUP_RATIO = 0.02
MAX_LEN = 1024
LOGGING_STEPS = 20
EVAL_STEPS = 1000
SAVE_STEPS = 1000


def main() -> int:
    if (LOGS / "phase_train.done").exists():
        print("[v8-train] already done; skipping")
        return 0

    print("[v8-train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import load_dataset

    print(f"[v8-train] loading {BASE_MODEL} (4-bit)")
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
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)

    print(f"[v8-train] applying fresh rank-{LORA_R} LoRA")
    lora_cfg = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGETS, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    print("[v8-train] loading datasets")
    train_ds = load_dataset("json", data_files=str(TRAIN_FILE), split="train")
    eval_ds = load_dataset("json", data_files=str(EVAL_FILE), split="train")

    def to_text(ex):
        msgs = ex["messages"]
        return {"text": tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)}

    train_ds = train_ds.map(to_text, remove_columns=train_ds.column_names)
    eval_ds = eval_ds.map(to_text, remove_columns=eval_ds.column_names)

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=MAX_LEN, padding=False)

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=["text"])
    eval_ds = eval_ds.map(tokenize, batched=True, remove_columns=["text"])

    args = TrainingArguments(
        output_dir=str(CKPT_V8),
        max_steps=MAX_STEPS,
        per_device_train_batch_size=PER_DEVICE_BATCH,
        gradient_accumulation_steps=GRAD_ACCUM,
        per_device_eval_batch_size=PER_DEVICE_BATCH,
        learning_rate=LR,
        warmup_ratio=WARMUP_RATIO,
        lr_scheduler_type="cosine",
        logging_steps=LOGGING_STEPS,
        save_strategy="steps",
        save_steps=SAVE_STEPS,
        save_total_limit=2,
        eval_strategy="steps",
        eval_steps=EVAL_STEPS,
        bf16=True,
        gradient_checkpointing=True,
        report_to=[],
        seed=13579,
        optim="adamw_8bit",
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False, pad_to_multiple_of=8)
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        tokenizer=tok, data_collator=collator,
    )
    print("[v8-train] starting V8")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[v8-train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[v8-train] final eval: {final_metrics}")

    final_dir = CKPT_V8 / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V8 / "training_meta.json").write_text(json.dumps({
        "base_model": BASE_MODEL,
        "starting_lora": None,
        "lora_rank": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "lora_dropout": LORA_DROPOUT,
        "lora_targets": LORA_TARGETS,
        "data_format": "multi-turn windows (4-8 turns) — same as V6",
        "max_steps": MAX_STEPS,
        "lr": LR,
        "max_len": MAX_LEN,
        "effective_batch": PER_DEVICE_BATCH * GRAD_ACCUM,
        "optimizer": "adamw_8bit",
        "wallclock_seconds": elapsed,
        "train_metrics": train_result.metrics,
        "final_eval_metrics": final_metrics,
    }, indent=2))
    print(f"[v8-train] saved to {final_dir}")
    (LOGS / "phase_train.done").touch()
    print("V8 training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
