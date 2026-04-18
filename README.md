<p align="center">
  <img src="personas/aurora/avatar/portrait.png" width="180" alt="Aurora" />
  <img src="personas/caelum/avatar/portrait.png" width="180" alt="Caelum" />
  <img src="personas/luma/avatar/portrait.png" width="180" alt="Luma" />
</p>

<h1 align="center">Aether</h1>

<p align="center"><strong>A desktop AI companion you actually own.<br/>
Pick a face. Pick a voice. Pick a mind. They live on your machine.</strong></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.13+-blue.svg" alt="Python 3.13+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/status-public%20preview-e3b770" alt="Public preview">
</p>

---

## What Aether is for

Aether is a **desktop AI companion**. You install it once. You set it up once. After that, it's *yours* — a specific character you picked, with a voice you picked, living quietly on your own computer, ready whenever you are.

There are three ways to talk to it:

- **Text chat** — streaming replies, markdown, everything you'd expect.
- **Voice** — push-to-talk microphone, local speech-to-text, persona-cloned voice back at you.
- **Video** — the same character, animated, lip-synced, looking at you on a call.

You can **switch any time** without losing context. You can **switch the character** without losing memory. You can **switch the LLM** powering it without losing either.

---

## Why you want it

**Because the assistants you have right now aren't yours.**

Cloud assistants send every word you say to a server, train on a slice of it, charge you per request, and change the personality every six weeks without asking. They're rented. Aether is owned.

Here's what that unlocks:

### 1. Privacy by default
Your conversations, your memory, your voice clone, your API keys — all live on your machine. In the OS keyring for secrets, in a local ChromaDB for memory, in your own home directory for configuration. Nothing leaves unless **you** configured a cloud provider yourself, and even then only the traffic to *that* provider.

### 2. Cost that rounds to zero
Point it at a local Ollama model and you get a 449 ms voice latency at literally **$0 per query**. Bring your own OpenAI/Anthropic/Google key and pay their rate — no middleman markup, no subscription, no monthly fee to Aether. The product is free; the inference is whatever you want it to be.

### 3. A relationship, not a session
Aether remembers the last time you talked to it. It remembers that you already told it what you do for work. It remembers your kids' names and your dog's name and that you're training for a half-marathon. There's no "reset" button because there's no reason to hit one — it's been the same character the whole time, building on what it already knows.

### 4. Twelve personas, not one
Different moods, different tasks, different people in your life who want different things out of an assistant. Aurora is warm and grounded. Caelum is structured and precise. Luma is playful. Nine more pre-built characters ship with v1.0, and you can author your own with a YAML file and a portrait.

### 5. Any LLM you want
Aether uses [litellm](https://github.com/BerriAI/litellm) under the hood, which means 100+ providers work out of the box. Ollama, Anthropic, OpenAI, Google, Groq, OpenRouter — pick per-tier, or let Aether route automatically between a fast local model for greetings and a heavy cloud model for real reasoning.

### 6. Open-source, MIT
You can read every line. You can fork it. You can ship your own branded build. You can trust it because you can verify it.

---

## Who it's for

- **People who care about privacy** and don't want every conversation going through OpenAI.
- **Developers** who want a real local-first AI runtime to build on.
- **Tinkerers** who want to author custom personas, voices, and prompts.
- **Anyone** who just wants a calm, consistent companion at their desk without a monthly bill.

---

## Download

> **Status — public preview (v1.0.0-pre).** The runtime is feature-complete and E2E-verified on Windows 11; a packaged installer is the next milestone. For now you run from source.

```bash
git clone https://github.com/dbhavery/aether.git
cd aether
git checkout dev

python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

# Optional — local voice (STT + TTS, needs a GPU for best results):
#   pip install -r requirements-voice.txt
#   pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 \
#       --index-url https://download.pytorch.org/whl/cu128
```

Start the backend and the UI:

```bash
# terminal 1
python -m src.main

# terminal 2
cd frontend
npm install --legacy-peer-deps
npm run dev

# browser → http://127.0.0.1:3000/
```

First launch walks you through **eight screens** — welcome, pick a face, pick a personality, name them, pick an LLM, pick a voice mode, accept the (short, honest) Terms, and you're talking.

---

## What you get out of the box

| Surface | What ships |
|---|---|
| **Personas** | 3 fully-rendered packs (Aurora / Caelum / Luma) + 9 placeholder slots you can fill with `scripts/persona_generator/` |
| **LLM providers** | litellm-backed: Ollama, OpenAI, Anthropic, Google, Groq, OpenRouter, "Aether Guest" free tier, plus anything else litellm supports — 100+ models |
| **Voice in** | faster-whisper (local), ElevenLabs Scribe (optional cloud fallback) |
| **Voice out** | Chatterbox Turbo with per-persona voice cloning, or ElevenLabs |
| **Video mode** | Headshot avatar with lip-sync (LivePortrait-ready; preprocessing is opt-in) |
| **Memory** | Hybrid BM25 + dense-vector search via ChromaDB, per-persona isolation |
| **Settings** | Sandbox panel: swap persona, swap provider, swap tier map, inspect memory, manage keys |
| **Secrets** | OS keyring (Windows Credential Manager / macOS Keychain / Secret Service on Linux). Never plaintext on disk. |
| **Desktop shell** | Optional pywebview native window wrapper — `desktop/launcher.ps1` |

---

## Hardware notes

| Use case | Minimum | Recommended |
|---|---|---|
| Text chat only (cloud LLM) | Any machine that runs Python 3.13 | — |
| Text chat + local LLM (Ollama) | 16 GB RAM, 8 GB VRAM | 32 GB RAM, 12+ GB VRAM |
| Voice (local STT + TTS) | NVIDIA GPU, 6 GB VRAM | 8 GB+ VRAM |
| Video avatar | NVIDIA GPU, 8 GB VRAM | 12 GB+ VRAM |
| OS | Windows 10/11 primary; code runs on macOS + Linux but not yet packaged |

No GPU? Run **cloud BYOK** and Aether is a pure network client. Everything still works.

---

## What's NOT in v1.0

These are deferred to the ground-up v2 rebuild (see [`docs/PRODUCT-PLAN.md § 2`](docs/PRODUCT-PLAN.md)):

- Tool use / agent workflows (file system, browsing, IDE actions)
- Vision / image understanding
- Mobile client
- Full-body photorealistic avatar
- Real-time interruption / barge-in
- Hosted cloud tier
- Packaged installers for macOS + Linux

---

## Build your own persona

Every persona is a folder of YAML + images + one 20s voice reference WAV. Full schema: [`docs/PERSONA-SCHEMA.md`](docs/PERSONA-SCHEMA.md). Recipe + generator scripts: [`scripts/persona_generator/README.md`](scripts/persona_generator/README.md).

If your persona follows the schema, Aether loads it automatically on next boot — no code changes, no builds, no installer rebuild.

---

## Links

- **Source** — [github.com/dbhavery/aether](https://github.com/dbhavery/aether)
- **Issues / bug reports** — [github.com/dbhavery/aether/issues](https://github.com/dbhavery/aether/issues)
- **Roadmap** — [`docs/PRODUCT-PLAN.md`](docs/PRODUCT-PLAN.md)
- **Architecture** — [`docs/ARCHITECTURE-V2.md`](docs/ARCHITECTURE-V2.md)
- **Portfolio** — [dbhavery.dev](https://dbhavery.dev)

---

## License

MIT — use it, fork it, ship your own build. See [`LICENSE`](LICENSE).
