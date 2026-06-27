# Company Profile Schema (`company.yaml`)

A **company profile** is to the Customer Assistant what a [persona pack](../../docs/PERSONA-SCHEMA.md)
is to the Aether Companion. Where a `persona.yaml` describes *one character's*
voice, tone, and avatar, a `company.yaml` describes *one business's* support
surface: branding, what the assistant may help with, when to escalate to a
human, which tools it may use, where its knowledge base lives, and which LLM
tier/temperature to run.

The profile is **compiled at runtime** into a support-assistant system prompt
(see `src/customer_assistant/assistant.py::build_system_prompt`). The canonical,
validated implementation of this schema is `src/customer_assistant/config.py`
(Pydantic models, `extra="forbid"` — unknown keys fail loudly).

---

## Folder layout

```
companies/<company_id>/
├── company.yaml          # this schema (REQUIRED)
├── knowledge/            # markdown docs ingested into the RAG store
│   ├── shipping-policy.md
│   ├── returns-policy.md
│   └── ...
└── .chroma/              # persisted vector store (generated, gitignored)
```

A directory is treated as an onboarded company if it contains a `company.yaml`.
Directories whose name starts with `_` are skipped (reserved for templates).

---

## Top-level fields

```yaml
schema_version: 1          # int — bump when this format changes

company:                   # REQUIRED — identity
  id: "northwind-outdoors" # REQUIRED — lowercase slug (a-z, 0-9, hyphens). Stable; never change after launch.
  display_name: "Northwind Outdoors"   # REQUIRED — shown in the widget header
  tagline: "Gear for people who'd rather be outside"   # optional
  website: "https://northwind-outdoors.example.com"    # optional
  support_email: "support@northwind-outdoors.example.com"  # optional
```

### `branding` — visual + voice identity

```yaml
branding:
  logo: null               # path relative to the company dir, or a URL, or null
  colors:                  # hex strings (#rgb or #rrggbb). Widget themes from these.
    primary: "#1f6f54"
    accent: "#f4a23b"
    background: "#0f1411"
    surface: "#161d18"
    text: "#e8efe9"
  tone: "warm, outdoorsy, and practical"   # injected into the system prompt
  greeting: "Hey there! I'm the Northwind assistant…"  # first message in the widget
```

### `support` — scope guardrails

```yaml
support:
  in_scope:                # the assistant is told it helps with these
    - "order status and tracking"
    - "returns, exchanges, and refunds"
  out_of_scope:            # the assistant is told to defer/escalate on these
    - "wholesale / B2B pricing"
    - "legal disputes or chargebacks"
  languages: ["en"]        # advisory; not enforced in the demo
```

### `escalation` — human handoff

```yaml
escalation:
  enabled: true
  triggers:                # case-insensitive substring match against the user message
    - "speak to a human"
    - "lost package"
    - "refund over $300"
  contact:
    email: "support@…"
    phone: "1-800-555-0142"
    hours: "Mon–Fri, 8am–6pm PT"
  message: "I'll connect you with a member of our support team…"
```

When a user message contains a trigger, the `/chat` response sets
`escalate: true` (the widget shows an "Escalating to a human" badge) and the
system prompt instructs the model to deliver the escalation `message` + contact
details.

### `tools` — allowed tool calls (SCAFFOLD)

```yaml
tools:
  - name: "lookup_order_status"
    description: "Look up an order's status and tracking by order number"
    enabled: false         # demo: advertised in the prompt, NOT executed
```

In this demo, **enabled tools are described to the model but never executed**.
Production tool execution would route through Aether's L5 policy layer
(`packages/l5-policy`), the single writer for side effects — see the repo
`CLAUDE.md` §1.5.

### `knowledge_base` — RAG configuration

```yaml
knowledge_base:
  path: "knowledge"        # folder (relative to company dir) of .md docs
  collection: null         # ChromaDB collection name; defaults to "<id>_kb"
  chunk_size: 800          # chars per chunk (100–4000)
  chunk_overlap: 120       # chars of overlap (< chunk_size)
```

### `llm` — model dispatch

```yaml
llm:
  tier: "fast"             # fast | main | heavy — maps to aether llm.tier_map
  model: null              # explicit Ollama model; overrides tier when set
  temperature: 0.3         # 0.0–2.0
  max_tokens: 512          # 16–8192
  fine_tuned_model: null   # per-company tuned model — see FINETUNING.md
```

**Model resolution priority:** `fine_tuned_model` → `model` → tier-mapped model.
The default `tier_map` mirrors `configs/default_config.yaml`:

| tier | model |
| --- | --- |
| fast | `qwen2.5:7b` |
| main | `qwen2.5:14b` |
| heavy | `qwen2.5:32b` |

---

## Onboarding a new company

1. `cp -r companies/northwind-outdoors companies/<your-company>` (or start fresh).
2. Edit `company.yaml` — set `company.id` to your slug and fill in branding,
   scope, escalation, and LLM tier.
3. Replace the markdown files under `knowledge/` with the company's real FAQs
   and policies.
4. Build the knowledge base: `python scripts/ingest.py <your-company>`.
5. Restart the server. The widget references the company via
   `data-company="<your-company>"`.
