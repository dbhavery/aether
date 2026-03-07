# Module 05: Tools

PC control tools, tool dispatching, and an approval gate for high-impact actions.

## Responsibility

Receives `TOOL_CALL_REQUESTED` events from Brain, validates and executes the named tool
against an explicit registry of allowed functions, and publishes the result back via
`TOOL_RESULT_READY`. High-impact actions (sending email, deleting files, running
scripts, etc.) are gated behind an approval flow that pauses execution, notifies the user via
the desktop, and waits up to 120 seconds for an explicit yes/no before proceeding.

## Key Files

- `handler.py` — `register_tools_handlers()`: subscribes `on_tool_call_requested` to
  the EventBus; validates tool name against registry; filters unexpected kwargs against
  the function signature before calling; publishes result or error event
- `dispatcher.py` — `dispatch_tool(name, args) -> str`: alternative direct-call entry
  point (used outside the EventBus path); also houses `TOOL_DEFINITIONS` in Claude
  tool_use JSON schema format for Brain's LLM API calls
- `pc_control.py` — five async tool functions: `open_application()` (allowlist-only:
  notepad, calculator, explorer, chrome, code, terminal), `type_text()`,
  `get_clipboard()` (win32clipboard), `take_screenshot()` (path-traversal-safe, saves
  to `./data\screenshots\`), `list_running_apps()` (psutil, capped at 50)
- `approval_gate.py` — `request_approval(action, description, details) -> bool`:
  checks `ActionRisk` level (SAFE/CONFIRM/EXPLICIT), publishes `APPROVAL_REQUESTED`
  event, awaits asyncio.Future resolved by `resolve_approval()`; times out at 120s and
  rejects; `is_approval_response(text)` parses natural-language yes/no from the user

## Interface Contract

Subscribes to:
- `TOOL_CALL_REQUESTED` — payload: `{"tool_name": str, "args": dict}`

Publishes:
- `TOOL_RESULT_READY` — payload: `{"tool_name": str, "success": bool, ...result fields}`
- `APPROVAL_REQUESTED` — payload: `{"approval_id": str, "action": str, "description": str,
  "details": dict, "risk": str}`

Exports:
- `register_tools_handlers()` — called at startup by orchestration
- `dispatch_tool(name, args) -> str` — direct dispatch (Brain path)
- `TOOL_DEFINITIONS` — list of Claude tool_use JSON schema dicts for Brain
- `request_approval(action, description, details) -> bool` — called by Brain before
  executing any action in `HIGH_IMPACT_ACTIONS`
- `resolve_approval(approval_id, approved)` — called by Brain when the user responds
- `is_approval_response(text) -> bool | None` — natural-language yes/no parser

## Dependencies

External packages:
- `pyautogui` — keyboard/mouse control (`FAILSAFE=True`, `PAUSE=0.1s`)
- `psutil` — process enumeration for `list_running_apps`
- `pywin32` (`win32clipboard`) — clipboard access
- `loguru` — structured logging

Internal modules:
- `src.core.events` — EventBus pub/sub
- `src.shared.config` — `get_settings()` for `aether_data_path`
- `src.shared.types` — `EventType`, `AetherEvent`
