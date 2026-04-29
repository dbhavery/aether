"""V9c: 7B base swap, fresh rank-32 LoRA — base-size capacity test.

Hypothesis: 3B is the architectural ceiling. If V9c on Qwen2.5-7B
shows ≥5pp WildChat or held-out-PPL gain over V8, the V*-arc should
move to 7B base for V10. If V9c ≈ V8 despite the bigger base, the
V*-arc data is the limit, not the base size.

Variables vs V8:
  base_model: Qwen2.5-7B-Instruct (was 3B)
  LoRA rank: 32 (was 96)         — kept small for VRAM safety on 7B
  LoRA alpha: 64                  — 2x rank ratio
  per_device_batch: 1 (was 2)
  grad_accum: 16 (was 8)
  max_len: 768                    — shorter context for VRAM safety
  Otherwise identical training shape.

VRAM safety note: 7B in 4-bit nf4 ≈ 4.0 GB weights, plus
activations + adamw_8bit optimizer + LoRA params + gradient
checkpointing overhead. Targeting ~22 GB of 24 GB available.
If OOM at first batch, the orchestrator will surface the failure
quickly (within ~5 min) — not a 6-hour silent burn.

Output: checkpoints_v9c/qwen25_7b_human_lora_v9c/final/

Wallclock estimate: ~9 hr train (3x 3B model size).
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V9C = ROOT / "checkpoints_v9c" / "qwen25_7b_human_lora_v9c"
LOGS = ROOT / "logs_v9_sweep"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

LORA_R = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]

MAX_STEPS = 1500
PER_DEVICE_BATCH = 1
GRAD_ACCUM = 16
LR = 1e-4
WARMUP_RATIO = 0.02
MAX_LEN = 768
LOGGING_STEPS = 20
EVAL_STEPS = 750
SAVE_STEPS = 750

DONE_FLAG = LOGS / "phase_v9c_train.done"


def main() -> int:
    if DONE_FLAG.exists():
        print("[v9c-train] already done; skipping")
        return 0

    print("[v9c-train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import load_dataset

    print(f"[v9c-train] loading {BASE_MODEL} (4-bit)")
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

    print(f"[v9c-train] applying fresh rank-{LORA_R} LoRA on 7B base")
    lora_cfg = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGETS, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    print("[v9c-train] loading datasets")
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
        output_dir=str(CKPT_V9C),
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
        optim="adamw_8bit",
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False, pad_to_multiple_of=8)
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        tokenizer=tok, data_collator=collator,
    )
    print("[v9c-train] starting V9c (7B base swap)")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[v9c-train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[v9c-train] final eval: {final_metrics}")

    final_dir = CKPT_V9C / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V9C / "training_meta.json").write_text(json.dumps({
        "variant": "v9c",
        "hypothesis": "7B base swap — base-size capacity test",
        "base_model": BASE_MODEL,
        "starting_lora": None,
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
    print(f"[v9c-train] saved to {final_dir}")
    DONE_FLAG.touch()
    print("V9c training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
