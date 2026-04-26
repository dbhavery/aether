"""Human-indistinguishable conversation model training pipeline.

Self-contained driver. Runs all phases sequentially. Each phase
writes a marker file to logs/ on completion. If a phase has
already completed (marker present), it is skipped on re-run —
so this script is safe to interrupt and resume.

Phases:
  1 setup              — verify env, write STATUS.md
  2 download_corpora   — pull human-human dialog datasets from HF
  3 normalize          — common turn-row schema, language filter
  4 format_sft         — ChatML pair formatting + train/eval split
  5 train_lora         — QLoRA fine-tune Qwen2.5-7B on SFT data
  6 train_discriminator — DistilBERT classifier (human vs AI)
  7 eval               — gen baseline + finetuned outputs, classify, score
  8 writeup            — human-readable findings doc

Usage:
  python train_pipeline.py            # run all phases sequentially
  python train_pipeline.py --phase 5  # run specific phase
  python train_pipeline.py --status   # print STATUS.md and exit
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODELS = ROOT / "models"
CKPT = ROOT / "checkpoints"
EVAL = ROOT / "eval"
LOGS = ROOT / "logs"
STATUS = ROOT / "STATUS.md"

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DISCRIM_MODEL = "distilbert-base-uncased"

PHASES = [
    "setup",
    "download_corpora",
    "normalize",
    "format_sft",
    "train_lora",
    "train_discriminator",
    "eval",
    "writeup",
]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log(msg: str) -> None:
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "pipeline.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def marker_path(phase: str) -> Path:
    return LOGS / f"phase_{phase}.done"


def is_done(phase: str) -> bool:
    return marker_path(phase).exists()


def mark_done(phase: str, payload: dict | None = None) -> None:
    marker_path(phase).write_text(
        json.dumps({"phase": phase, "completed_at": now_iso(), **(payload or {})}, indent=2),
        encoding="utf-8",
    )


def update_status(current_phase: str, state: str, extra: str = "") -> None:
    """STATUS.md is the single-source-of-truth for unattended monitoring."""
    completed = [p for p in PHASES if is_done(p)]
    pending = [p for p in PHASES if not is_done(p)]
    lines = [
        "# Training Pipeline Status",
        "",
        f"**Updated:** {now_iso()}",
        f"**Current phase:** {current_phase} — {state}",
        "",
        "## Completed",
    ]
    for p in completed:
        m = json.loads(marker_path(p).read_text(encoding="utf-8"))
        lines.append(f"- [x] {p} (at {m['completed_at']})")
    lines.append("")
    lines.append("## Pending")
    for p in pending:
        marker = "[>]" if p == current_phase else "[ ]"
        lines.append(f"- {marker} {p}")
    if extra:
        lines.append("")
        lines.append("## Notes")
        lines.append(extra)
    STATUS.write_text("\n".join(lines), encoding="utf-8")


# ========== Phase 1: setup ==========

def phase_setup() -> None:
    log("Phase 1: setup — verifying environment")
    update_status("setup", "verifying deps")
    import torch
    import transformers
    import peft
    import trl
    import datasets as hfds
    import bitsandbytes
    import accelerate
    payload = {
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "vram_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if torch.cuda.is_available() else 0,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "trl": trl.__version__,
        "datasets": hfds.__version__,
        "bitsandbytes": bitsandbytes.__version__,
        "accelerate": accelerate.__version__,
        "base_model": BASE_MODEL,
        "discriminator_model": DISCRIM_MODEL,
    }
    log(f"  env: {json.dumps(payload, indent=2)}")
    for d in (DATA, MODELS, CKPT, EVAL, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    mark_done("setup", payload)


# ========== Phase 2: download_corpora ==========

# (name, hf_path, license_tier, role)
# license_tier: 'shippable' = can train + ship model; 'eval_only' = NC license
CORPORA = [
    ("personachat",        "AlekseyKorshuk/persona-chat",       "shippable", "train+eval"),
    ("blended_skill",      "ParlAI/blended_skill_talk",         "shippable", "train+eval"),
    ("daily_dialog",       "roskoN/dailydialog",                "eval_only", "eval"),
    ("empathetic",         "Adapting/empathetic_dialogues_v2",  "eval_only", "eval"),
    ("topical_chat",       "Fishball02/topical-chat",           "shippable", "train+eval"),
    ("soda",               "allenai/soda",                      "shippable", "train+eval"),
]


def phase_download_corpora() -> None:
    log("Phase 2: download_corpora — pulling HF datasets")
    update_status("download_corpora", "downloading")
    from datasets import load_dataset, DatasetDict
    summary = {}
    for name, hf_path, license_tier, role in CORPORA:
        out_dir = DATA / name
        if out_dir.exists() and (out_dir / ".success").exists():
            log(f"  {name}: cached, skipping")
            summary[name] = {"status": "cached", "license": license_tier, "role": role}
            continue
        log(f"  {name}: loading {hf_path}")
        try:
            ds = load_dataset(hf_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            ds.save_to_disk(str(out_dir))
            (out_dir / ".success").touch()
            n = sum(len(s) for s in ds.values()) if isinstance(ds, DatasetDict) else len(ds)
            log(f"  {name}: ok, {n} rows")
            summary[name] = {"status": "ok", "rows": n, "license": license_tier, "role": role, "splits": list(ds.keys()) if isinstance(ds, DatasetDict) else ["train"]}
        except Exception as e:
            log(f"  {name}: FAIL — {type(e).__name__}: {e}")
            summary[name] = {"status": "fail", "error": f"{type(e).__name__}: {e}", "license": license_tier, "role": role}
    log(f"  download summary: {json.dumps(summary, indent=2)}")
    mark_done("download_corpora", summary)


# ========== Phase 3: normalize ==========

def phase_normalize() -> None:
    """Convert each downloaded dataset into a unified JSONL of
    {source, conversation_id, turns: [{speaker, text}]} where speaker
    is 'A' or 'B' (alternating). Language-filter to English.
    """
    log("Phase 3: normalize — unified schema")
    update_status("normalize", "normalizing")
    from datasets import load_from_disk
    out_path = DATA / "normalized.jsonl"
    out_path_train = DATA / "normalized_train.jsonl"  # shippable only
    out_path_eval = DATA / "normalized_eval.jsonl"     # all
    n_total = 0
    by_source = {}
    with out_path.open("w", encoding="utf-8") as fall, \
         out_path_train.open("w", encoding="utf-8") as ftrain, \
         out_path_eval.open("w", encoding="utf-8") as feval:
        for name, hf_path, license_tier, role in CORPORA:
            in_dir = DATA / name
            if not (in_dir / ".success").exists():
                log(f"  {name}: skip (not downloaded)")
                continue
            try:
                ds = load_from_disk(str(in_dir))
            except Exception as e:
                log(f"  {name}: load_from_disk FAIL — {e}")
                continue
            # Per-source caps to keep training tractable on one GPU.
            # SODA is 1.5M; we sample 80k. Others uncapped.
            cap = {"soda": 80000}.get(name)
            n_src = 0
            from datasets import DatasetDict
            splits = ds if isinstance(ds, DatasetDict) else {"train": ds}
            stop = False
            for split_name, split in splits.items():
                if stop:
                    break
                for i, row in enumerate(split):
                    turns = _extract_turns(name, row)
                    if not turns or len(turns) < 2:
                        continue
                    rec = {
                        "source": name,
                        "conversation_id": f"{name}.{split_name}.{i}",
                        "turns": turns,
                    }
                    line = json.dumps(rec, ensure_ascii=False) + "\n"
                    fall.write(line)
                    feval.write(line)
                    if license_tier == "shippable":
                        ftrain.write(line)
                    n_src += 1
                    if cap is not None and n_src >= cap:
                        stop = True
                        break
            log(f"  {name}: {n_src} normalized convos")
            by_source[name] = n_src
            n_total += n_src
    payload = {"total_conversations": n_total, "by_source": by_source}
    log(f"  total: {json.dumps(payload, indent=2)}")
    mark_done("normalize", payload)


def _extract_turns(source: str, row: dict) -> list[dict]:
    """Source-specific extraction. Each adapter returns
    [{speaker: 'A'|'B', text: str}, ...] or [] on failure."""
    import ast
    import re as _re
    try:
        if source == "personachat":
            for key in ("history", "dialog", "utterances"):
                if key in row and isinstance(row[key], list):
                    h = row[key]
                    if h and isinstance(h[0], str):
                        return [{"speaker": "AB"[i % 2], "text": s.strip()} for i, s in enumerate(h) if isinstance(s, str) and s.strip()]
            return []
        if source == "blended_skill":
            # ParlAI/blended_skill_talk
            free = row.get("free_messages") or []
            guided = row.get("guided_messages") or []
            prev = row.get("previous_utterance") or []
            turns = []
            if isinstance(prev, list):
                for i, s in enumerate(prev):
                    if isinstance(s, str) and s.strip():
                        turns.append({"speaker": "AB"[i % 2], "text": s.strip()})
            for f, g in zip(free, guided):
                if isinstance(f, str) and f.strip():
                    turns.append({"speaker": "A", "text": f.strip()})
                if isinstance(g, str) and g.strip():
                    turns.append({"speaker": "B", "text": g.strip()})
            return turns
        if source == "daily_dialog":
            d = row.get("dialog") or row.get("utterances") or []
            return [{"speaker": "AB"[i % 2], "text": s.strip()} for i, s in enumerate(d) if isinstance(s, str) and s.strip()]
        if source == "empathetic":
            # Adapting/empathetic_dialogues_v2: chat_history is a STRING
            # repr of a Python list (["...", "..."]) + sys_response is target.
            hist = row.get("chat_history")
            target = row.get("sys_response")
            turns = []
            if isinstance(hist, str):
                try:
                    parsed = ast.literal_eval(hist)
                    if isinstance(parsed, list):
                        for i, s in enumerate(parsed):
                            if isinstance(s, str) and s.strip():
                                turns.append({"speaker": "AB"[i % 2], "text": s.strip()})
                except Exception:
                    pass
            if isinstance(target, str) and target.strip():
                spk = "B" if (len(turns) % 2 == 1) else "A"
                turns.append({"speaker": spk, "text": target.strip()})
            return turns
        if source == "topical_chat":
            # Fishball02/topical-chat: conversation is one string with
            # <s>[agent_1]...</s><s>[agent_2]...</s> markers.
            c = row.get("conversation")
            if isinstance(c, str):
                segments = _re.findall(r"<s>\[(agent_\d+)\](.*?)</s>", c, flags=_re.DOTALL)
                turns = []
                for agent, txt in segments:
                    spk = "A" if agent.endswith("1") else "B"
                    txt = txt.strip()
                    if txt:
                        turns.append({"speaker": spk, "text": txt})
                return turns
            # Fallback: legacy alexa structure
            c = row.get("content") or row.get("messages") or []
            if isinstance(c, list) and c and isinstance(c[0], dict):
                turns = []
                for i, item in enumerate(c):
                    msg = item.get("message") or item.get("text")
                    if isinstance(msg, str) and msg.strip():
                        agent = item.get("agent", "")
                        spk = "A" if i % 2 == 0 else "B"
                        turns.append({"speaker": spk, "text": msg.strip()})
                return turns
            return []
        if source == "soda":
            # allenai/soda: dialogue=list[str], speakers=list[str] (parallel)
            d = row.get("dialogue") or []
            s = row.get("speakers") or []
            if isinstance(d, list) and isinstance(s, list) and len(d) == len(s):
                speaker_map: dict = {}
                turns = []
                for utt, name_ in zip(d, s):
                    if not isinstance(utt, str) or not utt.strip():
                        continue
                    if name_ not in speaker_map:
                        speaker_map[name_] = "A" if not speaker_map else "B"
                    turns.append({"speaker": speaker_map[name_], "text": utt.strip()})
                return turns
            return []
    except Exception:
        return []
    return []


# ========== Phase 4: format_sft ==========

def phase_format_sft() -> None:
    """Convert normalized conversations into SFT pairs for QLoRA.

    We use a "predict the next human turn given prior context"
    objective. For a 6-turn convo [A1 B1 A2 B2 A3 B3], we generate
    samples like (input=[A1 B1 A2 B2 A3], target=B3).

    Format: ChatML-style messages list. The 'assistant' role IS
    the human partner whose turn we're predicting — we reframe the
    task as 'continue this human conversation as the other speaker'.
    Only the assistant turn is loss-masked-in.
    """
    log("Phase 4: format_sft — building ChatML pairs")
    update_status("format_sft", "formatting")
    src = DATA / "normalized_train.jsonl"
    out = DATA / "sft_train.jsonl"
    out_eval = DATA / "sft_eval.jsonl"
    n_train = 0
    n_eval = 0
    n_skipped = 0
    SYSTEM = (
        "You are continuing a casual conversation between two people. "
        "Reply naturally as the other speaker — short, human, no AI mannerisms. "
        "Match the tone, register, and length of the dialog you've been shown."
    )
    with src.open("r", encoding="utf-8") as fin, \
         out.open("w", encoding="utf-8") as ftrain, \
         out_eval.open("w", encoding="utf-8") as feval:
        for line_idx, line in enumerate(fin):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            turns = rec.get("turns") or []
            if len(turns) < 4:
                n_skipped += 1
                continue
            # Skip if any turn is suspiciously long (>500 words = monologue, not chat)
            if any(len((t.get("text") or "").split()) > 500 for t in turns):
                n_skipped += 1
                continue
            # English filter: rough — at least 80% ASCII letters/space/punct
            full = " ".join(t.get("text", "") for t in turns)
            if not full or sum(1 for c in full if ord(c) < 128) / max(len(full), 1) < 0.95:
                n_skipped += 1
                continue
            # Generate up to 3 SFT pairs per conversation, sliding window.
            # Always predict B-side turns (target speaker = "B").
            generated = 0
            for tidx in range(2, len(turns)):
                if turns[tidx].get("speaker") != "B":
                    continue
                ctx = turns[:tidx]
                target_text = (turns[tidx].get("text") or "").strip()
                if not target_text or len(target_text.split()) > 100:
                    continue
                msgs = [{"role": "system", "content": SYSTEM}]
                for t in ctx:
                    role = "user" if t["speaker"] == "A" else "assistant"
                    msgs.append({"role": role, "content": t["text"]})
                msgs.append({"role": "assistant", "content": target_text})
                sample = {"messages": msgs, "source": rec.get("source")}
                # 95/5 split: line idx % 20 == 0 -> eval
                if line_idx % 20 == 0:
                    feval.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    n_eval += 1
                else:
                    ftrain.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    n_train += 1
                generated += 1
                if generated >= 3:
                    break
    payload = {"train_samples": n_train, "eval_samples": n_eval, "skipped_convos": n_skipped}
    log(f"  formatted: {json.dumps(payload, indent=2)}")
    mark_done("format_sft", payload)


# ========== Phase 5: train_lora ==========

def phase_train_lora() -> None:
    """QLoRA fine-tune Qwen2.5-7B-Instruct on the SFT data.

    Stops Ollama first to free VRAM (3090 Ti has 24GB; QLoRA-7B
    needs ~12GB; Ollama loaded model occupies ~5GB).
    """
    log("Phase 5: train_lora — QLoRA fine-tune of Qwen2.5-7B-Instruct")
    update_status("train_lora", "preparing")

    # Free VRAM: kill Ollama before training.
    log("  stopping Ollama to free VRAM")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from datasets import load_dataset
    from transformers import (
        AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    log("  loading tokenizer + 4-bit base model")
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_cfg,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="eager",  # avoid FA2 build issues on Windows
    )
    model = prepare_model_for_kbit_training(model)
    lora_cfg = LoraConfig(
        r=64, lora_alpha=128, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    log("  loading SFT datasets")
    ds_train = load_dataset("json", data_files=str(DATA / "sft_train.jsonl"), split="train")
    ds_eval = load_dataset("json", data_files=str(DATA / "sft_eval.jsonl"), split="train")
    log(f"  train: {len(ds_train)}  eval: {len(ds_eval)}")

    def format_func(example):
        return tok.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)

    out_dir = CKPT / "qwen25_7b_human_lora"
    sft_cfg = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.03,
        logging_steps=20,
        save_strategy="steps",
        save_steps=500,
        save_total_limit=3,
        eval_strategy="steps",
        eval_steps=500,
        per_device_eval_batch_size=4,
        bf16=True,
        max_length=1024,
        packing=False,
        dataset_text_field=None,  # we provide formatting_func
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to="none",
    )
    trainer = SFTTrainer(
        model=model, args=sft_cfg,
        train_dataset=ds_train, eval_dataset=ds_eval,
        formatting_func=format_func,
        processing_class=tok,
    )
    log("  training start")
    t0 = time.time()
    trainer.train()
    log(f"  training done in {time.time()-t0:.0f}s")
    log("  saving final LoRA adapter")
    trainer.save_model(str(out_dir / "final"))
    tok.save_pretrained(str(out_dir / "final"))
    payload = {
        "ckpt_dir": str(out_dir / "final"),
        "train_samples": len(ds_train), "eval_samples": len(ds_eval),
        "training_seconds": round(time.time()-t0),
    }
    mark_done("train_lora", payload)


# ========== Phase 6: train_discriminator ==========

def phase_train_discriminator() -> None:
    """Train DistilBERT to distinguish human dialog turns from
    AI-generated dialog turns. Used in Phase 7 to score 'how
    human-like' the fine-tuned model's outputs are."""
    log("Phase 6: train_discriminator — DistilBERT human/AI classifier")
    update_status("train_discriminator", "training")

    from datasets import Dataset
    from transformers import (
        AutoTokenizer, AutoModelForSequenceClassification,
        TrainingArguments, Trainer,
    )
    import numpy as np
    import torch

    # Positives: real human turns from normalized eval set.
    pos = []
    with (DATA / "normalized_eval.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for t in rec.get("turns", []):
                txt = (t.get("text") or "").strip()
                if 5 <= len(txt.split()) <= 80 and sum(1 for c in txt if ord(c) < 128) / max(len(txt), 1) > 0.95:
                    pos.append(txt)
                    if len(pos) >= 12000:
                        break
            if len(pos) >= 12000:
                break
    log(f"  collected {len(pos)} human positives")

    # Negatives: query Ollama gemma4:e4b for short responses to a
    # diverse prompt set. (Ollama may have been killed in Phase 5;
    # restart it.)
    log("  restarting Ollama for negative generation")
    os.system('start "" /B "C:\\Users\\dbhav\\AppData\\Local\\Programs\\Ollama\\ollama.exe" serve')
    time.sleep(8)

    # Sample prompts from human turns themselves (use A-side as a
    # naturalistic prompt distribution).
    prompt_pool = []
    with (DATA / "normalized_eval.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for t in rec.get("turns", []):
                if t.get("speaker") == "A":
                    txt = (t.get("text") or "").strip()
                    if 5 <= len(txt.split()) <= 50:
                        prompt_pool.append(txt)
            if len(prompt_pool) >= 6000:
                break
    log(f"  prompt pool: {len(prompt_pool)}")

    import urllib.request
    def gen_one(prompt: str) -> str | None:
        body = json.dumps({"model": "gemma4:e4b", "prompt": prompt, "stream": False, "options": {"num_predict": 80}}).encode("utf-8")
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return (payload.get("response") or "").strip()
        except Exception:
            return None

    neg = []
    target_neg = min(8000, len(pos))
    log(f"  generating {target_neg} negatives via Ollama gemma4:e4b — slow")
    t0 = time.time()
    for i, p in enumerate(prompt_pool[:target_neg * 2]):
        if len(neg) >= target_neg:
            break
        if i % 200 == 0 and i > 0:
            log(f"    generated {len(neg)}/{target_neg} ({time.time()-t0:.0f}s)")
        out = gen_one(p)
        if out and 5 <= len(out.split()) <= 80:
            neg.append(out)
    log(f"  collected {len(neg)} AI negatives in {time.time()-t0:.0f}s")

    # Build dataset
    texts = pos[: len(neg)] + neg
    labels = [1] * len(neg) + [0] * len(neg)  # 1=human, 0=AI
    n = len(texts)
    idx = list(range(n))
    import random
    random.Random(42).shuffle(idx)
    texts = [texts[i] for i in idx]
    labels = [labels[i] for i in idx]
    split_at = int(n * 0.9)
    ds_tr = Dataset.from_dict({"text": texts[:split_at], "label": labels[:split_at]})
    ds_ev = Dataset.from_dict({"text": texts[split_at:], "label": labels[split_at:]})
    log(f"  classifier dataset: train={len(ds_tr)} eval={len(ds_ev)}")

    tok = AutoTokenizer.from_pretrained(DISCRIM_MODEL)
    def tok_fn(batch):
        return tok(batch["text"], truncation=True, padding="max_length", max_length=128)
    ds_tr = ds_tr.map(tok_fn, batched=True)
    ds_ev = ds_ev.map(tok_fn, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(DISCRIM_MODEL, num_labels=2)
    out_dir = CKPT / "discriminator_distilbert"
    args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=2,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=64,
        learning_rate=5e-5,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        logging_steps=50,
        report_to="none",
    )
    def compute_metrics(p):
        import numpy as np
        preds = np.argmax(p.predictions, axis=1)
        acc = (preds == p.label_ids).mean()
        return {"accuracy": float(acc)}
    trainer = Trainer(model=model, args=args, train_dataset=ds_tr, eval_dataset=ds_ev, compute_metrics=compute_metrics)
    log("  training discriminator")
    t0 = time.time()
    trainer.train()
    eval_res = trainer.evaluate()
    log(f"  discriminator eval: {eval_res}")
    trainer.save_model(str(out_dir / "final"))
    tok.save_pretrained(str(out_dir / "final"))
    payload = {
        "ckpt_dir": str(out_dir / "final"),
        "train_samples": len(ds_tr), "eval_samples": len(ds_ev),
        "eval_accuracy": eval_res.get("eval_accuracy"),
        "training_seconds": round(time.time()-t0),
    }
    mark_done("train_discriminator", payload)


# ========== Phase 7: eval ==========

def phase_eval() -> None:
    """Generate continuations from baseline (gemma4:e4b via Ollama)
    and from fine-tuned (Qwen2.5-7B + LoRA), score both with the
    discriminator. Report % of outputs misclassified as human."""
    log("Phase 7: eval — generating + scoring")
    update_status("eval", "generating outputs")

    import torch
    import urllib.request
    from transformers import (
        AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig,
        AutoModelForSequenceClassification,
        pipeline,
    )
    from peft import PeftModel

    # 1. Build eval prompt set: take 200 conversations from
    # normalized_eval.jsonl, take the first 4-6 turns as context,
    # ask the model to continue.
    eval_prompts = []
    with (DATA / "normalized_eval.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            turns = rec.get("turns") or []
            if len(turns) < 4:
                continue
            ctx = turns[:5]
            if any(len((t.get("text") or "").split()) > 80 for t in ctx):
                continue
            eval_prompts.append({"context": ctx, "source": rec.get("source")})
            if len(eval_prompts) >= 200:
                break
    log(f"  built {len(eval_prompts)} eval prompts")
    (EVAL / "eval_prompts.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in eval_prompts), encoding="utf-8"
    )

    SYSTEM = (
        "You are continuing a casual conversation between two people. "
        "Reply naturally as the other speaker — short, human, no AI mannerisms. "
        "Match the tone, register, and length of the dialog you've been shown."
    )

    # 2. Baseline: Ollama gemma4:e4b
    log("  ensuring Ollama is up for baseline gen")
    os.system('start "" /B "C:\\Users\\dbhav\\AppData\\Local\\Programs\\Ollama\\ollama.exe" serve')
    time.sleep(6)
    baseline_outs = []
    for i, p in enumerate(eval_prompts):
        if i % 25 == 0:
            log(f"    baseline gen {i}/{len(eval_prompts)}")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        body = json.dumps({"model": "gemma4:e4b", "messages": msgs, "stream": False, "options": {"num_predict": 80}}).encode("utf-8")
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            out = payload.get("message", {}).get("content", "").strip()
        except Exception as e:
            out = ""
        baseline_outs.append(out)
    (EVAL / "baseline_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(baseline_outs)),
        encoding="utf-8",
    )

    # 3. Fine-tuned: load Qwen2.5-7B + LoRA
    log("  stopping Ollama to free VRAM for fine-tuned gen")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    log("  loading fine-tuned Qwen2.5-7B + LoRA")
    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=bnb_cfg, device_map="auto", trust_remote_code=True, attn_implementation="eager")
    lora_dir = CKPT / "qwen25_7b_human_lora" / "final"
    model = PeftModel.from_pretrained(base, str(lora_dir))
    model.eval()

    finetuned_outs = []
    for i, p in enumerate(eval_prompts):
        if i % 25 == 0:
            log(f"    finetuned gen {i}/{len(eval_prompts)}")
        msgs = [{"role": "system", "content": SYSTEM}]
        for t in p["context"]:
            role = "user" if t["speaker"] == "A" else "assistant"
            msgs.append({"role": role, "content": t["text"]})
        prompt_str = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt_str, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outs = model.generate(**inputs, max_new_tokens=80, do_sample=True, top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        text = tok.decode(outs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        finetuned_outs.append(text)
    (EVAL / "finetuned_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(finetuned_outs)),
        encoding="utf-8",
    )
    del model, base
    torch.cuda.empty_cache()

    # 4. Score both with discriminator
    log("  scoring with discriminator")
    discrim_dir = CKPT / "discriminator_distilbert" / "final"
    clf = pipeline("text-classification", model=str(discrim_dir), tokenizer=str(discrim_dir), device=0, top_k=None)
    def score_set(texts):
        # label 1 = human; we want fraction predicted as human
        preds = clf(texts, truncation=True, padding=True, max_length=128, batch_size=32)
        n_human = 0
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
            # transformers pipeline returns labels like 'LABEL_0' / 'LABEL_1'
            if scores.get("LABEL_1", 0) > scores.get("LABEL_0", 0):
                n_human += 1
        return n_human / len(texts) if texts else 0.0
    baseline_human_rate = score_set([o for o in baseline_outs if o])
    finetuned_human_rate = score_set([o for o in finetuned_outs if o])

    log(f"  baseline (gemma4:e4b)   classified-as-human rate: {baseline_human_rate:.3f}")
    log(f"  fine-tuned (Qwen LoRA)  classified-as-human rate: {finetuned_human_rate:.3f}")
    log(f"  delta: {finetuned_human_rate - baseline_human_rate:+.3f}")

    payload = {
        "n_eval_prompts": len(eval_prompts),
        "baseline_human_rate": baseline_human_rate,
        "finetuned_human_rate": finetuned_human_rate,
        "delta": finetuned_human_rate - baseline_human_rate,
    }
    (EVAL / "scores.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    mark_done("eval", payload)


# ========== Phase 8: writeup ==========

def phase_writeup() -> None:
    log("Phase 8: writeup")
    update_status("writeup", "generating findings doc")
    out = ROOT.parent / "HUMAN_LIKE_TRAINING_REPORT.md"
    chunks = ["# Human-Like Conversation Training Report", "",
              f"**Run completed:** {now_iso()}", ""]
    for p in PHASES:
        m_path = marker_path(p)
        if m_path.exists():
            m = json.loads(m_path.read_text(encoding="utf-8"))
            chunks.append(f"## Phase: {p}")
            chunks.append("")
            chunks.append("```json")
            chunks.append(json.dumps(m, indent=2))
            chunks.append("```")
            chunks.append("")
    out.write_text("\n".join(chunks), encoding="utf-8")
    log(f"  wrote {out}")
    mark_done("writeup", {"output_path": str(out)})


# ========== Main driver ==========

PHASE_FNS = {
    "setup": phase_setup,
    "download_corpora": phase_download_corpora,
    "normalize": phase_normalize,
    "format_sft": phase_format_sft,
    "train_lora": phase_train_lora,
    "train_discriminator": phase_train_discriminator,
    "eval": phase_eval,
    "writeup": phase_writeup,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default=None, help="Run a single phase")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reset", default=None, help="Delete done-marker for phase to force re-run")
    args = parser.parse_args()

    if args.status:
        if STATUS.exists():
            print(STATUS.read_text(encoding="utf-8"))
        else:
            print("(no STATUS.md yet)")
        return

    if args.reset:
        m = marker_path(args.reset)
        if m.exists():
            m.unlink()
            print(f"reset {args.reset}")
        return

    log(f"=== Pipeline driver invoked ({args.phase or 'all phases'}) ===")
    phases_to_run = [args.phase] if args.phase else PHASES
    for p in phases_to_run:
        if p not in PHASE_FNS:
            log(f"unknown phase {p}")
            continue
        if is_done(p):
            log(f"phase {p}: already done, skipping")
            continue
        try:
            PHASE_FNS[p]()
            update_status(p, "done")
        except Exception as e:
            log(f"phase {p} FAILED: {type(e).__name__}: {e}")
            log(traceback.format_exc())
            update_status(p, f"FAILED — {type(e).__name__}: {e}")
            raise
    log("=== Pipeline driver finished ===")


if __name__ == "__main__":
    main()
