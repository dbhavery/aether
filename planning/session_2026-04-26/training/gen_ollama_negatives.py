"""STEP 2C: generate AI-source negatives from Ollama models (gemma4, qwen3:8b).

Uses /api/chat with think:false (gemma4 and qwen3:8b are reasoning
models — without think:false they spend num_predict on internal
thinking and return empty content).

Saves to eval_v4/gen_gemma4.jsonl and eval_v4/gen_qwen3.jsonl.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL_V4 = ROOT / "eval_v4"
PROMPTS_FILE = EVAL_V4 / "discrim_prompts.jsonl"

OLLAMA_HOST = "http://127.0.0.1:11434"
N_PER_MODEL = 2000
TIMEOUT_S = 60

SYSTEM = (
    "You are continuing a casual conversation between two people. "
    "Reply naturally as the other speaker — short, human, no AI mannerisms. "
    "Match the tone, register, and length of the dialog you've been shown."
)

MODELS = [
    ("gemma4", "gemma4:e4b", EVAL_V4 / "gen_gemma4.jsonl"),
    ("qwen3", "qwen3:8b", EVAL_V4 / "gen_qwen3.jsonl"),
]


def ensure_ollama() -> None:
    """Make sure ollama is running. If not, start it."""
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=3) as r:
            r.read()
        print("  ollama already up")
        return
    except Exception:
        pass
    print("  starting ollama serve...")
    # Background start. Ollama is on PATH on this system.
    os.system('start /B "" ollama serve')
    for _ in range(30):
        time.sleep(2)
        try:
            with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=3) as r:
                r.read()
            print("  ollama up")
            return
        except Exception:
            continue
    raise RuntimeError("ollama did not start")


def chat(model: str, p: dict, max_tokens: int = 100) -> str:
    msgs = [{"role": "system", "content": SYSTEM}]
    for t in p["context"]:
        role = "user" if t["speaker"] == "A" else "assistant"
        msgs.append({"role": role, "content": t["text"]})
    body = json.dumps({
        "model": model,
        "messages": msgs,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.8,
            "top_p": 0.9,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message", {}).get("content") or "").strip()


def load_prompts():
    rows = []
    with PROMPTS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows[:N_PER_MODEL]


def run_model(label: str, model: str, out_path: Path, prompts: list[dict]) -> None:
    if out_path.exists():
        existing = sum(1 for _ in out_path.open(encoding="utf-8"))
        if existing >= N_PER_MODEL:
            print(f"[{label}] already complete at {out_path} ({existing} rows), skipping")
            return
        print(f"[{label}] resuming at {existing}/{N_PER_MODEL}")
        start = existing
    else:
        start = 0

    f = out_path.open("a", encoding="utf-8")
    t0 = time.time()
    fails = 0
    for i in range(start, len(prompts)):
        p = prompts[i]
        try:
            text = chat(model, p)
        except Exception as e:
            fails += 1
            text = ""
            if fails % 10 == 1:
                print(f"  [{label}] gen error #{fails}: {e}")
        f.write(json.dumps({
            "prompt_idx": i,
            "source": p.get("source", "?"),
            "output": text,
        }, ensure_ascii=False) + "\n")
        if (i + 1) % 100 == 0:
            f.flush()
            elapsed = time.time() - t0
            rate = (i + 1 - start) / max(elapsed, 1e-3)
            eta = (len(prompts) - i - 1) / max(rate, 1e-3)
            print(f"  [{label}] {i+1}/{len(prompts)} in {elapsed:.0f}s "
                  f"({rate:.2f}/s, ETA {eta:.0f}s, fails {fails})")
    f.close()
    print(f"[{label}] done: {len(prompts)} prompts in {time.time()-t0:.0f}s "
          f"(fails {fails})")


def main() -> int:
    ensure_ollama()
    prompts = load_prompts()
    print(f"loaded {len(prompts)} prompts")
    for label, model, out_path in MODELS:
        print(f"\n=== generating {label} ({model}) ===")
        run_model(label, model, out_path, prompts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
