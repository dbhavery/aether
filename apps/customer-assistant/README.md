# Aether Customer Assistant

A **per-company, fine-tunable AI customer-support assistant** built on the
Aether Companion concept. Where Aether's [persona packs](../../docs/PERSONA-SCHEMA.md)
describe *a character*, this app's `company.yaml` profiles describe *a
business's support surface* — branding, scope, escalation, tools, knowledge
base, and LLM tier. Each company gets a grounded assistant that answers from
its own docs, escalates on its own rules, and is themed in its own colors.

This is a **self-contained local demo** (scaffold + working demo, not a full
product). It runs on CPU, needs no API keys, and degrades gracefully when
Ollama isn't running.

```
                ┌──────────────┐
  company.yaml ─┤  config.py   │  validated Pydantic profile
                └──────┬───────┘
                       │ compile system prompt
 knowledge/*.md ─► knowledge_base.py (ChromaDB + MiniLM) ─► retrieved context
                       │                                          │
                       ▼                                          ▼
                  assistant.py  ──►  llm.py (Ollama /api/chat)  ──►  answer + citations
                       ▲                                          │
                       │ POST /chat                               │ graceful stub if Ollama down
              widget.js (Shadow DOM, drop-in) ◄── server.py (FastAPI) ◄──┘
```

## What's in here

| Path | What it is |
| --- | --- |
| `src/customer_assistant/config.py` | `company.yaml` schema (Pydantic) + loader |
| `src/customer_assistant/knowledge_base.py` | RAG: ChromaDB + bundled CPU embeddings |
| `src/customer_assistant/llm.py` | Minimal Ollama chat client + graceful degradation |
| `src/customer_assistant/assistant.py` | Compiles profile + context → grounded answer |
| `src/customer_assistant/server.py` | FastAPI service (`/chat`, branding, static widget) |
| `scripts/ingest.py` | CLI to (re)build a company's vector store |
| `companies/northwind-outdoors/` | Worked sample company (invented) + 6 KB docs |
| `widget/widget.js` + `widget/index.html` | Drop-in embeddable chat widget + demo page |
| `COMPANY-SCHEMA.md` | Full documented `company.yaml` schema |
| `FINETUNING.md` | Real path to a per-company tuned model (scaffolded hook) |

## Run the demo locally

From the repo root (`C:/Users/dbhav/Projects/aether`):

```bash
# 1. Install deps (CPU-only, no API keys)
python -m pip install -r apps/customer-assistant/requirements.txt

# 2. Build the sample company's knowledge base
#    (downloads the small MiniLM embedding model once, then caches it)
cd apps/customer-assistant
python scripts/ingest.py

# 3. Start the service (serves the API AND the widget/demo page)
PYTHONPATH=src python -m customer_assistant.server
#   → http://127.0.0.1:8200
```

Then open **http://127.0.0.1:8200/** — the demo page loads with the chat bubble
in the bottom-right. Try:

- "How long do I have to return something?"
- "What are my shipping options?"
- "My package is lost." (triggers escalation)

### Optional: enable the LLM

The demo works without Ollama (answers come straight from retrieved articles
with an "offline" note). For full generated answers:

```bash
# install Ollama (https://ollama.com), then:
ollama pull qwen2.5:7b      # the default 'fast' tier model (see company.yaml)
ollama serve                # if not already running
```

Override the host with `OLLAMA_HOST` if Ollama isn't on `localhost:11434`.

### Call the API directly

```bash
curl -s http://127.0.0.1:8200/chat \
  -H "Content-Type: application/json" \
  -d '{"company_id":"northwind-outdoors","message":"What is your return window?"}'
```

```jsonc
{
  "company_id": "northwind-outdoors",
  "answer": "You have 60 days from delivery for a full refund… [returns-policy.md]",
  "citations": [{"source": "returns-policy.md", "snippet": "You can return most items within 60 days…"}],
  "model": "qwen2.5:7b",
  "degraded": false,
  "escalate": false
}
```

Endpoints: `GET /health`, `GET /companies`, `GET /companies/{id}/branding`,
`POST /chat`, `GET /widget.js`, `GET /`.

## Embedding the widget on a real site

One script tag — it themes itself from the company's branding:

```html
<script
  src="https://your-assistant-host/widget.js"
  data-company="northwind-outdoors"
  data-api="https://your-assistant-host"
  defer></script>
```

The widget renders inside a Shadow DOM so it can't collide with the host page's
CSS.

## Onboarding a new company

1. Copy `companies/northwind-outdoors/` to `companies/<your-company>/`.
2. Edit `company.yaml` (set `company.id`, branding, scope, escalation, LLM tier)
   — full field reference in `COMPANY-SCHEMA.md`.
3. Replace `knowledge/*.md` with the company's real FAQs/policies.
4. `python scripts/ingest.py <your-company>` then restart the server.
5. Point the widget at it with `data-company="<your-company>"`.

## Architecture notes / how this relates to Aether

- **Additive + self-contained.** This app does not import the Rust seven-layer
  core (`packages/l*`); it reuses the same *conventions* (typed profile →
  compiled system prompt; Ollama-by-default dispatch matching
  `configs/default_config.yaml`; local ChromaDB retrieval mirroring
  `src/memory/`) in a small Python service.
- **`company.yaml` ≈ `persona.yaml`.** Same idea — a typed, inspectable,
  shareable profile compiled at runtime — applied to a business instead of a
  character.
- **Ollama is the default**, models pulled from Aether's `llm.tier_map`
  (`fast` → `qwen2.5:7b`).

## Scaffolded vs. production-TODO

| Working in this demo | Scaffolded / production-TODO |
| --- | --- |
| `company.yaml` schema + strict validation | Tool **execution** (advertised, not run — would route through L5 policy) |
| RAG ingest + retrieval + citations | Auth / API keys / per-company rate limiting |
| Ollama chat + graceful offline stub | Streaming responses (currently single-shot) |
| Multi-company discovery + isolation | Conversation memory across turns (stateless per request today) |
| Drop-in themed widget | CORS allowlist per company (demo allows `*`) |
| Fine-tuning config hook (`fine_tuned_model`) | Actual training pipeline (documented in `FINETUNING.md`) |
| Branding-driven widget theming | Logo asset handling / file uploads |
