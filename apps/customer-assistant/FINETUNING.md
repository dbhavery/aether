# Per-Company Fine-Tuning

This document describes the **real path** to a per-company fine-tuned model and
how it plugs into the assistant. The hook is **scaffolded** in this demo: the
config field exists and is honored at model-resolution time, but no training is
performed here.

> TL;DR — RAG (retrieval) handles *facts*; fine-tuning handles *behaviour/voice*.
> Start with RAG (already built). Fine-tune only when a company needs a
> consistent style, format, or domain phrasing that prompting alone can't hold.

---

## 1. Where it plugs in

The hook is the `llm.fine_tuned_model` field in `company.yaml`:

```yaml
llm:
  tier: "fast"
  model: null
  fine_tuned_model: "northwind-support:latest"   # ← set after training
```

Model resolution (`config.py::CompanyProfile.effective_model`) checks in order:

1. `fine_tuned_model` — if set, used directly.
2. `model` — explicit Ollama model name.
3. tier-mapped model — `fast`/`main`/`heavy` → `configs/default_config.yaml`.

So flipping a company onto its tuned model is a **one-line config change**, no
code edit. In the broader Aether architecture this mirrors L4-router tier
selection (`packages/l4-router`): the company profile chooses a tier or an
explicit/tuned model, and the router dispatches to the provider (Ollama by
default).

---

## 2. When to fine-tune (vs. just RAG)

| Need | Use |
| --- | --- |
| Up-to-date facts, policies, prices | **RAG** (this demo already does it) |
| Consistent brand voice / formatting | Fine-tune |
| Domain jargon the base model gets wrong | Fine-tune |
| Shorter/cheaper prompts (fold instructions into weights) | Fine-tune |
| One-off knowledge that changes weekly | **RAG** (never fine-tune on volatile data) |

RAG + a small instruction-tuned base (qwen2.5:7b) is enough for most support
assistants. Reach for fine-tuning when prompt engineering plateaus.

---

## 3. Training data format

Collect real (anonymized) support transcripts and curate them into chat-format
JSONL. Each line is one conversation:

```jsonl
{"messages": [
  {"role": "system", "content": "You are the Northwind Outdoors support assistant…"},
  {"role": "user", "content": "How long do I have to return a jacket?"},
  {"role": "assistant", "content": "You've got 60 days from delivery for a full refund, as long as it's unworn with tags on. [returns-policy.md]"}
]}
```

Guidelines:

- **200–2,000 examples** is a typical useful range for style/format adaptation.
- Keep the `system` message close to the one `build_system_prompt` produces so
  training and inference match.
- **Preserve the citation style** (`[source.md]`) in assistant turns so the
  tuned model keeps grounding its answers.
- **Scrub PII** — names, emails, order numbers, addresses. Never train on raw
  customer data without consent and redaction.

---

## 4. Training options (all local-capable)

Because Aether defaults to **Ollama**, the most direct path keeps the tuned
model in Ollama:

### Option A — LoRA fine-tune, then import into Ollama (recommended)

1. Fine-tune a LoRA adapter on the base model (e.g. `qwen2.5:7b`) with a local
   trainer such as **Unsloth**, **axolotl**, or **Hugging Face PEFT**.
   (See the repo's `flux-lora-finetune` reference for the QLoRA/VRAM playbook —
   the LoRA mechanics transfer from diffusion to LLMs.)
2. Merge the adapter and convert to GGUF (`llama.cpp` `convert_hf_to_gguf.py`),
   or keep the adapter and reference it from a `Modelfile`.
3. Register it with Ollama:

   ```Dockerfile
   # Modelfile
   FROM qwen2.5:7b
   ADAPTER ./northwind-support-lora.gguf
   SYSTEM "You are the Northwind Outdoors support assistant…"
   ```

   ```bash
   ollama create northwind-support -f Modelfile
   ```
4. Point the company at it: `fine_tuned_model: "northwind-support:latest"`.

### Option B — full SFT

Same data format; full-parameter SFT on a small base if you have the VRAM. More
expensive, rarely needed for support-voice adaptation.

### Option C — hosted fine-tune

If a company opts into a cloud provider, fine-tune there and set
`fine_tuned_model` to the provider's model id (and switch `llm.provider` at the
deployment level). Out of scope for the local demo.

---

## 5. Evaluation before rollout

Don't ship a tuned model on vibes. Before flipping `fine_tuned_model`:

1. Hold out ~10% of curated transcripts as an eval set.
2. Compare tuned vs. base on: factual grounding (does it still cite?),
   escalation correctness (does it escalate on triggers?), tone match, and
   refusal of out-of-scope asks.
3. The Aether eval harness (`tools/` / `research/evals`) is the natural home for
   a per-company support eval suite.

---

## 6. What is scaffolded vs. real here

| Piece | Status |
| --- | --- |
| `fine_tuned_model` config field | **Real** — validated + honored at resolution |
| Model-resolution priority | **Real** — `effective_model()` |
| Ollama dispatch to a custom model | **Real** — works the moment the model exists in Ollama |
| Training pipeline / data prep scripts | **Scaffold** — documented here, not implemented |
| Per-company eval suite | **Scaffold** — wiring described, not implemented |
