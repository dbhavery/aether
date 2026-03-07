"""Research agent — web search + synthesis. Returns results to Aether."""

import asyncio
import uuid

from loguru import logger

from src.agents.base import AgentStatus, AgentTask
from src.agents.task_registry import register_task, update_task
from src.shared.config import get_settings


async def run_research(query: str) -> str:
    """
    Research a query using DuckDuckGo + synthesis.
    Returns a summary string Aether can present as her own.
    """
    task_id = f"research_{uuid.uuid4().hex[:8]}"
    task = AgentTask(
        task_id=task_id,
        agent_name="research_agent",
        instruction=query,
    )
    await register_task(task)
    await update_task(task_id, AgentStatus.RUNNING)

    try:
        from duckduckgo_search import DDGS

        results = await asyncio.wait_for(
            asyncio.to_thread(lambda: list(DDGS().text(query, max_results=5))),
            timeout=30.0,
        )
        if not results:
            result = f"I couldn't find current results for: {query}"
            await update_task(task_id, AgentStatus.COMPLETE, result)
            return result

        # Synthesize results using Brain's LLM
        snippets = "\n\n".join(f"[{r.get('title', '')}]\n{r.get('body', '')}" for r in results[:5])
        synthesis_prompt = (
            f"You are Aether's research agent. Synthesize these search results "
            f"into a clear, direct answer for the user. Be concise. No fluff.\n\n"
            f"Query: {query}\n\nResults:\n{snippets}"
        )

        # Try Claude first, fall back to Ollama
        settings = get_settings()
        if settings.anthropic_api_key:
            from src.brain.clients import _get_anthropic_client
            from src.shared.config import get_yaml_config

            client = _get_anthropic_client()
            yaml_config = get_yaml_config()
            agent_model = yaml_config.get("llm", {}).get("research_agent_model", "claude-sonnet-4-6")
            response = await client.messages.create(
                model=agent_model,
                max_tokens=800,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            if response.content and hasattr(response.content[0], "text"):
                result = response.content[0].text.strip()
            else:
                logger.warning("ResearchAgent: LLM returned empty content, using raw snippets")
                result = f"Here's what I found:\n\n{snippets}"
        else:
            # Fallback: return raw snippets if no API key
            result = f"Here's what I found:\n\n{snippets}"

        await update_task(task_id, AgentStatus.COMPLETE, result)
        logger.info(f"ResearchAgent: completed task {task_id}")
        return result

    except Exception as e:
        error_msg = f"Research failed: {e}"
        await update_task(task_id, AgentStatus.FAILED, error=error_msg)
        logger.error(f"ResearchAgent: {error_msg}")
        return "I ran into an issue researching that. Please try again."
