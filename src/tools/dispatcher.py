"""Tool dispatcher — routes tool_name to the actual function and returns the result."""

import inspect
import json

from loguru import logger

from src.tools.audit_log import AuditTimer, log_tool_execution
from src.tools.file_ops import (
    create_directory,
    list_directory,
    read_file,
    search_files,
    write_to_file,
)
from src.tools.pc_control import (
    close_window,
    focus_window,
    get_active_window_title,
    get_clipboard,
    list_running_apps,
    maximize_window,
    minimize_window,
    open_application,
    take_screenshot,
    type_text,
)
from src.tools.shell_exec import run_command

TOOL_REGISTRY: dict[str, callable] = {
    # PC control
    "open_application": open_application,
    "type_text": type_text,
    "get_clipboard": get_clipboard,
    "take_screenshot": take_screenshot,
    "list_running_apps": list_running_apps,
    "focus_window": focus_window,
    "get_active_window_title": get_active_window_title,
    "minimize_window": minimize_window,
    "maximize_window": maximize_window,
    "close_window": close_window,
    # File operations
    "read_file": read_file,
    "write_to_file": write_to_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "create_directory": create_directory,
    # Shell
    "run_command": run_command,
}

# Tool definitions for LLM APIs (Claude tool_use format)
TOOL_DEFINITIONS = [
    {
        "name": "open_application",
        "description": "Open an application on the user's PC. Only allowlisted apps are permitted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the app to open (e.g., notepad, chrome, spotify)",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text using the keyboard at the current cursor position.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_clipboard",
        "description": "Get the current clipboard contents.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot of the primary monitor.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_running_apps",
        "description": "List currently running applications on the user's PC.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "focus_window",
        "description": "Focus a window by its title (partial match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Window title to search for"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "get_active_window_title",
        "description": "Get the title of the currently active window.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_file",
        "description": "Read a file's contents. Max 1MB. Blocked paths (.ssh, .env, credentials) are denied.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_to_file",
        "description": "Write content to a file. Max 100KB. Only in safe directories (Documents, AetherData).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {"type": "boolean", "description": "Append instead of overwrite (default false)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the directory"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for files matching a glob pattern in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.py', '**/*.txt')"},
            },
            "required": ["directory", "pattern"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory (with parents). Only in safe directories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path for the new directory"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": "Execute a shell command. Dangerous commands are blocked. Requires the user's approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 60)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "minimize_window",
        "description": "Minimize a window by its title (partial match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Window title to search for"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "maximize_window",
        "description": "Maximize a window by its title (partial match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Window title to search for"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "close_window",
        "description": "Close a window by its title (partial match). May lose unsaved work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Window title to search for"},
            },
            "required": ["title"],
        },
    },
]


async def dispatch_tool(name: str, args: dict) -> str:
    """Execute a tool by name with the given arguments. Returns result as string."""
    if name not in TOOL_REGISTRY:
        logger.warning(f"Dispatcher: unknown tool '{name}'")
        return f"Error: tool '{name}' not found. Available: {', '.join(TOOL_REGISTRY.keys())}"
    try:
        tool_fn = TOOL_REGISTRY[name]
        valid_params = set(inspect.signature(tool_fn).parameters.keys())
        filtered_args = {k: v for k, v in args.items() if k in valid_params}
        if len(filtered_args) != len(args):
            rejected = set(args.keys()) - valid_params
            logger.warning(f"Dispatcher: rejected unexpected args for '{name}': {rejected}")

        with AuditTimer() as timer:
            result = await tool_fn(**filtered_args)

        result_str = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
        logger.info(f"Dispatcher: '{name}' completed in {timer.elapsed_ms:.1f}ms")

        # Log to audit trail (non-blocking, errors swallowed)
        await log_tool_execution(
            tool_name=name,
            args=filtered_args,
            result=result_str,
            execution_time_ms=timer.elapsed_ms,
        )

        return result_str
    except Exception as e:
        logger.error(f"Dispatcher: tool '{name}' failed: {e}", exc_info=True)
        return f"Error: tool '{name}' failed. Check server logs for details."
