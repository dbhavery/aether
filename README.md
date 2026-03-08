# Aether

A production AI voice assistant framework that handles the full pipeline from wake word to spoken response in under 450ms -- with multi-LLM routing that sends 70%+ of queries to free local models and reserves paid APIs for complex reasoning.

[![CI](https://github.com/dbhavery/aether/actions/workflows/ci.yml/badge.svg)](https://github.com/dbhavery/aether/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Modules](https://img.shields.io/badge/modules-12-blue.svg)](#module-overview)
[![Tests](https://img.shields.io/badge/tests-520+-brightgreen.svg)](#tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Why I Built This

Cloud voice assistants send every word you say to external servers, lock you into a single LLM provider, and charge per request with no way to optimize cost. Local alternatives sacrifice quality -- they work offline but can't match the reasoning ability of frontier models.

I wanted both: a voice assistant that runs locally by default (privacy, zero cost for simple queries) but escalates to Claude or Gemini when the question actually needs it. And I wanted the full stack -- wake word, speech-to-text, LLM routing, text-to-speech, animated avatar, persistent memory -- in a modular architecture where each piece can be tested, swapped, or disabled independently.

## What It Does

- **449ms p50 end-to-end voice latency** from wake word detection through STT, LLM routing, and TTS synthesis to audible response
- **5-tier LLM routing** selects the optimal model per query: simple greetings route to local Ollama (free, ~50ms), complex reasoning routes to Claude ($0.01-0.05 per query) -- balances cost vs. quality automatically
- **92.5% wake word detection accuracy** using Picovoice Porcupine with speaker verification via SpeechBrain ECAPA-TDNN
- **Real-time avatar animation** at 20-25 FPS on consumer GPU using LivePortrait, synced to speech output
- **Persistent memory with hybrid search** combining BM25 keyword matching and dense vector retrieval via ChromaDB -- the assistant remembers context across sessions
- **28 tools with extensible registry** including PC control, file operations, shell commands, and web search, all gated behind an approval system with audit logging

## Architecture

```
                         +------------------+
                         |    Desktop GUI   |  PySide6 native app
                         |   (Module 07)    |  Text / Voice / Video views
                         +--------+---------+
                                  | WebSocket :8765
                                  v
+---------------+    +------------------------+    +----------------+
|  Voice-In     |--->|     Core (Module 01)   |--->|  Voice-Out     |
|  (Module 02)  |    |  EventBus + WS Server  |    |  (Module 03)   |
|  Wake/VAD/STT |    |  Health :8767          |    |  TTS + Stream  |
+---------------+    +----------+-------------+    +----------------+
                                |
              +-----------------+------------------+
              |                 |                   |
    +---------v------+  +------v--------+  +-------v--------+
    | Brain           |  | Memory        |  | Tools           |
    | (Module 04)     |  | (Module 08)   |  | (Module 05)     |
    | 5-Tier LLM      |  | ChromaDB      |  | PC Control      |
    | Router           |  | BM25 + Dense  |  | Approval Gate   |
    | Intent Classify  |  | Fact Extract  |  | Audit Log       |
    +-----------------+  +---------------+  +---------+-------+
              |                                       |
    +---------v------+  +---------------+  +----------v------+
    | Agents          |  | Avatar        |  | Notifications   |
    | (Module 11)     |  | (Module 06)   |  | (Module 12)     |
    | Research/Write  |  | LivePortrait  |  | Cron + FCM      |
    +-----------------+  | 20-25 FPS     |  +-----------------+
                         +---------------+
```

All modules communicate exclusively through the **EventBus** -- a typed pub/sub backbone with backpressure support and per-event-type inflight limits. No module imports another module directly.

## Key Technical Decisions

- **PySide6 over Electron for the desktop client.** Native performance with a ~50MB footprint vs. 200MB+ for Electron. Direct GPU access for avatar rendering without IPC overhead. PySide6 also provides Qt's mature widget system without bundling a browser engine.

- **5-tier LLM routing over single-model.** Local Ollama handles 70%+ of queries (greetings, simple lookups, intent classification) at zero API cost. Claude is reserved for complex reasoning. This architecture means the assistant is useful even when cloud APIs are down, and monthly API costs stay low despite heavy usage.

- **ChromaDB over Pinecone for memory.** Local-first architecture -- no network latency for memory retrieval, no cloud dependency, no per-query billing. Memory search runs in single-digit milliseconds on local storage.

- **EventBus architecture over direct module coupling.** Modules publish and subscribe to typed events. This means the voice pipeline can be tested without the brain module, the brain can be tested without the tools module, and any module can be hot-swapped or disabled without cascading failures.

- **Whisper + Silero VAD over cloud STT.** Privacy-first -- no audio leaves the machine. Works fully offline. Silero VAD runs inference in ~1ms per audio frame, keeping CPU overhead negligible during continuous listening.

## Module Overview

| # | Module | Responsibility |
|---|--------|---------------|
| 01 | Core | WebSocket server, EventBus, config, health endpoint, startup orchestration |
| 02 | Voice-In | Audio capture, wake word (Porcupine), VAD (Silero), STT, speaker verification |
| 03 | Voice-Out | TTS synthesis (Chatterbox local / ElevenLabs cloud fallback), audio streaming |
| 04 | Brain | 5-tier LLM routing, system prompt construction, conversation management, tool dispatch |
| 05 | Tools | PC control, file ops, shell commands, approval gate, audit logging |
| 06 | Avatar | LivePortrait face animation, MJPEG streaming, 20-25 FPS on RTX 3090 |
| 07 | Desktop | PySide6 GUI -- text chat, voice call, and video call views |
| 08 | Memory | ChromaDB hybrid search (BM25 + dense), fact extraction, pattern learning |
| 09 | Media | Image understanding (vision LLM), face recognition (InsightFace) |
| 10 | Android | Kotlin + Jetpack Compose client (spec) |
| 11 | Agents | Research and writing specialist agents with task persistence |
| 12 | Notifications | APScheduler cron jobs, Windows toast (winotify), FCM push to Android |

## Results & Metrics

| Metric | Value |
|--------|-------|
| End-to-end voice latency (p50) | 449ms (wake word to audible response) |
| Wake word accuracy | 92.5% (Picovoice Porcupine) |
| Avatar frame rate | 20-25 FPS (RTX 3090, LivePortrait) |
| LLM routing tiers | 5 (Ollama / Claude / Claude Heavy / Gemini / Gemini Pro) |
| Local query cost | $0.00 (Ollama handles 70%+ of queries) |
| Cloud query cost | $0.01-0.05 per query (Claude, reserved for complex reasoning) |
| Memory search | Hybrid BM25 + dense vector retrieval via ChromaDB |
| Tool count | 28 registered tools with fuzzy matching |
| Codebase | 20K+ lines of Python across 12 modules |
| Test coverage | 520+ tests (unit + integration) |

## Demo

Desktop application -- not web-deployable. See [demo video](https://github.com/dbhavery/aether/wiki/demo) for a walkthrough of voice interaction, LLM routing, and avatar animation.

## Quick Start

```bash
# Clone and set up
git clone https://github.com/dbhavery/aether.git
cd aether
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install PyTorch with CUDA
pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128

# Install dependencies
pip install -r requirements.txt

# Pull local models
ollama pull nomic-embed-text
ollama pull qwen2.5:7b

# Configure (add your API keys)
cp .env.example .env

# Run
python -m src.main              # Start server
python -m src.desktop.app       # Start desktop client (separate terminal)
```

## Lessons Learned

1. **Voice pipeline buffering is the #1 reliability risk.** An STT buffer overflow caused a zombie process that stayed alive but unresponsive for 5 days -- CPU and memory looked normal, but no audio was being processed. I implemented a 4-layer defense: circuit breaker on the STT buffer, a pipeline health watchdog, EventBus backpressure with per-event inflight limits, and an external process supervisor that kills zombies after 3 failed health checks.

2. **LLM routing heuristics need continuous tuning.** My initial keyword-based router was ~60% accurate at selecting the right model tier. Switching to a 3-stage classifier (instant regex match, keyword patterns, then LLM-based intent classification as fallback) improved routing accuracy to ~85%. The remaining 15% is genuinely ambiguous queries where multiple tiers would produce acceptable results.

3. **Avatar rendering and voice processing compete for GPU memory.** LivePortrait and Whisper both want VRAM, and PyTorch's memory allocator does not release unused blocks promptly. I had to implement VRAM budgeting -- the shared module tracks allocations per component and forces garbage collection before handing VRAM to a different subsystem. Without this, OOM crashes occurred within 2-3 hours of continuous use.

## Tests

```bash
# Run the full test suite
python -m pytest tests/unit/ -v --tb=short

# Run integration tests (requires running services)
python -m pytest tests/integration/ -v --tb=short
```

520+ tests across 45 test files covering: EventBus pub/sub and backpressure, LLM routing tier selection and fallback chains, voice pipeline state machine transitions, memory store CRUD and hybrid search, tool approval gate and audit logging, agent task lifecycle, desktop GUI event handling.

## License

[MIT](LICENSE)
