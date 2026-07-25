"""LLM clients — one per provider. All async. All handle their own errors and fallbacks.

Each client accepts either:
- messages: list[dict] — multi-turn conversation [{role, content}, ...]
- prompt: str — single user message (convenience, auto-wrapped)

Singletons:
- Ollama: uses the shared aiohttp session from src.shared.http_client
- Claude: module-level AsyncAnthropic, lazily created
- Gemini: module-level genai.Client, lazily created
"""

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from src.shared.config import get_settings, get_yaml_config
from src.shared.http_client import get_shared_session

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic as _AsyncAnthropicType
    from google.genai import Client as _GenaiClientType

# ---------------------------------------------------------------------------
# Provider singletons — one client per process, lazily initialised
# ---------------------------------------------------------------------------

_anthropic_client: "_AsyncAnthropicType | None" = None
_genai_client: "_GenaiClientType | None" = None


def _get_anthropic_client() -> "_AsyncAnthropicType":
    """Return the module-level AsyncAnthropic singleton."""
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        logger.debug("Brain/Clients: AsyncAnthropic singleton created")
    return _anthropic_client


def _get_genai_client() -> "_GenaiClientType":
    """Return the module-level google-genai Client singleton."""
    global _genai_client
    if _genai_client is None:
        from google import genai

        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        _genai_client = genai.Client(api_key=settings.google_api_key)
        logger.debug("Brain/Clients: genai.Client singleton created")
    return _genai_client


# Tier-appropriate timeouts (seconds) — configurable via aether_config.yaml
FAST_TIMEOUT = 15.0
PRIMARY_TIMEOUT = 45.0
HEAVY_TIMEOUT = 120.0
GEMINI_TIMEOUT = 30.0


def _get_timeout(tier: str) -> float:
    """Get timeout for a given tier, falling back to module defaults."""
    yaml_config = get_yaml_config()
    llm_config = yaml_config.get("llm", {})
    defaults = {
        "fast": FAST_TIMEOUT,
        "primary": PRIMARY_TIMEOUT,
        "heavy": HEAVY_TIMEOUT,
        "gemini": GEMINI_TIMEOUT,
    }
    return float(llm_config.get(f"timeout_{tier}_seconds", defaults.get(tier, PRIMARY_TIMEOUT)))


def _ensure_messages(prompt: str | None, messages: list[dict] | None) -> list[dict]:
    """Normalize to a messages list. If prompt is given, wrap it."""
    if messages:
        return messages
    if prompt:
        return [{"role": "user", "content": prompt}]
    raise ValueError("Either prompt or messages must be provided")


async def call_ollama(
    prompt: str | None = None,
    system: str = "",
    model: str | None = None,
    messages: list[dict] | None = None,
) -> str:
    """Call local Ollama. Always available. Never requires internet."""
    import aiohttp

    settings = get_settings()
    yaml_config = get_yaml_config()
    model_name = model or yaml_config["llm"]["fast_model"]
    url = f"{settings.ollama_base_url}/api/chat"
    chat_messages = [{"role": "system", "content": system}, *_ensure_messages(prompt, messages)]
    timeout = _get_timeout("fast")
    payload = {
        "model": model_name,
        "messages": chat_messages,
        "stream": False,
        "options": {"num_predict": yaml_config["llm"]["fast_max_tokens"]},
    }
    try:
        session = await get_shared_session()
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Ollama returned {resp.status}")
            data = await resp.json()
            text = data.get("message", {}).get("content", "")
            if not text and data.get("message", {}).get("thinking"):
                logger.warning(f"Ollama ({model_name}): thinking consumed all tokens, no content returned")
            logger.debug(f"Ollama ({model_name}): {len(text)} chars")
            return text
    except Exception as e:
        logger.error(f"Ollama client error: {e}")
        raise


async def call_claude(
    prompt: str | None = None,
    system: str = "",
    heavy: bool = False,
    messages: list[dict] | None = None,
) -> str:
    """Call Anthropic Claude."""
    yaml_config = get_yaml_config()
    model = yaml_config["llm"]["claude_heavy_model"] if heavy else yaml_config["llm"]["claude_model"]
    client = _get_anthropic_client()
    chat_messages = _ensure_messages(prompt, messages)
    timeout = _get_timeout("heavy" if heavy else "primary")
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=yaml_config["llm"]["max_tokens"],
                system=system,
                messages=chat_messages,
            ),
            timeout=timeout,
        )
        # Extract text from first text block (skip ThinkingBlock etc.)
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = block.text
                break
        logger.debug(f"Claude ({model}): {len(text)} chars")
        return text
    except TimeoutError as exc:
        logger.error(f"Claude ({model}): call timed out after {timeout}s")
        raise RuntimeError(f"Claude timed out ({timeout}s) — try again or use a faster model") from exc
    except Exception as e:
        logger.error(f"Claude client error ({model}): {e}")
        raise


