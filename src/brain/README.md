# Module 04: Brain

LLM routing, system prompt construction, conversation context, and tool call orchestration.

## Responsibility

Brain is Aether's decision-making core. It receives every user message via EventBus, selects
the correct LLM tier based on content, fetches conversation history and RAG context in parallel,
constructs the full system prompt with Aether's persona, and runs the agentic tool-calling
loop when needed. The routing is invisible to the user — he always sees Aether, never model names.

## Key Files

- `handler.py` — Main event handler (`on_user_message`): orchestrates the full pipeline per
  message. Detects memory corrections, checks for agent dispatch patterns (research, email
  drafting), fetches RAG context + history + routes concurrently via `asyncio.gather`, wraps
  external content through content guard, and publishes `RESPONSE_TEXT_READY`. Sends a
  randomized "hold on" backchannel if processing exceeds 3 seconds. Fallback chain: primary
  tier -> CLAUDE -> GEMINI -> FAST (Ollama). Max 5 tool-call rounds per request.
  `register_brain_handlers()` subscribes `on_user_message` to `USER_MESSAGE`.

- `router.py` — `route(text) -> LLMTier`: keyword/pattern-based classifier.
  - FAST (Ollama qwen2.5:7b) — greetings and one-word replies
  - CLAUDE_HEAVY (claude-opus-4-6) — coding, debugging, refactoring
  - GEMINI (gemini-2.5-flash) — weather, news, real-time queries
  - GEMINI_PRO (gemini-2.5-pro) — research, analysis, deep dives
  - GEMINI_FAST (gemini-2.0-flash-lite) — summarization
  - CLAUDE (claude-sonnet-4-6) — everything else (default)

- `clients.py` — One async function per provider:
  - `call_ollama(prompt, system, model, messages)` — POST to Ollama `/api/chat`
  - `call_claude(prompt, system, heavy, messages)` — Anthropic SDK, text-only
  - `call_claude_with_tools(messages, system, tools, heavy)` — Anthropic SDK with tool_use
    blocks; returns `{text, tool_calls: [{id, name, arguments}]}`
  - `call_gemini(prompt, system, model_key, messages)` — google.generativeai SDK, converts
    messages list to Gemini alternating history format

- `persona.py` — `build_system_prompt(mode, rag_context, datetime_now) -> str`: assembles
  the full system prompt from the core Aether persona, current date/time, interaction mode
  hint (voice = brief, text = detailed, video = conversational), up to 5 RAG memory chunks,
  and the injection guard rule from `content_guard.py`.

- `content_guard.py` — Prompt injection defense:
  - `wrap_external_content(content, source)` — wraps tool outputs, web results, and file
    contents in `[EXTERNAL_CONTENT]...[END_EXTERNAL_CONTENT]` tags and logs a warning if
    injection patterns are detected.
  - `get_injection_guard_system_prompt()` — returns the system prompt clause that instructs
    the LLM to treat tagged content as data only, never as instructions.
  - `scan_for_injection(content)` — returns matched injection patterns for auditing.

## Interface Contract

Subscribes to:
- `USER_MESSAGE` — triggers `on_user_message`

Publishes:
- `RESPONSE_TEXT_READY` — `{text: str, emotion: str, is_interim: bool}` — final and interim
  (backchannel) responses
- `MEMORY_CORRECTION` — `{correction_text, original_context}` — when user corrects a fact
- `AGENT_TASK_COMPLETE` — `{intent, payload}` — after a research/writing agent finishes

Does NOT store conversation turns directly. Memory storage is handled by `src/memory/handler.py`
which subscribes independently to `USER_MESSAGE` and `RESPONSE_TEXT_READY`.

## Dependencies

External packages:
- `anthropic` — Claude client (claude-sonnet-4-6, claude-opus-4-6)
- `google-generativeai` — Gemini client
- `aiohttp` — Ollama HTTP calls
- `loguru` — logging

Other modules:
- `src/core/events` — EventBus publish/subscribe
- `src/shared/types` — EventType, AetherEvent, InteractionMode
- `src/shared/config` — get_settings(), get_yaml_config() (model names, token limits)
- `src/memory/store` — `get_recent_turns()`, `search_memory()` (RAG context)
- `src/tools/dispatcher` — `dispatch_tool()`, `TOOL_DEFINITIONS`
- `src/tools/approval_gate` — `request_approval()`, `HIGH_IMPACT_ACTIONS`
- `src/agents/dispatcher` — `dispatch(intent, payload)` for research/writing agents
- `src/persona/memory_corrections` — `detect_correction(text)`
