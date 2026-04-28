"""V6: multi-turn-format SFT continuation from V4.

Hypothesis from V5_RESULTS.md §4-5: V5's multi-turn regression
implicates the SFT data format, not the model capacity. V6 tests this
by training on multi-turn windows (full chat histories) instead of
(context → single response) pairs.

Variables held constant from V4:
  Base, LoRA shape, lr (1e-4), warmup ratio, schedule, batch size

Variable changed:
  Data: sft_train_v6.jsonl (30k multi-turn windows, 4-8 turns each)

Steps: 1500 (~75 min at observed pace) — shorter than V4's 2200
       to fit autonomous-session budget with margin.

Output: checkpoints_v6/qwen25_3b_human_lora_v6/final/
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V4 = ROOT / "checkpoints_v4" / "qwen25_3b_human_lora_v4" / "final"
CKPT_V6 = ROOT / "checkpoints_v6" / "qwen25_3b_human_lora_v6"
LOGS = ROOT / "logs_v6"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

MAX_STEPS = 1500
PER_DEVICE_BATCH = 4   # smaller because multi-turn windows are longer
GRAD_ACCUM = 4         # effective batch 16 same as V4
LR = 1e-4
WARMUP_RATIO = 0.02
MAX_LEN = 1024         # longer sequences for multi-turn windows
LOGGING_STEPS = 20
EVAL_STEPS = 750
SAVE_STEPS = 750


def main() -> int:
    if (LOGS / "phase_train.done").exists():
        print("[train] already done; skipping")
        return 0
    if not CKPT_V4.exists():
        raise FileNotFoundError(f"V4 LoRA not found at {CKPT_V4}")

    print("[train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import PeftModel, prepare_model_for_kbit_training
    from datasets import load_dataset

    print(f"[train] loading {BASE_MODEL} (4-bit)")
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

    print(f"[train] loading V4 LoRA from {CKPT_V4}")
    model = PeftModel.from_pretrained(base, str(CKPT_V4), is_trainable=True)
    for n, p in model.named_parameters():
        if "lora_" in n.lower() or "adapter" in n.lower():
            p.data = p.data.float()
            p.requires_grad = True
    model.print_trainable_parameters()

    print("[train] loading datasets")
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
        output_dir=str(CKPT_V6),
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
        seed=24680,
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False, pad_to_multiple_of=8)
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        tokenizer=tok, data_collator=collator,
    )
    print("[train] starting V6")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[train] final eval: {final_metrics}")

    final_dir = CKPT_V6 / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V6 / "training_meta.json").write_text(json.dumps({
        "base_model": BASE_MODEL,
        "starting_lora": str(CKPT_V4),
        "data_format": "multi-turn windows (4-8 turns)",
        "max_steps": MAX_STEPS,
        "lr": LR,
        "max_len": MAX_LEN,
        "effective_batch": PER_DEVICE_BATCH * GRAD_ACCUM,
        "wallclock_seconds": elapsed,
        "train_metrics": train_result.metrics,
        "final_eval_metrics": final_metrics,
    }, indent=2))
    print(f"[train] saved to {final_dir}")
    (LOGS / "phase_train.done").touch()
    print("V6 training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
