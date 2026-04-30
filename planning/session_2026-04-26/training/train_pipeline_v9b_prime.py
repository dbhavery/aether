"""V9b': V6 chain + rank-96 expansion — Path B from V9C_FULL_RESULTS §5.

Hypothesis: the V4 → V5 → V6 continuation chain is the WildChat lever,
not the data format alone or rank alone. V9b' tests this by:

  1. Loading the V6 adapter (the current WildChat ceiling at 28.0%).
  2. Merging V6 LoRA into base weights in-memory ("route 1" per the
     V9c doc — cleaner semantics, lower implementation risk than
     `add_weighted_adapter`).
  3. Applying a fresh rank-96 LoRA on top of the V6-merged base.
  4. Training 1500 steps on the same multi-turn-format data V6/V7/V8
     trained on.

Decision matrix (per V9C_FULL_RESULTS §6):

  V9b' WildChat ≥ 28%  → continuation chain + capacity is the lever.
                         V10 picks up here at higher rank or longer
                         schedule. V*-arc continues on 3B.
  V9b' WildChat < 28%  → V6 is the absolute ceiling on 3B regardless
                         of rank. Path A (V9c-3000) becomes the next
                         test for the 7B viability question. Path D
                         (ship V6, freeze V*-arc) becomes the right
                         call if Path A also lands short.

Variables vs V8:
  Starting LoRA: V6 final, MERGED into base (was None → fresh-from-base)
  LoRA rank: 96 (matches V8/V9b)
  Steps: 1500 (matches V8 single-pass budget)
  Data: same multi-turn-format as V6/V7/V8/V9b
  Optimizer: adamw_8bit (matches V7/V8/V9b)

Output: checkpoints_v9b_prime/qwen25_3b_human_lora_v9b_prime/final/

Wallclock estimate: ~3-4 hr unattended on RTX 3090 Ti. Higher than V8/V9b
because the V6 merge + bf16 base path can't use 4-bit quantization
(peft's merge_and_unload doesn't compose cleanly with bnb 4-bit). Run
loads ~6 GB bf16 base + rank-96 LoRA + activations; expect ~14-16 GB
peak VRAM at PER_DEVICE_BATCH=1 with gradient_checkpointing.

Resumable: checkpoint every 500 steps; safe to kill mid-run and restart.

Implementation note: merge_and_unload before applying the fresh LoRA so
the V6 priors are baked into the base weights. The new rank-96 LoRA
trains from a "warm" model that already has V6's WildChat lift, and
should learn deltas on top rather than relearning from scratch (the V8
fresh-from-base failure mode).
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CKPT_V6_FINAL = ROOT / "checkpoints_v6" / "qwen25_3b_human_lora_v6" / "final"
CKPT_V9B_PRIME = ROOT / "checkpoints_v9b_prime" / "qwen25_3b_human_lora_v9b_prime"
LOGS = ROOT / "logs_v9b_prime"
LOGS.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
TRAIN_FILE = DATA / "sft_train_v6.jsonl"
EVAL_FILE = DATA / "sft_eval_v6.jsonl"

# Rank-96 matches V8/V9b for direct cross-comparison. Alpha 192 keeps
# the alpha/rank ratio at 2× consistent with V8's recipe.
LORA_R = 96
LORA_ALPHA = 192
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]

# 1500 steps matches V8 single-pass budget. The whole point of this
# experiment is "what does fresh rank-96 look like when it's trained on
# top of V6's priors instead of fresh-from-base?" Holding step budget
# constant isolates the chain variable.
MAX_STEPS = 1500
PER_DEVICE_BATCH = 1
GRAD_ACCUM = 16  # → effective batch 16, matches V8's effective batch
LR = 5e-5  # matches V9b's continuation LR (avoids catastrophic forgetting)
WARMUP_RATIO = 0.02
MAX_LEN = 1024
LOGGING_STEPS = 20
EVAL_STEPS = 500
SAVE_STEPS = 500

DONE_FLAG = LOGS / "phase_v9b_prime_train.done"


def main() -> int:
    if DONE_FLAG.exists():
        print("[v9b'-train] already done; skipping")
        return 0

    if not CKPT_V6_FINAL.exists():
        print(f"[v9b'-train] FATAL: V6 final adapter not at {CKPT_V6_FINAL}")
        return 2

    # Free up VRAM/RAM that other GPU consumers might hold. Same dance
    # the v8/v9b scripts do.
    print("[v9b'-train] killing ollama")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              TrainingArguments,
                              DataCollatorForLanguageModeling, Trainer)
    from peft import (PeftModel, LoraConfig, get_peft_model,
                      prepare_model_for_kbit_training)
    from datasets import load_dataset

    # ─── STEP 1: Load base in bf16 (NOT 4-bit). ───────────────────────
    # peft.merge_and_unload does not compose cleanly with bitsandbytes
    # 4-bit quantized weights — the merge requires writing back to the
    # base linear layers, which the bnb wrapper short-circuits. bf16 on
    # a 3B model fits comfortably in a 24 GB 3090 Ti at our batch size.
    print(f"[v9b'-train] loading {BASE_MODEL} in bf16 (no quantization, "
          f"required for merge_and_unload)")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )

    # ─── STEP 2: Load V6 LoRA + merge into base. ──────────────────────
    print(f"[v9b'-train] loading V6 LoRA from {CKPT_V6_FINAL}")
    v6_model = PeftModel.from_pretrained(base, str(CKPT_V6_FINAL), is_trainable=False)
    print("[v9b'-train] merging V6 LoRA into base weights (route 1)")
    merged = v6_model.merge_and_unload()
    # `merged` is now a plain HF model with V6's deltas baked in.
    # Drop the peft wrapper so the next get_peft_model call layers a
    # fresh (rank-96) adapter without conflicting with the merged one.
    del v6_model

    # ─── STEP 3: Prep for k-bit-style training. ───────────────────────
    # We're not actually in k-bit mode (loaded bf16), but
    # prepare_model_for_kbit_training handles cast-to-fp32 on the
    # output_layer + gradient checkpointing + input_require_grads
    # hooks the same way and is safe on bf16 models.
    merged = prepare_model_for_kbit_training(merged, use_gradient_checkpointing=True)

    # ─── STEP 4: Apply fresh rank-96 LoRA. ────────────────────────────
    print(f"[v9b'-train] attaching fresh rank-{LORA_R} LoRA "
          f"(alpha={LORA_ALPHA}, targets={LORA_TARGETS})")
    lora_cfg = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGETS,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(merged, lora_cfg)
    model.print_trainable_parameters()

    # ─── STEP 5: Datasets — same multi-turn format as V6/V7/V8/V9b. ──
    print("[v9b'-train] loading datasets")
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

    # ─── STEP 6: Train. ───────────────────────────────────────────────
    args = TrainingArguments(
        output_dir=str(CKPT_V9B_PRIME),
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
    print("[v9b'-train] starting V9b' (V6 chain + rank-96 expansion)")
    t0 = time.time()
    train_result = trainer.train()
    elapsed = time.time() - t0
    print(f"[v9b'-train] done in {elapsed:.0f}s")
    final_metrics = trainer.evaluate()
    print(f"[v9b'-train] final eval: {final_metrics}")

    # ─── STEP 7: Save. ────────────────────────────────────────────────
    final_dir = CKPT_V9B_PRIME / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (CKPT_V9B_PRIME / "training_meta.json").write_text(json.dumps({
        "variant": "v9b_prime",
        "hypothesis": "V*-arc chain hypothesis — V6 + rank-96 expansion via merge_and_unload",
        "path_label": "Path B from V9C_FULL_RESULTS §5",
        "base_model": BASE_MODEL,
        "starting_lora_merged": str(CKPT_V6_FINAL),
        "lora_rank": LORA_R,
        "lora_alpha": LORA_ALPHA,
        "lora_dropout": LORA_DROPOUT,
        "lora_targets": LORA_TARGETS,
        "data_format": "multi-turn windows (4-8 turns) — same as V6/V7/V8/V9b",
        "max_steps": MAX_STEPS,
        "lr": LR,
        "max_len": MAX_LEN,
        "effective_batch": PER_DEVICE_BATCH * GRAD_ACCUM,
        "optimizer": "adamw_8bit",
        "merge_route": "1 (peft.merge_and_unload, bf16 base)",
        "wallclock_seconds": elapsed,
        "train_metrics": train_result.metrics,
        "final_eval_metrics": final_metrics,
    }, indent=2))
    print(f"[v9b'-train] saved to {final_dir}")
    DONE_FLAG.touch()
    print("V9b' training complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
