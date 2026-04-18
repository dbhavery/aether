# Aether

**A local-first AI companion with voice, avatar, and persistent memory — runs on your machine, talks to the LLM of your choice.**

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> v1.0 public release. Status: pre-alpha on `dev` branch. Installer / packaged release coming.

---

## What is Aether

Aether is a desktop AI companion you install on your own machine. Pick a character (one of 12 pre-built personas), pick how you want to talk to them (chat, voice, or animated video), pick which LLM you want powering the conversation (bring your own key, use a local model via Ollama, or use the free-tier guest mode). Your conversations stay on your machine — nothing leaves unless you configured a cloud provider yourself.

Three interaction modes:

1. **Chat** — text conversation with streaming responses.
2. **Voice** — push-to-talk microphone, local STT + TTS, transcript visible.
3. **Video** — headshot avatar with lip-sync, idle animation, and per-persona voice.

Plus a **sandbox / settings** panel that lets you switch personas, change LLM providers, manage memory, and tune voice parameters at any time.

## Why it exists

Cloud assistants send every word to external servers, lock you into one model, and charge per request. Running a local assistant alone sacrifices reasoning quality. Aether lets you use both: local for privacy-sensitive or trivial queries, cloud frontier models when you actually need the horsepower — and you choose per-provider, per-tier, or let the router decide automatically.

## Install

> Pre-alpha — no installer yet. To run from source:

```bash
git clone https://github.com/dbhavery/aether.git
cd aether
git checkout dev

python -m venv .venv
.venv\Scripts\activate             # Windows
# source .venv/bin/activate         # macOS/Linux

# GPU-dependent deps — installs PyTorch with CUDA
pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 \
    --index-url https://download.pytorch.org/whl/cu128

pip install -r requirements.txt
```

## Run

```bash
# Start the backend server
python -m src.main
```

First run launches in onboarding mode. Once the frontend (Next.js, scaffolded in an upcoming commit) connects, the wizard walks you through:

1. Pick an avatar (1 of 12 bundled personas).
2. Pick a personality (independent of avatar).
3. Name your assistant.
4. Configure an LLM provider (Ollama / Anthropic / OpenAI / Google / Groq / OpenRouter / guest).
5. Configure voice (local / ElevenLabs / off).
6. Accept Terms & Privacy.

After the wizard, your config lives at `<user_data_dir>/aether/config.yaml` and your secrets in the OS keyring. On Windows that's `%APPDATA%\aether\config.yaml`.

## Requirements

| Feature | Minimum | Recommended |
|---------|---------|-------------|
| Chat mode | Any machine with Python 3.13 | — |
| Local LLM (Ollama) | 16 GB RAM | 32 GB RAM, 8 GB+ VRAM |
| Cloud LLM (BYOK) | Internet + API key | — |
| Voice (local STT+TTS) | NVIDIA GPU, 6 GB+ VRAM | 8+ GB VRAM |
| Voice (cloud) | Internet + ElevenLabs key | — |
| Avatar (video mode) | NVIDIA GPU, 8 GB+ VRAM | 12+ GB VRAM |
| OS | Windows 10/11 (primary) | Windows 11 |

macOS and Linux are code-ready but not packaged or tested in v1.0.

## What's in v1.0

- Three interaction modes (chat, voice, video).
- 12 bundled personas (avatars + voices + personalities).
- Bring-your-own-key LLM support via `litellm` (100+ providers).
- Local LLM via Ollama.
- Local voice (faster-whisper STT + Chatterbox Turbo TTS).
- Persistent conversation memory with hybrid BM25 + dense-vector search via ChromaDB.
- Per-persona memory isolation.
- Onboarding wizard for first-run setup.
- Settings panel for runtime changes.
- Secrets stored in OS keyring, never plaintext.

## What's NOT in v1.0

Deferred to the ground-up v2 rebuild (see `docs/PRODUCT-PLAN.md` § 2):

- Tool use / agent workflows.
- Vision / image understanding.
- Mobile client.
- Full-body photorealistic avatar.
- Real-time interruption / barge-in.
- Hosted cloud tier.
- macOS and Linux installers.

## Documentation

- file:///C:/Users/dbhav/Projects/aether/docs/PRODUCT-PLAN.md — roadmap, phases, decisions.
- file:///C:/Users/dbhav/Projects/aether/docs/ARCHITECTURE-V2.md — system design, ports, events.
- file:///C:/Users/dbhav/Projects/aether/docs/PERSONA-SCHEMA.md — persona pack format (write your own).
- file:///C:/Users/dbhav/Projects/aether/docs/ONBOARDING-SPEC.md — wizard flow.
- file:///C:/Users/dbhav/Projects/aether/docs/LLM-PROVIDERS.md — provider abstraction + key storage.
- file:///C:/Users/dbhav/Projects/aether/docs/SYNC-ISABELLE.md — upstream-port rules (developer-only).

## Contributing

Not currently accepting external contributions — pre-alpha. If you find a bug, open an issue at https://github.com/dbhavery/aether/issues

## License

MIT — see [LICENSE](LICENSE).

## Branches

- `master` — stable showcase snapshot (unchanged).
- `dev` — v1.0 productization.
- `feature/*` — individual feature branches off `dev`.

## Links

- Issues: https://github.com/dbhavery/aether/issues
- `dev` branch: https://github.com/dbhavery/aether/tree/dev
