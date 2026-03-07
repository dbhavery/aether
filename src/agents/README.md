# Module 11: Agents

Specialist sub-agents dispatched by Aether's Brain to handle research and writing tasks.

## Responsibility

The agents module provides a dispatcher that routes intents from the Brain to the correct
specialist agent. Each agent runs its task asynchronously, tracks its own state in the
in-memory task registry, and returns a result string that Aether presents as her own work.
The user never interacts with agents directly — he only ever sees Aether's name. The task
registry is polled by the desktop TaskPanel every 5 s so the user can see running and completed
work on demand.

## Key Files

- `base.py` — shared data types: `AgentStatus` enum (`pending/running/complete/failed`) and
  `AgentTask` dataclass (`task_id`, `agent_name`, `instruction`, `status`, `result`, `error`,
  `metadata`)
- `dispatcher.py` — `dispatch(intent, payload, context) -> str`; routes four intents:
  `research` → `run_research()`, `draft_email` / `draft_message` / `draft_document` →
  `draft_content()`; logs a warning and returns a graceful string for unknown intents
- `research_agent.py` — `run_research(query) -> str`; searches DuckDuckGo via `duckduckgo_search`
  (max 5 results), synthesizes with `claude-sonnet-4-6`; falls back to returning raw snippets
  if no API key is present; registers and updates a task entry for every run
- `writing_agent.py` — `draft_content(content_type, instructions, context) -> str`; drafts
  emails, messages, and documents using `claude-sonnet-4-6`; never sends anything — always
  returns the draft for the user's approval; falls back to a placeholder if no API key is present
- `task_registry.py` — in-memory `dict[str, AgentTask]` protected by `asyncio.Lock`;
  exports `register_task()`, `update_task()`, `get_task_summary()` (used by desktop
  TaskPanel), and `clear_completed_tasks()`

## Interface Contract

**Called by Brain:**
- `dispatch(intent: str, payload: str, context: str = "") -> str`
  - Supported intents: `"research"`, `"draft_email"`, `"draft_message"`, `"draft_document"`
  - Returns synthesized result string

**Called by Desktop (TaskPanel):**
- `get_task_summary() -> list[dict]` — returns all tasks sorted newest-first; each entry
  has keys: `task_id`, `agent`, `instruction` (80 chars max), `status`, `result_preview`
  (100 chars max)
- `clear_completed_tasks() -> int` — removes complete and failed tasks; returns count removed

**No EventBus subscriptions or publications.** Agents are driven by direct async calls from
the Brain, not by events.

## Dependencies

**External packages:**
- `duckduckgo_search` — web search for `research_agent`
- `anthropic` — `AsyncAnthropic` client for synthesis and drafting (both agents)
- `loguru` — logging

**Internal modules:**
- `src.shared.config` — `get_settings()` to read `anthropic_api_key`
- `src.agents.base` — `AgentTask`, `AgentStatus` (used by all agents and registry)
- `src.agents.task_registry` — `register_task()`, `update_task()` (used by both agents)
