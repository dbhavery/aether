"""Human-indistinguishable conversation training pipeline v2.

Lessons from v1 (HUMAN_LIKE_TRAINING_REPORT.md):
- 7B QLoRA at 5s/step burns the budget on parameter count we don't
  need for chat naturalness. v2 uses Qwen2.5-3B-Instruct → ~1.5s/step.
- Eval set must be tiny (≤500) and run rarely (eval_steps≥2500).
- Need 2-3x more data variety, not 2-3x more samples from same convos.

Speed budget: 12h × 3600s / 1.5s/step = 28,800 steps.
Effective batch 16 → ~460,000 SFT samples in budget.
We aim for 200k–300k samples to leave training-time headroom for
discriminator + eval phases.

Phases (idempotent, resumable):
  1 setup
  2 download_corpora   — six sources (3 in v1 + OASST2, UltraChat, DailyDialog)
  3 normalize          — common turn-row schema with quality filters
  4 format_sft         — ChatML pairs + dedup + length filter
  5 train_lora         — Qwen2.5-3B-Instruct + QLoRA (faster base)
  6 train_discriminator — DistilBERT human/AI
  7 eval               — generate baseline + finetuned, score
  8 writeup
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MODELS = ROOT / "models"
CKPT = ROOT / "checkpoints_v2"
EVAL = ROOT / "eval_v2"
LOGS = ROOT / "logs_v2"
STATUS = ROOT / "STATUS_V2.md"

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"  # 3B vs v1's 7B → ~3x faster
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
    completed = [p for p in PHASES if is_done(p)]
    pending = [p for p in PHASES if not is_done(p)]
    lines = ["# Training Pipeline V2 Status", "", f"**Updated:** {now_iso()}",
             f"**Current phase:** {current_phase} — {state}", "", "## Completed"]
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
    log("Phase 1 v2: setup — verifying environment")
    update_status("setup", "verifying deps")
    import torch, transformers, peft, trl, datasets as hfds, bitsandbytes, accelerate
    payload = {
        "torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "vram_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if torch.cuda.is_available() else 0,
        "transformers": transformers.__version__, "peft": peft.__version__,
        "trl": trl.__version__, "datasets": hfds.__version__,
        "bitsandbytes": bitsandbytes.__version__, "accelerate": accelerate.__version__,
        "base_model": BASE_MODEL, "discriminator_model": DISCRIM_MODEL,
        "version": "v2",
    }
    log(f"  env: {json.dumps(payload, indent=2)}")
    for d in (DATA, MODELS, CKPT, EVAL, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    mark_done("setup", payload)


# ========== Phase 2: download_corpora ==========

# (name, hf_path, license_tier, role, optional split, optional config)
CORPORA = [
    # Tier A: human-human, shippable. (v1)
    ("blended_skill",      "ParlAI/blended_skill_talk",         "shippable", "train+eval", None, None),
    ("topical_chat",       "Fishball02/topical-chat",           "shippable", "train+eval", None, None),
    ("soda",               "allenai/soda",                      "shippable", "train+eval", None, None),
    # New for v2:
    ("oasst2",             "OpenAssistant/oasst2",              "shippable", "train+eval", None, None),
    ("ultrachat",          "HuggingFaceH4/ultrachat_200k",      "shippable", "train+eval", None, None),  # synthesized but MIT, large
    ("daily_dialog",       "pixelsandpointers/better_daily_dialog", "shippable", "train+eval", None, None),
    # Eval-only:
    ("empathetic",         "Adapting/empathetic_dialogues_v2",  "eval_only", "eval", None, None),
    # WildChat reserved for eval-only (real-human prompt distribution).
    ("wildchat",           "allenai/WildChat-1M",               "eval_only", "eval", None, None),
]


def phase_download_corpora() -> None:
    log("Phase 2 v2: download_corpora")
    update_status("download_corpora", "downloading")
    from datasets import load_dataset, DatasetDict
    summary = {}
    for name, hf_path, license_tier, role, split, config in CORPORA:
        out_dir = DATA / name
        if (out_dir / ".success").exists():
            log(f"  {name}: cached, skipping")
            summary[name] = {"status": "cached", "license": license_tier, "role": role}
            continue
        log(f"  {name}: loading {hf_path}")
        try:
            kwargs = {}
            if config:
                kwargs["name"] = config
            ds = load_dataset(hf_path, **kwargs)
            out_dir.mkdir(parents=True, exist_ok=True)
            ds.save_to_disk(str(out_dir))
            (out_dir / ".success").touch()
            n = sum(len(s) for s in ds.values()) if isinstance(ds, DatasetDict) else len(ds)
            log(f"  {name}: ok, {n} rows")
            summary[name] = {"status": "ok", "rows": n, "license": license_tier, "role": role}
        except Exception as e:
            log(f"  {name}: FAIL — {type(e).__name__}: {e}")
            summary[name] = {"status": "fail", "error": f"{type(e).__name__}: {e}", "license": license_tier, "role": role}
    log(f"  download summary: {json.dumps(summary, indent=2)}")
    mark_done("download_corpora", summary)


# ========== Phase 3: normalize (with quality filters) ==========

# Per-source caps tuned for ~12h training budget.
SOURCE_CAPS = {
    "soda": 250000,
    "ultrachat": 80000,
    "oasst2": None,        # all ~135k messages → ~50k convos
    "topical_chat": None,
    "blended_skill": None,
    "daily_dialog": None,
    "empathetic": None,
    "wildchat": 30000,     # eval-only sampling
}

# Quality filter parameters
MIN_TURN_WORDS = 1
MAX_TURN_WORDS = 200
MIN_CONV_TURNS = 2
ASCII_MIN_RATIO = 0.95


def _quality_ok(turns: list[dict]) -> bool:
    if len(turns) < MIN_CONV_TURNS:
        return False
    full = " ".join(t.get("text", "") for t in turns)
    if not full:
        return False
    if sum(1 for c in full if ord(c) < 128) / len(full) < ASCII_MIN_RATIO:
        return False
    if any(len((t.get("text") or "").split()) > MAX_TURN_WORDS for t in turns):
        return False
    if any(len((t.get("text") or "").split()) < MIN_TURN_WORDS for t in turns):
        return False
    # Drop convos with massive repetition (single token > 30% of total)
    tokens = full.split()
    if tokens:
        from collections import Counter
        common = Counter(t.lower() for t in tokens).most_common(1)[0][1]
        if common > 0.3 * len(tokens) and len(tokens) > 30:
            return False
    return True


# Strip leading speaker name like "Veda: text" in SODA.
SPEAKER_PREFIX_RE = re.compile(r"^[A-Z][a-zA-Z']{1,15}:\s+")


def _strip_speaker_prefix(text: str) -> str:
    return SPEAKER_PREFIX_RE.sub("", text)


def phase_normalize() -> None:
    log("Phase 3 v2: normalize")
    update_status("normalize", "normalizing")
    from datasets import load_from_disk, DatasetDict
    out_path = DATA / "normalized_v2.jsonl"
    out_train = DATA / "normalized_train_v2.jsonl"
    out_eval = DATA / "normalized_eval_v2.jsonl"
    by_source = {}
    n_total = 0
    seen_hashes: set[str] = set()
    n_dedup_drops = 0
    with out_path.open("w", encoding="utf-8") as fall, \
         out_train.open("w", encoding="utf-8") as ftrain, \
         out_eval.open("w", encoding="utf-8") as feval:
        for name, hf_path, license_tier, role, *_ in CORPORA:
            in_dir = DATA / name
            if not (in_dir / ".success").exists():
                log(f"  {name}: skip (not downloaded)")
                continue
            try:
                ds = load_from_disk(str(in_dir))
            except Exception as e:
                log(f"  {name}: load FAIL — {e}")
                continue
            cap = SOURCE_CAPS.get(name)

            # Sources that need batch reconstruction across rows.
            if name == "oasst2":
                convos = _reconstruct_oasst2(ds)
            elif name == "daily_dialog":
                convos = _reconstruct_daily_dialog(ds)
            else:
                convos = None

            if convos is not None:
                if cap:
                    convos = convos[:cap]
                n_src = 0
                for ci, turns in enumerate(convos):
                    if not _quality_ok(turns):
                        continue
                    h = _conv_hash(turns)
                    if h in seen_hashes:
                        n_dedup_drops += 1
                        continue
                    seen_hashes.add(h)
                    rec = {"source": name, "conversation_id": f"{name}.{ci}", "turns": turns}
                    line = json.dumps(rec, ensure_ascii=False) + "\n"
                    fall.write(line); feval.write(line)
                    if license_tier == "shippable":
                        ftrain.write(line)
                    n_src += 1
                log(f"  {name}: {n_src} normalized convos (cap={cap})")
                by_source[name] = n_src
                n_total += n_src
                continue

            # Other sources: per-row extraction.
            n_src = 0
            splits = ds if isinstance(ds, DatasetDict) else {"train": ds}
            stop = False
            for split_name, split in splits.items():
                if stop:
                    break
                for i, row in enumerate(split):
                    turns = _extract_turns(name, row)
                    if not turns or not _quality_ok(turns):
                        continue
                    h = _conv_hash(turns)
                    if h in seen_hashes:
                        n_dedup_drops += 1
                        continue
                    seen_hashes.add(h)
                    rec = {"source": name, "conversation_id": f"{name}.{split_name}.{i}", "turns": turns}
                    line = json.dumps(rec, ensure_ascii=False) + "\n"
                    fall.write(line); feval.write(line)
                    if license_tier == "shippable":
                        ftrain.write(line)
                    n_src += 1
                    if cap is not None and n_src >= cap:
                        stop = True; break
            log(f"  {name}: {n_src} normalized convos (cap={cap})")
            by_source[name] = n_src
            n_total += n_src

    payload = {
        "total_conversations": n_total,
        "by_source": by_source,
        "dedup_drops": n_dedup_drops,
        "filters": {"min_turns": MIN_CONV_TURNS, "min_words": MIN_TURN_WORDS,
                    "max_words": MAX_TURN_WORDS, "ascii_min_ratio": ASCII_MIN_RATIO},
        "caps": {k: v for k, v in SOURCE_CAPS.items() if v is not None},
    }
    log(f"  total: {json.dumps(payload, indent=2)}")
    mark_done("normalize", payload)


def _conv_hash(turns: list[dict]) -> str:
    s = "|".join(t.get("text", "")[:120] for t in turns)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _reconstruct_daily_dialog(ds) -> list[list[dict]]:
    """pixelsandpointers/better_daily_dialog: row-per-utterance with
    dialog_id grouping. Reconstruct alternating-speaker conversations."""
    from datasets import DatasetDict
    by_dialog: dict[int, list[str]] = defaultdict(list)
    splits = ds if isinstance(ds, DatasetDict) else {"train": ds}
    for s_name, split in splits.items():
        for r in split:
            did = r.get("dialog_id")
            utt = (r.get("utterance") or "").strip()
            if did is None or not utt:
                continue
            by_dialog[did].append(utt)
    convos = []
    for did, utts in by_dialog.items():
        if len(utts) < 2:
            continue
        turns = [{"speaker": "AB"[i % 2], "text": u} for i, u in enumerate(utts)]
        convos.append(turns)
    return convos


def _reconstruct_oasst2(ds) -> list[list[dict]]:
    """OASST2 is one-row-per-message with parent_id. Walk every leaf
    backward to assemble [(prompter), (assistant), (prompter), ...]
    threads. Returns deduped conversations as turn lists with
    speaker A=prompter, B=assistant."""
    from datasets import DatasetDict
    rows = []
    splits = ds if isinstance(ds, DatasetDict) else {"train": ds}
    for s_name, split in splits.items():
        for r in split:
            rows.append(r)
    by_id = {r["message_id"]: r for r in rows}
    children = defaultdict(list)
    for r in rows:
        if r.get("parent_id"):
            children[r["parent_id"]].append(r)
    # English filter
    rows = [r for r in rows if (r.get("lang") or "").lower().startswith("en")]
    by_id = {r["message_id"]: r for r in rows}
    # Find leaves: messages with no English children.
    leaves = []
    for r in rows:
        kids = [c for c in children.get(r["message_id"], []) if c["message_id"] in by_id]
        if not kids:
            leaves.append(r)
    convos = []
    for leaf in leaves:
        chain = []
        cur = leaf
        while cur is not None:
            chain.append(cur)
            pid = cur.get("parent_id")
            cur = by_id.get(pid) if pid else None
        chain.reverse()
        if len(chain) < MIN_CONV_TURNS:
            continue
        turns = []
        for m in chain:
            role = m.get("role", "")
            spk = "A" if role == "prompter" else "B"
            txt = (m.get("text") or "").strip()
            if not txt:
                turns = []
                break
            turns.append({"speaker": spk, "text": txt})
        if turns:
            convos.append(turns)
    return convos


def _extract_turns(source: str, row: dict) -> list[dict]:
    import ast
    try:
        if source == "blended_skill":
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
        if source == "topical_chat":
            c = row.get("conversation")
            if isinstance(c, str):
                segments = re.findall(r"<s>\[(agent_\d+)\](.*?)</s>", c, flags=re.DOTALL)
                turns = []
                for agent, txt in segments:
                    spk = "A" if agent.endswith("1") else "B"
                    txt = txt.strip()
                    if txt:
                        turns.append({"speaker": spk, "text": txt})
                return turns
            return []
        if source == "soda":
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
                    # Strip "Veda: " style speaker prefixes
                    txt = _strip_speaker_prefix(utt.strip())
                    if txt:
                        turns.append({"speaker": speaker_map[name_], "text": txt})
                return turns
            return []
        if source == "ultrachat":
            # HuggingFaceH4/ultrachat_200k: 'messages' is list of {role, content}
            msgs = row.get("messages") or []
            if isinstance(msgs, list):
                turns = []
                for m in msgs:
                    role = (m or {}).get("role")
                    content = (m or {}).get("content")
                    if not isinstance(content, str) or not content.strip():
                        continue
                    spk = "A" if role == "user" else "B"
                    turns.append({"speaker": spk, "text": content.strip()})
                return turns
            return []
        if source == "daily_dialog":
            # pixelsandpointers/better_daily_dialog: row-per-utterance with dialog_id
            # We aggregate elsewhere; this function returns [] and we
            # must batch reconstruct. Handle inline below.
            return []
        if source == "empathetic":
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
        if source == "wildchat":
            # allenai/WildChat-1M: 'conversation' is list of {role, content}
            # Filter to English only.
            if (row.get("language") or "").lower() != "english":
                return []
            convo = row.get("conversation") or []
            if not isinstance(convo, list):
                return []
            turns = []
            for m in convo:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                content = m.get("content") or ""
                if not isinstance(content, str) or not content.strip():
                    continue
                spk = "A" if role == "user" else "B"
                turns.append({"speaker": spk, "text": content.strip()})
            return turns
    except Exception:
        return []
    return []


# Daily dialog needs inline reconstruction. Patch normalize to handle
# it specially — adding a tiny helper here, called after the loop.
# (Implemented in the main function via a separate pass for now.)


# ========== Phase 4: format_sft (with dedup) ==========

def phase_format_sft() -> None:
    log("Phase 4 v2: format_sft")
    update_status("format_sft", "formatting")
    src = DATA / "normalized_train_v2.jsonl"
    out = DATA / "sft_train_v2.jsonl"
    out_eval = DATA / "sft_eval_v2.jsonl"
    SYSTEM = (
        "You are continuing a casual conversation between two people. "
        "Reply naturally as the other speaker — short, human, no AI mannerisms. "
        "Match the tone, register, and length of the dialog you've been shown."
    )
    n_train = n_eval = n_skipped = 0
    seen_target_hashes: set[str] = set()
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
            generated = 0
            for tidx in range(2, len(turns)):
                if turns[tidx].get("speaker") != "B":
                    continue
                ctx = turns[:tidx]
                target_text = (turns[tidx].get("text") or "").strip()
                if not target_text or len(target_text.split()) > 100:
                    continue
                # Dedup on target text (cuts heavy duplicate-style training).
                th = hashlib.md5(target_text[:200].encode("utf-8")).hexdigest()
                if th in seen_target_hashes:
                    continue
                seen_target_hashes.add(th)
                msgs = [{"role": "system", "content": SYSTEM}]
                for t in ctx:
                    role = "user" if t["speaker"] == "A" else "assistant"
                    msgs.append({"role": role, "content": t["text"]})
                msgs.append({"role": "assistant", "content": target_text})
                sample = {"messages": msgs, "source": rec.get("source")}
                if line_idx % 40 == 0:
                    feval.write(json.dumps(sample, ensure_ascii=False) + "\n"); n_eval += 1
                else:
                    ftrain.write(json.dumps(sample, ensure_ascii=False) + "\n"); n_train += 1
                generated += 1
                if generated >= 4:
                    break
    payload = {"train_samples": n_train, "eval_samples": n_eval, "skipped_convos": n_skipped}
    log(f"  formatted: {json.dumps(payload, indent=2)}")
    mark_done("format_sft", payload)


# ========== Phase 5: train_lora (Qwen2.5-3B + tuned config) ==========

def phase_train_lora() -> None:
    log("Phase 5 v2: train_lora — Qwen2.5-3B-Instruct + QLoRA")
    update_status("train_lora", "preparing")
    log("  stopping Ollama to free VRAM")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    import torch
    from datasets import load_dataset
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, SFTConfig

    log("  loading tokenizer + 4-bit base model")
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
    )
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, quantization_config=bnb_cfg, device_map="auto",
        trust_remote_code=True, attn_implementation="sdpa",  # SDPA is faster than 'eager'
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
    ds_train = load_dataset("json", data_files=str(DATA / "sft_train_v2.jsonl"), split="train")
    ds_eval_full = load_dataset("json", data_files=str(DATA / "sft_eval_v2.jsonl"), split="train")
    ds_eval = ds_eval_full.select(range(min(500, len(ds_eval_full))))
    log(f"  train: {len(ds_train)}  eval: {len(ds_eval)} (truncated from {len(ds_eval_full)})")

    def format_func(example):
        return tok.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)

    out_dir = CKPT / "qwen25_3b_human_lora"
    sft_cfg = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=1,
        per_device_train_batch_size=8,        # 3B fits this on 24GB with max_length 768
        gradient_accumulation_steps=2,        # effective batch = 16
        learning_rate=2e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=20,
        save_strategy="steps",
        save_steps=1000,
        save_total_limit=3,
        eval_strategy="steps",
        eval_steps=2500,
        per_device_eval_batch_size=8,
        bf16=True,
        max_length=768,
        packing=False,
        dataset_text_field=None,
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
    resume = False
    if out_dir.exists():
        ckpts = sorted(out_dir.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
        if ckpts:
            resume = True
            log(f"  resuming from {ckpts[-1].name}")
    trainer.train(resume_from_checkpoint=resume)
    log(f"  training done in {time.time()-t0:.0f}s")
    trainer.save_model(str(out_dir / "final"))
    tok.save_pretrained(str(out_dir / "final"))
    payload = {
        "ckpt_dir": str(out_dir / "final"),
        "train_samples": len(ds_train), "eval_samples": len(ds_eval),
        "training_seconds": round(time.time()-t0),
        "base_model": BASE_MODEL,
    }
    mark_done("train_lora", payload)


# ========== Phases 6, 7, 8 (reuse v1 logic) ==========
# These are identical in structure to v1; placeholder calls into the
# v1 functions where possible. Kept self-contained for clarity.

def phase_train_discriminator() -> None:
    """Train DistilBERT to distinguish human from AI dialog turns.
    Uses v2 normalized_eval as the human-positive source; queries
    Ollama gemma4:e4b for AI negatives."""
    log("Phase 6 v2: train_discriminator")
    update_status("train_discriminator", "training")
    from datasets import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              TrainingArguments, Trainer)
    import torch

    # Positives: real human turns from v2 normalized eval set.
    pos = []
    with (DATA / "normalized_eval_v2.jsonl").open("r", encoding="utf-8") as f:
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

    log("  restarting Ollama for negative generation")
    os.system('start "" /B "C:\\Users\\dbhav\\AppData\\Local\\Programs\\Ollama\\ollama.exe" serve')
    time.sleep(8)

    prompt_pool = []
    with (DATA / "normalized_eval_v2.jsonl").open("r", encoding="utf-8") as f:
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
            if len(prompt_pool) >= 12000:
                break
    log(f"  prompt pool: {len(prompt_pool)}")

    import urllib.request
    def gen_one(prompt: str) -> str | None:
        # gemma4:e4b is a reasoning model — without "think": false it
        # spends all num_predict tokens on the thinking field and
        # returns empty content. Fix: disable thinking for this use.
        body = json.dumps({
            "model": "gemma4:e4b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"num_predict": 80},
        }).encode("utf-8")
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return (payload.get("message", {}).get("content") or "").strip()
        except Exception:
            return None

    neg = []
    target_neg = min(3000, len(pos))  # 3000 plenty for DistilBERT classifier
    log(f"  generating {target_neg} negatives via Ollama gemma4:e4b (think=false)")
    t0 = time.time()
    for i, p in enumerate(prompt_pool[:target_neg * 3]):
        if len(neg) >= target_neg:
            break
        if i % 200 == 0 and i > 0:
            log(f"    generated {len(neg)}/{target_neg} ({time.time()-t0:.0f}s)")
        out = gen_one(p)
        if out and 5 <= len(out.split()) <= 80:
            neg.append(out)
    log(f"  collected {len(neg)} AI negatives in {time.time()-t0:.0f}s")

    texts = pos[:len(neg)] + neg
    labels = [1] * len(neg) + [0] * len(neg)
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


def phase_eval() -> None:
    """Generate continuations from baseline (gemma4:e4b) and from
    fine-tuned (Qwen2.5-3B + LoRA), score with discriminator."""
    log("Phase 7 v2: eval")
    update_status("eval", "generating outputs")
    import torch
    import urllib.request
    from transformers import (AutoTokenizer, AutoModelForCausalLM,
                              BitsAndBytesConfig, pipeline)
    from peft import PeftModel

    # Build eval prompt set from v2 normalized eval (200 prompts)
    eval_prompts = []
    with (DATA / "normalized_eval_v2.jsonl").open("r", encoding="utf-8") as f:
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
        body = json.dumps({"model": "gemma4:e4b", "messages": msgs, "stream": False, "think": False, "options": {"num_predict": 80}}).encode("utf-8")
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            out = payload.get("message", {}).get("content", "").strip()
        except Exception:
            out = ""
        baseline_outs.append(out)
    (EVAL / "baseline_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(baseline_outs)),
        encoding="utf-8",
    )

    log("  stopping Ollama to free VRAM for fine-tuned gen")
    os.system('taskkill /F /IM "ollama.exe" 2>NUL')
    os.system('taskkill /F /IM "ollama app.exe" 2>NUL')
    time.sleep(2)

    log("  loading fine-tuned Qwen2.5-3B + LoRA")
    bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=bnb_cfg,
                                                 device_map="auto", trust_remote_code=True,
                                                 attn_implementation="sdpa")
    lora_dir = CKPT / "qwen25_3b_human_lora" / "final"
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
            outs = model.generate(**inputs, max_new_tokens=80, do_sample=True,
                                  top_p=0.9, temperature=0.8, pad_token_id=tok.pad_token_id)
        text = tok.decode(outs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        finetuned_outs.append(text)
    (EVAL / "finetuned_outputs.jsonl").write_text(
        "\n".join(json.dumps({"prompt_idx": i, "output": o}) for i, o in enumerate(finetuned_outs)),
        encoding="utf-8",
    )
    del model, base
    torch.cuda.empty_cache()

    log("  scoring with discriminator")
    discrim_dir = CKPT / "discriminator_distilbert" / "final"
    clf = pipeline("text-classification", model=str(discrim_dir), tokenizer=str(discrim_dir),
                   device=0, top_k=None)
    def score_set(texts):
        preds = clf(texts, truncation=True, padding=True, max_length=128, batch_size=32)
        n_human = 0
        for p in preds:
            scores = {x["label"]: x["score"] for x in p}
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


def phase_writeup() -> None:
    log("Phase 8 v2: writeup")
    update_status("writeup", "generating findings doc")
    out = ROOT.parent / "HUMAN_LIKE_TRAINING_REPORT_V2.md"
    chunks = ["# Human-Like Conversation Training Report (v2)", "", f"**Run completed:** {now_iso()}", ""]
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
    parser.add_argument("--phase", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reset", default=None)
    args = parser.parse_args()
    if args.status:
        if STATUS.exists():
            print(STATUS.read_text(encoding="utf-8"))
        else:
            print("(no STATUS_V2.md yet)")
        return
    if args.reset:
        m = marker_path(args.reset)
        if m.exists():
            m.unlink()
            print(f"reset {args.reset}")
        return
    log(f"=== V2 Pipeline driver invoked ({args.phase or 'all phases'}) ===")
    phases_to_run = [args.phase] if args.phase else PHASES
    for p in phases_to_run:
        if p not in PHASE_FNS:
            log(f"unknown phase {p}"); continue
        if is_done(p):
            log(f"phase {p}: already done, skipping"); continue
        try:
            PHASE_FNS[p]()
            update_status(p, "done")
        except Exception as e:
            log(f"phase {p} FAILED: {type(e).__name__}: {e}")
            log(traceback.format_exc())
            update_status(p, f"FAILED — {type(e).__name__}: {e}")
            raise
    log("=== V2 Pipeline driver finished ===")


if __name__ == "__main__":
    main()
