"""
Agent dispatcher — Aether's Brain calls this when a task needs an agent.
Routes based on task type. The user never sees agent names.
"""

from loguru import logger


async def dispatch(intent: str, payload: str, context: str = "") -> str:
    """
    Dispatch to the right agent based on intent.
    Returns result string that Aether presents as her own response.

    Intents: 'research', 'draft_email', 'draft_message', 'draft_document'
    """
    if not payload or not payload.strip():
        return "I need to know what to work on. Could you give me more details?"
    logger.info(f"Dispatcher: intent='{intent}', payload='{payload[:60]}'")

    if intent == "research":
        from src.agents.research_agent import run_research

        return await run_research(payload)

    elif intent in ("draft_email", "draft_message", "draft_document"):
        from src.agents.writing_agent import draft_content

        content_type = intent.replace("draft_", "")
        return await draft_content(content_type, payload, context)

    else:
        logger.warning(f"Dispatcher: unknown intent '{intent}' -- no agent dispatched")
        return f"I don't have an agent for '{intent}' yet."
