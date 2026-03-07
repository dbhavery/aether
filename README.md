# Aether

[![CI](https://github.com/dbhavery/aether/actions/workflows/ci.yml/badge.svg)](https://github.com/dbhavery/aether/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A modular AI assistant framework with voice I/O, multi-LLM routing, persistent memory, animated avatar, and a native desktop client. Built for extensibility -- every capability is an isolated module communicating through a central EventBus.

## Key Capabilities

- **Multi-LLM Routing** -- 6-tier intelligent routing across Ollama (local), Claude, and Gemini models with automatic fallback chains
- **Voice Pipeline** -- Wake word detection, VAD, real-time STT (ElevenLabs Scribe / Whisper fallback), speaker verification, and TTS synthesis
- **Persistent Memory** -- ChromaDB hybrid search (BM25 + dense vectors), 3-tier memory hierarchy (VRAM/RAM/archive), automatic fact extraction and pattern learning
- **Animated Avatar** -- LivePortrait integration for real-time photorealistic face animation synced to speech
- **Desktop Client** -- PySide6 native app with text chat, voice call, and video call views; dark neumorphic design system
- **Agent System** -- Specialist agents (research, writing) dispatched transparently by the orchestrator
- **Tool Execution** -- PC control, file operations, shell commands, web search -- all gated behind an approval system with audit logging
- **Notifications** -- APScheduler cron jobs, Windows toast notifications, FCM push to Android
- **Persona Engine** -- Emotion tracking, proactive scheduling, bilingual support, configurable personality

## Architecture

```
                         +------------------+
                         |    Desktop GUI   |  PySide6 (Text / Voice / Video views)
                         |   (Module 07)    |
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
    | LLM Router      |  | ChromaDB      |  | PC Control      |
    | 6-Tier Routing   |  | 3-Tier Cache  |  | Approval Gate   |
    | Persona Builder  |  | Fact Extract  |  | Audit Log       |
    +-----------------+  +---------------+  +---------+-------+
              |                                       |
    +---------v------+  +---------------+  +----------v------+
    | Agents          |  | Avatar        |  | Notifications   |
    | (Module 11)     |  | (Module 06)   |  | (Module 12)     |
    | Research/Write  |  | LivePortrait  |  | Cron + FCM      |
    +-----------------+  +---------------+  +-----------------+
              |
    +---------v------+  +---------------+  +----------------+
    | Persona         |  | Media         |  | Android        |
    | Emotion Track   |  | (Module 09)   |  | (Module 10)    |
    | Proactive Sched |  | Vision + Face |  | Kotlin/Compose |
    +-----------------+  +---------------+  +----------------+
```

All modules communicate exclusively through the **EventBus** (`src/core/events.py`) -- a pub/sub backbone with backpressure support and per-event-type inflight limits.

## Module Overview

| # | Module | Directory | Responsibility |
|---|--------|-----------|---------------|
| 01 | Core | `src/core/` | WebSocket server, EventBus, config, health endpoint, startup orchestration |
| 02 | Voice-In | `src/voice/` | Audio capture, wake word (Porcupine), VAD (Silero), STT, speaker verification |
| 03 | Voice-Out | `src/voice/` | TTS synthesis (Chatterbox/ElevenLabs), audio streaming |
| 04 | Brain | `src/brain/` | LLM routing, system prompt construction, conversation management, tool orchestration |
| 05 | Tools | `src/tools/` | PC control, file ops, shell commands, approval gate, audit logging |
| 06 | Avatar | `src/avatar/` | LivePortrait face animation server, MJPEG streaming |
| 07 | Desktop | `src/desktop/` | PySide6 GUI -- text chat, voice call, video call views |
| 08 | Memory | `src/memory/` | ChromaDB hybrid search, 3-tier cache, fact extraction, pattern learning |
| 09 | Media | `src/media/` | Image understanding (vision LLM), face recognition (InsightFace) |
| 10 | Android | `src/android/` | Kotlin + Jetpack Compose client (spec only) |
| 11 | Agents | `src/agents/` | Research and writing agents with task persistence |
| 12 | Notifications | `src/notifications/` | APScheduler, Windows toast (winotify), FCM push |
| -- | Persona | `src/persona/` | Emotion tracking, proactive scheduling, memory corrections, busy detection |
| -- | Shared | `src/shared/` | Config, types, logging, HTTP client, VRAM manager |

## LLM Routing Strategy

Aether routes every message through a 3-stage classifier to select the optimal model:

```
User Message
    |
    v
[Stage 1: Instant Match]  -- regex patterns for greetings, farewells
    |  match? --> FAST (local Ollama)
    v
[Stage 2: Keyword Match]  -- regex for code, realtime, research, summarize
    |  match? --> CLAUDE_HEAVY / GEMINI / GEMINI_PRO / GEMINI_FAST
    v
[Stage 3: LLM Classify]   -- ask local model to classify the intent
    |  --> route to appropriate tier
    v
[Fallback Chain]           -- CLAUDE --> GEMINI --> FAST (local)
```

**Tier definitions:**

| Tier | Model | Use Case |
|------|-------|----------|
| FAST | Local Ollama (e.g. qwen2.5:7b) | Greetings, intent classification, instant responses |
| CLAUDE | claude-sonnet-4-6 | General conversation, reasoning |
| CLAUDE_HEAVY | claude-opus-4-6 | Coding, complex analysis |
| GEMINI | gemini-2.5-flash | Real-time tasks (weather, news, search) |
| GEMINI_FAST | gemini-2.0-flash-lite | Summarization, quick lookups |
| GEMINI_PRO | gemini-2.5-pro | Deep research, long-form analysis |

If any provider fails, the system falls through the chain automatically. The user never sees routing decisions.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Async | asyncio + winloop (Windows uvloop equivalent) |
| LLM Clients | anthropic, google-genai, aiohttp (Ollama) |
| Voice STT | ElevenLabs Scribe v2, faster-whisper (fallback) |
| Voice TTS | Chatterbox TTS (local), ElevenLabs Flash v2.5 (cloud fallback) |
| Wake Word | Picovoice Porcupine |
| Speaker ID | SpeechBrain ECAPA-TDNN |
| Memory | ChromaDB 1.5.2 (hybrid BM25 + dense), SQLite |
| Embeddings | nomic-embed-text v1 via Ollama |
| Desktop GUI | PySide6 6.10.2 |
| Avatar | LivePortrait (separate process) |
| Web Framework | FastAPI + uvicorn (health + data server) |
| Notifications | APScheduler, winotify, firebase-admin |
| GPU | PyTorch 2.7.0 + CUDA |
| Lint/Format | Ruff |
| Type Check | Pyright |
| Testing | pytest + pytest-asyncio |
| CI | GitHub Actions |

## Quick Start

### Prerequisites

- Python 3.13+
- NVIDIA GPU with CUDA support (recommended)
- [Ollama](https://ollama.com) running locally (for FAST tier + embeddings)

### Installation

```bash
# Clone
git clone https://github.com/dbhavery/aether.git
cd aether

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install PyTorch with CUDA (adjust cu128 to your CUDA version)
pip install torch==2.7.0+cu128 torchaudio==2.7.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128

# Install dependencies
pip install -r requirements.txt

# Pull embedding model
ollama pull nomic-embed-text
ollama pull qwen2.5:7b  # or your preferred local model
```

### Configuration

```bash
# Create .env from the required variables
cat > .env << 'EOF'
ANTHROPIC_API_KEY=your-key-here
GOOGLE_API_KEY=your-key-here
ELEVENLABS_API_KEY=your-key-here        # optional, for cloud STT/TTS
PICOVOICE_ACCESS_KEY=your-key-here      # optional, for wake word
AETHER_DATA_PATH=./data
CHROMA_PATH=./data/chroma
WEBSOCKET_PORT=8765
HEALTH_PORT=8767
DATA_SERVER_PORT=8766
LOG_LEVEL=DEBUG
EOF

# Create the YAML config (see aether_config.yaml.example for full options)
```

### Running

```bash
# Start the server
python -m src.main

# Start the desktop client (separate terminal)
python -m src.desktop.app
```

### Running Tests

```bash
python -m pytest tests/unit/ -v --tb=short
```

## Project Structure

```
aether/
+-- src/
|   +-- core/           # WebSocket server, EventBus, health, startup
|   +-- brain/          # LLM routing, persona, clients, content guard
|   +-- voice/          # Wake word, VAD, STT, TTS, speaker verify
|   +-- memory/         # ChromaDB store, embeddings, tier manager
|   +-- desktop/        # PySide6 GUI app, views, theme
|   +-- tools/          # PC control, file ops, approval gate, audit
|   +-- agents/         # Research + writing agents, task registry
|   +-- avatar/         # LivePortrait client/server/handler
|   +-- media/          # Image understanding, face recognition
|   +-- persona/        # Emotion tracking, proactive, corrections
|   +-- notifications/  # Scheduler, Windows toast, FCM
|   +-- data_server/    # FastAPI data storage endpoints
|   +-- shared/         # Config, types, logging, HTTP client
|   +-- main.py         # Entry point
+-- tests/
|   +-- unit/           # 40+ unit test files
|   +-- integration/    # End-to-end integration tests
+-- .github/workflows/  # CI pipeline
+-- pyproject.toml      # Project config, Ruff, Pyright, pytest
+-- requirements.txt    # Pinned dependencies
+-- LICENSE             # MIT
```

## Design Principles

1. **Module isolation** -- Each module owns its directory, README, and tests. Modules communicate only through the EventBus.
2. **No silent failures** -- Every error is logged with context. No bare `except:` blocks.
3. **Config-driven** -- Zero hardcoded values. All settings come from `.env` or `aether_config.yaml`.
4. **Graceful degradation** -- If a cloud API is unavailable, the system falls back to local models.
5. **Security by default** -- Tool execution requires approval. File access is path-validated. Shell commands are blocklisted.

## Stats

- **103 source files** | ~14,600 lines of Python
- **45 test files** | ~5,600 lines of tests
- **12 modules** with dedicated handlers and EventBus integration

## License

[MIT](LICENSE)
