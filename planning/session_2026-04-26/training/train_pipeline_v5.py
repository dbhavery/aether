"""V5: LoRA continuation from V4 — tests whether more training extends V4's gains
or whether rank-16 LoRA is saturating.

Per V4_RESULTS.md §4 decision rule: V4 → V3-partial gain was +7.5pp on
real signals (WildChat, multi-turn). 5-10pp band → continue LoRA with
more steps + same broad mix.

Plan:
  Base:     Qwen2.5-3B-Instruct (4-bit nf4)
  LoRA:     load V4 final/ as starting adapter (is_trainable=True)
  Data:     same data/sft_train_v4.jsonl (53.9k pairs, broad mix)
  Steps:    2200 more (~108 min at observed 2.94s/step)
  LR:       5e-5 (lower than V4's 1e-4 since model already moved)
  Save:     checkpoints_v5/qwen25_3b_human_lora_v5/

Hard-fail conditions: train loss spikes >2.0 sustained → abort.
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
CKPT_V5 = ROOT / "checkpoints_v5" / "qwen25_3b_human_lora_v5"
LOGS = ROOT / "logs_v5"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v4.jsonl"
EVAL_FILE = DATA / "sft_eval_v4.jsonl"

MAX_STEPS = 2200
PER_DEVICE_BATCH = 8
GRAD_ACCUM = 2  # effective 16
LR = 5e-5
WARMUP_RATIO = 0.02
MAX_LEN = 768
LOGGING_STEPS = 20
EVAL_STEPS = 1100
SAVE_STEPS = 1000


def phase_done(name: str) -> bool:
    return (LOGS / f"phase_{name}.done").exists()


def mark_done(name: str) -> None:
    (LOGS / f"phase_{name}.done").touch()


def main() -> int:
    if phase_done("train"):
        print("[train] already done; skipping")
        return 0
    if not CKPT_V4.exists():
        raise FileNotFoundError(f"V4 LoRA not found at {CKPT_V4}")

    print("[train] killing ollama to free VRAM")
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

    print(f"[train] loading V4 LoRA adapter from {CKPT_V4}")
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
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        return {"text": text}

    train_ds = train_ds.map(to_text, remove_columns=train_ds.column_names)
    eval_ds = eval_ds.map(to_text, remove_columns=eval_ds.column_names)

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=MAX_LEN, padding=False)

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=["text"])
    eval_ds = eval_ds.map(tokenize, batched=True, remove_columns=["text"])

    args = TrainingArguments(
        output_dir=str(CKPT_V5),
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
        seed=98765,
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False,
                                               pad_to_multiple_of=8)
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        tokenizer=tok,
        data_collator=collator,
    )
    print("[train] starting V5")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[train] done in {elapsed:.0f}s")
    print(f"[train] metrics: {train_result.metrics}")
    final_metrics = trainer.evaluate()
    print(f"[train] final eval: {final_metrics}")

    final_dir = CKPT_V5 / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V5 / "training_meta.json").write_text(json.dumps({
        "base_model": BASE_MODEL,
        "starting_lora": str(CKPT_V4),
        "max_steps": MAX_STEPS,
        "lr": LR,
        "warmup_ratio": WARMUP_RATIO,
        "max_len": MAX_LEN,
        "effective_batch": PER_DEVICE_BATCH * GRAD_ACCUM,
        "wallclock_seconds": elapsed,
        "train_metrics": train_result.metrics,
        "final_eval_metrics": final_metrics,
    }, indent=2))
    print(f"[train] saved to {final_dir}")
    mark_done("train")
    print("V5 training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
