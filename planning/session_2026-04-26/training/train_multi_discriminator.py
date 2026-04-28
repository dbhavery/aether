"""STEP 2E: train multi-model DistilBERT discriminator.

Class 0 (AI): outputs from gemma4, qwen3:8b, raw Qwen2.5-3B base,
              V2 fine-tuned, V3-partial.
Class 1 (human): real turns from v3 corpora.

Saves to checkpoints_v4/discriminator_multi/final/.
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V4 = ROOT / "eval_v4"
OUT_DIR = ROOT / "checkpoints_v4" / "discriminator_multi"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEG_FILES = [
    ("gemma4", EVAL_V4 / "gen_gemma4.jsonl"),
    ("qwen3", EVAL_V4 / "gen_qwen3.jsonl"),
    ("base", EVAL_V4 / "gen_base.jsonl"),
    ("v2", EVAL_V4 / "gen_v2.jsonl"),
    ("v3", EVAL_V4 / "gen_v3.jsonl"),
]
POS_FILE = EVAL_V4 / "human_positives.jsonl"

MODEL_NAME = "distilbert-base-uncased"
MAX_LEN = 128
EPOCHS = 2
BATCH = 32
LR = 5e-5
SEED = 17


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        print(f"  WARNING: {path} missing")
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def main() -> int:
    import random
    random.seed(SEED)

    print("ensuring Ollama is dead before loading transformers")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    print("loading negatives:")
    neg_rows = []
    per_src_count: dict[str, int] = {}
    for label, path in NEG_FILES:
        items = load_jsonl(path)
        items = [r for r in items if r.get("output", "").strip()]
        print(f"  {label}: {len(items)} from {path.name}")
        for r in items:
            r["ai_source"] = label
            r["label"] = 0
            neg_rows.append(r)
            per_src_count[label] = per_src_count.get(label, 0) + 1
    print(f"  total negatives: {len(neg_rows)}")

    print("loading positives:")
    pos_rows = load_jsonl(POS_FILE)
    pos_rows = [r for r in pos_rows if r.get("output", "").strip()]
    for r in pos_rows:
        r["ai_source"] = "human"
        r["label"] = 1
    print(f"  total positives: {len(pos_rows)}")

    # Balance positives to roughly equal total negatives
    target_pos = len(neg_rows)
    if len(pos_rows) > target_pos:
        random.shuffle(pos_rows)
        pos_rows = pos_rows[:target_pos]
    print(f"  using {len(pos_rows)} positives, {len(neg_rows)} negatives")

    all_rows = neg_rows + pos_rows
    random.shuffle(all_rows)
    n_eval = max(500, len(all_rows) // 20)
    eval_rows = all_rows[:n_eval]
    train_rows = all_rows[n_eval:]
    print(f"  train {len(train_rows)} / eval {len(eval_rows)}")

    import torch
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              TrainingArguments, Trainer, DataCollatorWithPadding)
    from datasets import Dataset

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)

    def to_ds(rows):
        return Dataset.from_list([
            {"text": r["output"], "labels": r["label"], "ai_source": r["ai_source"]}
            for r in rows
        ])

    ds_train = to_ds(train_rows)
    ds_eval = to_ds(eval_rows)

    def tokenize(batch):
        return tok(batch["text"], truncation=True, max_length=MAX_LEN)

    ds_train = ds_train.map(tokenize, batched=True, remove_columns=["text", "ai_source"])
    ds_eval = ds_eval.map(tokenize, batched=True, remove_columns=["text", "ai_source"])

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=2)

    args = TrainingArguments(
        output_dir=str(OUT_DIR / "trainer"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH,
        per_device_eval_batch_size=BATCH,
        learning_rate=LR,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        logging_steps=50,
        report_to=[],
        seed=SEED,
        fp16=torch.cuda.is_available(),
    )

    def compute_metrics(eval_pred):
        import numpy as np
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = float((preds == labels).mean())
        # AI=0 / human=1
        tp = int(((preds == 1) & (labels == 1)).sum())
        fp = int(((preds == 1) & (labels == 0)).sum())
        fn = int(((preds == 0) & (labels == 1)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        return {"accuracy": acc, "precision_human": prec, "recall_human": rec}

    trainer = Trainer(
        model=model, args=args,
        train_dataset=ds_train, eval_dataset=ds_eval,
        tokenizer=tok,
        data_collator=DataCollatorWithPadding(tokenizer=tok),
        compute_metrics=compute_metrics,
    )
    trainer.train()
    final_metrics = trainer.evaluate()
    print(f"final metrics: {json.dumps(final_metrics, indent=2)}")

    final_dir = OUT_DIR / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tok.save_pretrained(str(final_dir))
    (OUT_DIR / "training_meta.json").write_text(json.dumps({
        "n_train": len(train_rows),
        "n_eval": len(eval_rows),
        "neg_per_source": per_src_count,
        "n_pos": len(pos_rows),
        "epochs": EPOCHS,
        "metrics": final_metrics,
    }, indent=2))
    print(f"wrote {final_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
