"""Writing agent — drafts emails, messages, documents for the user's approval."""

import uuid

from loguru import logger

from src.agents.base import AgentStatus, AgentTask
from src.agents.task_registry import register_task, update_task
from src.shared.config import get_settings


async def draft_content(
    content_type: str,
    instructions: str,
    context: str = "",
) -> str:
    """
    Draft a piece of writing. Returns draft text.
    content_type: 'email', 'message', 'document', 'reply'
    NOTE: Never sends anything — always returns draft for the user's approval.
    """
    task_id = f"writing_{uuid.uuid4().hex[:8]}"
    task = AgentTask(
        task_id=task_id,
        agent_name="writing_agent",
        instruction=f"Draft {content_type}: {instructions[:60]}",
    )
    await register_task(task)
    await update_task(task_id, AgentStatus.RUNNING)

    system_prompt = (
        f"You are Aether's writing agent. Draft a {content_type} for the developer. "
        f"Match his tone: direct, professional but not stuffy, no fluff. "
        f"Return ONLY the draft -- no preamble, no 'here's a draft' intro. "
        f"This will be shown to the user for his approval before sending."
    )
    if context:
        system_prompt += f"\n\nContext: {context}"

    try:
        settings = get_settings()
        if settings.anthropic_api_key:
            from src.brain.clients import _get_anthropic_client
            from src.shared.config import get_yaml_config

            client = _get_anthropic_client()
            yaml_config = get_yaml_config()
            agent_model = yaml_config.get("llm", {}).get("writing_agent_model", "claude-sonnet-4-6")
            response = await client.messages.create(
                model=agent_model,
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": instructions}],
            )
            if response.content and hasattr(response.content[0], "text"):
                result = response.content[0].text.strip()
            else:
                logger.warning("WritingAgent: LLM returned empty content, using placeholder")
                result = f"[Draft incomplete — LLM did not return content]\n\nInstructions: {instructions}"
        else:
            result = f"[Draft unavailable -- ANTHROPIC_API_KEY not set]\n\nInstructions: {instructions}"

        await update_task(task_id, AgentStatus.COMPLETE, result)
        logger.info(f"WritingAgent: completed task {task_id}")
        return result
    except Exception as e:
        error_msg = f"Writing failed: {e}"
        await update_task(task_id, AgentStatus.FAILED, error=error_msg)
        return "I had trouble drafting that. Please try again."