async def call_claude_with_tools(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    heavy: bool = False,
) -> dict:
    """Call Claude with tool use support. Returns full response dict.

    Returns:
        {"text": str, "tool_calls": list[dict]} where each tool_call has
        {name, arguments, id} or tool_calls is empty for a final text response.
    """
    yaml_config = get_yaml_config()
    model = yaml_config["llm"]["claude_heavy_model"] if heavy else yaml_config["llm"]["claude_model"]
    client = _get_anthropic_client()
    timeout = _get_timeout("heavy" if heavy else "primary")
    try:
        kwargs = {
            "model": model,
            "max_tokens": yaml_config["llm"]["max_tokens"],
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        response = await asyncio.wait_for(
            client.messages.create(**kwargs),
            timeout=timeout,
        )

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        result = {"text": "\n".join(text_parts), "tool_calls": tool_calls}
        logger.debug(f"Claude ({model}): {len(result['text'])} chars, {len(tool_calls)} tool calls")
        return result
    except TimeoutError as exc:
        logger.error(f"Claude tools ({model}): call timed out after {timeout}s")
        raise RuntimeError(f"Claude timed out ({timeout}s)") from exc
    except Exception as e:
        logger.error(f"Claude tool_use error ({model}): {e}")
        raise


async def call_gemini(
    prompt: str | None = None,
    system: str = "",
    model_key: str = "gemini_model",
    messages: list[dict] | None = None,
) -> str:
    """Call Google Gemini via google-genai SDK (async native)."""
    from google.genai import types

    yaml_config = get_yaml_config()
    model_name = yaml_config["llm"][model_key]
    client = _get_genai_client()
    timeout = _get_timeout("gemini")
    try:
        # Convert messages list to google-genai Content format
        chat_msgs = _ensure_messages(prompt, messages)
        contents = []
        for msg in chat_msgs:
            role = "model" if msg["role"] == "assistant" else "user"
            content = msg["content"]
            if isinstance(content, str):
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=content)]))
            elif isinstance(content, list):
                # Handle structured content from tool loops
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(types.Part.from_text(text=block["text"]))
                        elif block.get("type") == "tool_result":
                            parts.append(types.Part.from_text(text=str(block.get("content", ""))))
                        elif block.get("type") == "tool_use":
                            parts.append(types.Part.from_text(text=f"[tool call: {block.get('name', 'unknown')}]"))
                    else:
                        parts.append(types.Part.from_text(text=str(block)))
                if parts:
                    contents.append(types.Content(role=role, parts=parts))

        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=yaml_config["llm"]["max_tokens"],
        )
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            ),
            timeout=timeout,
        )
        try:
            text = response.text or ""
        except ValueError as exc:
            # Safety-blocked responses raise ValueError on .text access
            logger.warning(f"Gemini ({model_name}): response blocked by safety filter")
            raise RuntimeError(f"Gemini ({model_name}): response blocked by safety filter") from exc
        logger.debug(f"Gemini ({model_name}): {len(text)} chars")
        return text
    except TimeoutError as exc:
        logger.error(f"Gemini ({model_name}): call timed out after {timeout}s")
        raise RuntimeError(f"Gemini timed out ({timeout}s)") from exc
    except Exception as e:
        logger.error(f"Gemini client error ({model_name}): {e}")
        raise


async def call_gemini_with_tools(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
    model_key: str = "gemini_model",
) -> dict:
    """Call Gemini with function calling support. Returns full response dict.

    Returns:
        {"text": str, "tool_calls": list[dict]} where each tool_call has
        {name, arguments, id} or tool_calls is empty for a final text response.

    The tools parameter expects Anthropic/Claude-format tool definitions.
    They are converted to Gemini's function declaration format internally.
    """
    from google.genai import types

    yaml_config = get_yaml_config()
    model_name = yaml_config["llm"][model_key]
    client = _get_genai_client()
    timeout = _get_timeout("gemini")

    try:
        # Convert messages to Gemini Content format
        contents = []
        for msg in messages:
            if isinstance(msg.get("content"), str):
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
            elif isinstance(msg.get("content"), list):
                # Handle structured content (tool_use from assistant, tool_result from user)
                parts = []
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        parts.append(
                            types.Part.from_function_response(
                                name=block.get("name", "tool"),
                                response={"result": block.get("content", "")},
                            )
                        )
                    elif block.get("type") == "tool_use":
                        # Convert Claude-style tool_use to Gemini function_call
                        parts.append(
                            types.Part.from_function_call(
                                name=block.get("name", "unknown"),
                                args=block.get("input", {}),
                            )
                        )
                    elif block.get("type") == "text":
                        parts.append(types.Part.from_text(text=block["text"]))
                if parts:
                    role = "model" if msg["role"] == "assistant" else "user"
                    contents.append(types.Content(role=role, parts=parts))

        # Convert Claude-format tools to Gemini function declarations
        gemini_tools = None
        if tools:
            func_declarations = []
            for tool in tools:
                func_declarations.append(
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters=tool.get("input_schema", {}),
                    )
                )
            gemini_tools = [types.Tool(function_declarations=func_declarations)]

        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=yaml_config["llm"]["max_tokens"],
            tools=gemini_tools,
        )

        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            ),
            timeout=timeout,
        )

        # Parse response for text and function calls
        text_parts = []
        tool_calls = []
        candidate = response.candidates[0] if response.candidates else None
        if candidate and getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
            for part in candidate.content.parts:
                if part.text:
                    text_parts.append(part.text)
                elif part.function_call:
                    tool_calls.append(
                        {
                            "id": f"gemini_{part.function_call.name}_{len(tool_calls)}",
                            "name": part.function_call.name,
                            "arguments": dict(part.function_call.args) if part.function_call.args else {},
                        }
                    )

        result = {"text": "\n".join(text_parts), "tool_calls": tool_calls}
        logger.debug(f"Gemini tools ({model_name}): {len(result['text'])} chars, {len(tool_calls)} tool calls")
        return result

    except TimeoutError as exc:
        logger.error(f"Gemini tools ({model_name}): call timed out after {timeout}s")
        raise RuntimeError(f"Gemini timed out ({timeout}s)") from exc
    except Exception as e:
        logger.error(f"Gemini tool_use error ({model_name}): {e}")
        raise
