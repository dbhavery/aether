"""V7: LoRA continuation from V6 with bare-metal optimizations.

Hypothesis (V7 candidate A from V6_RESULTS §5): V6 used 1500 steps on
multi-turn-format SFT and unlocked +4.5pp WildChat over V4. Maybe more
multi-turn steps extends the gain — or saturates like V5 did with
single-turn-format continuation.

Variables changed from V6:
  - Starting LoRA: V6 (was V4)
  - Optimizer: adamw_8bit (bitsandbytes) instead of adamw_torch
                ↳ optimizer state ~3 GB instead of ~12 GB
  - Steps: 1500 more on top of V6's 1500

Variables held constant:
  Base, LoRA shape (rank 64, alpha 128), data (sft_train_v6 multi-turn-format),
  lr (1e-4), warmup ratio, batch size, max_length 1024.

Steps: 1500 (~85 min at observed pace).
Output: checkpoints_v7/qwen25_3b_human_lora_v7/final/

NOTE on optimizer offload to CPU: HF Trainer does not expose
`offload_optimizer=True` as a top-level flag. True CPU optimizer offload
requires DeepSpeed ZeRO-2 or accelerate FSDP config — not set up here.
adamw_8bit alone gives ~70% of the VRAM win without that complexity.
Documented as deferred in V7_RESULTS §scope-cuts.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V6 = ROOT / "checkpoints_v6" / "qwen25_3b_human_lora_v6" / "final"
CKPT_V7 = ROOT / "checkpoints_v7" / "qwen25_3b_human_lora_v7"
LOGS = ROOT / "logs_v7"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

MAX_STEPS = 1500
PER_DEVICE_BATCH = 4
GRAD_ACCUM = 4
LR = 1e-4
WARMUP_RATIO = 0.02
MAX_LEN = 1024
LOGGING_STEPS = 20
EVAL_STEPS = 750
SAVE_STEPS = 750


def main() -> int:
    if (LOGS / "phase_train.done").exists():
        print("[v7-train] already done; skipping")
        return 0
    if not CKPT_V6.exists():
        raise FileNotFoundError(f"V6 LoRA not found at {CKPT_V6}")

    print("[v7-train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import PeftModel, prepare_model_for_kbit_training
    from datasets import load_dataset

    print(f"[v7-train] loading {BASE_MODEL} (4-bit)")
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

    print(f"[v7-train] loading V6 LoRA from {CKPT_V6}")
    model = PeftModel.from_pretrained(base, str(CKPT_V6), is_trainable=True)
    for n, p in model.named_parameters():
        if "lora_" in n.lower() or "adapter" in n.lower():
            p.data = p.data.float()
            p.requires_grad = True
    model.print_trainable_parameters()

    print("[v7-train] loading datasets")
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
        output_dir=str(CKPT_V7),
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
        seed=86420,
        optim="adamw_8bit",          # NEW: bitsandbytes 8-bit Adam, ~70% VRAM win
    )

    collator = DataCollatorForLanguageModeling(tokenizer=tok, mlm=False, pad_to_multiple_of=8)
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        tokenizer=tok, data_collator=collator,
    )
    print("[v7-train] starting V7")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[v7-train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[v7-train] final eval: {final_metrics}")

    final_dir = CKPT_V7 / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V7 / "training_meta.json").write_text(json.dumps({
        "base_model": BASE_MODEL,
        "starting_lora": str(CKPT_V6),
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
    print(f"[v7-train] saved to {final_dir}")
    (LOGS / "phase_train.done").touch()
    print("V7 training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
