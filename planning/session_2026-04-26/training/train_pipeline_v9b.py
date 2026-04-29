"""V9b: V8 continuation +1500 steps — training-budget test.

Hypothesis: V8 saturated at 1500 steps OR has more learnable signal in
the data. V9b loads V8's final adapter and trains 1500 more steps on
the same data with the same hyperparameters. If V9b > V8, the V8 budget
was insufficient and the V*-arc benefits from more steps. If V9b ≈ V8,
the architecture has saturated on this data.

Variables vs V8:
  Starting LoRA: V8 final (was None)
  Steps: 1500 MORE (so total 3000 from base)
  Otherwise identical to V8.

Output: checkpoints_v9b/qwen25_3b_human_lora_v9b/final/

Wallclock estimate: ~2.5 hr train (matches V8 step pace).
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V8_FINAL = ROOT / "checkpoints_v8" / "qwen25_3b_human_lora_v8" / "final"
CKPT_V9B = ROOT / "checkpoints_v9b" / "qwen25_3b_human_lora_v9b"
LOGS = ROOT / "logs_v9_sweep"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

# V8's LoRA shape — kept for clean continuation
LORA_R = 96
LORA_ALPHA = 192
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]

MAX_STEPS = 1500
PER_DEVICE_BATCH = 2
GRAD_ACCUM = 8
LR = 5e-5  # reduced (continuation; avoid catastrophic forgetting)
WARMUP_RATIO = 0.02
MAX_LEN = 1024
LOGGING_STEPS = 20
EVAL_STEPS = 750
SAVE_STEPS = 750

DONE_FLAG = LOGS / "phase_v9b_train.done"


def main() -> int:
    if DONE_FLAG.exists():
        print("[v9b-train] already done; skipping")
        return 0

    if not CKPT_V8_FINAL.exists():
        print(f"[v9b-train] FATAL: V8 final adapter not at {CKPT_V8_FINAL}")
        return 2

    print("[v9b-train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import PeftModel, prepare_model_for_kbit_training
    from datasets import load_dataset

    print(f"[v9b-train] loading {BASE_MODEL} (4-bit) + V8 LoRA from {CKPT_V8_FINAL}")
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
    model = PeftModel.from_pretrained(base, str(CKPT_V8_FINAL), is_trainable=True)
    model.print_trainable_parameters()

    print("[v9b-train] loading datasets")
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
        output_dir=str(CKPT_V9B),
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
        seed=11235,
        optim="adamw_8bit",
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False, pad_to_multiple_of=8)
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        tokenizer=tok, data_collator=collator,
    )
    print("[v9b-train] starting V9b (continuation from V8, 1500 more steps)")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[v9b-train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[v9b-train] final eval: {final_metrics}")

    final_dir = CKPT_V9B / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V9B / "training_meta.json").write_text(json.dumps({
        "variant": "v9b",
        "hypothesis": "training-budget test — V8 + 1500 more steps",
        "base_model": BASE_MODEL,
        "starting_lora": str(CKPT_V8_FINAL),
        "lora_rank": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "lora_dropout": LORA_DROPOUT,
        "lora_targets": LORA_TARGETS,
        "data_format": "multi-turn windows (4-8 turns) — same as V6/V8",
        "max_steps": MAX_STEPS,
        "lr": LR,
        "max_len": MAX_LEN,
        "effective_batch": PER_DEVICE_BATCH * GRAD_ACCUM,
        "optimizer": "adamw_8bit",
        "wallclock_seconds": elapsed,
        "train_metrics": train_result.metrics,
        "final_eval_metrics": final_metrics,
    }, indent=2))
    print(f"[v9b-train] saved to {final_dir}")
    DONE_FLAG.touch()
    print("V9b training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
