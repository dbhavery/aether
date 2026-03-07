"""Tools event handler — registers tools on startup.

NOTE: Tools are dispatched DIRECTLY by brain/handler.py via dispatch_tool(),
not through EventBus events. This is intentional — the brain needs synchronous
tool results within its agentic LLM loop.
"""

from loguru import logger

from src.tools.dispatcher import TOOL_REGISTRY


def register_tools_handlers() -> None:
    """Register tool subsystem. Tools are invoked directly by brain via dispatch_tool()."""
    logger.info(f"Tools: registered {len(TOOL_REGISTRY)} tools, handler active")
