"""Single entry point for all LLM calls, backed by litellm.

``complete()`` is an async generator that yields :class:`Chunk` objects. It is
the only function in the brain package that actually hits a provider. Everything
above it (complexity routing, fallback cascade, cost tracking) goes through
this function so that provider choice stays centralised and observable.

Design points:

* **Streaming by default.** Non-streaming is supported but implemented as a
  single yielded chunk so callers don't need two code paths.
* **Provider keys fetched from the OS keyring at call time.** No plaintext on
  disk (see docs/LLM-PROVIDERS.md §6). Ollama needs no key.
* **Errors are typed.** litellm raises a variety of provider-flavoured
  exceptions; we normalise them to :class:`AuthError` / :class:`RateLimitError`
  / :class:`ProviderError` / :class:`TimeoutError` so the fallback cascade and
  the UI can act on them consistently.
* **Usage metrics are emitted on the final chunk.** The ``usage`` dict matches
  the shape litellm gives us (``prompt_tokens``, ``completion_tokens``,
  ``total_tokens``) and is consumed by ``src.brain.cost.track_usage``.

See:
    docs/LLM-PROVIDERS.md §5 (fallback), §9 (streaming contract)
"""

from __future__ import annotations

import builtins
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from loguru import logger

from src.brain.llm_router import Tier, resolve_model, resolve_provider

# ---------------------------------------------------------------------------
# Chunk type
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Chunk:
    """One streaming delta from the LLM.

    Attributes:
        content: Text delta for this chunk. May be an empty string on the
            terminal chunk that carries only ``finish_reason`` + ``usage``.
        finish_reason: ``None`` while streaming; one of ``"stop"``, ``"length"``,
            ``"content_filter"``, ``"tool_calls"``, ``"error"`` on the final chunk.
        usage: Populated only on the final chunk, ``None`` otherwise. Shape:
            ``{"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}``.
    """

    content: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Error hierarchy
#
# These wrap litellm's provider-specific exceptions so downstream code (the
# fallback cascade, the UI layer in Sandbox -> Status) can make decisions
# without caring which provider is underneath.
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base class for all LLM call failures. Carries the provider name for UX."""

    def __init__(self, message: str, *, provider: str, model: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model


class AuthError(LLMError):
    """401/403 — API key missing, invalid, or lacking required scopes.

    Auth errors are USER-FIXABLE (rotate the key, check quota). The fallback
    cascade must NOT retry on this class; that would waste calls and hide the
    real problem.
    """


class RateLimitError(LLMError):
    """429 — too many requests. Retryable with backoff, then fall through."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider, model=model)
        self.retry_after = retry_after


class ProviderError(LLMError):
    """5xx or other transient provider issue. Fall through to the next tier."""


class TimeoutError(LLMError):
    """Network or server timeout. Fall through to the next tier."""


# ---------------------------------------------------------------------------
# Config / key retrieval
# ---------------------------------------------------------------------------

# Environment variable names litellm reads per provider. We set these in-process
# for the duration of the call so the user's keyring stays the canonical source.
_PROVIDER_ENV_KEY: Final[dict[str, str]] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Tier-appropriate request timeouts (seconds). Overridable via llm.timeout_<tier>_seconds.
_DEFAULT_TIMEOUT: Final[dict[Tier, float]] = {
    Tier.FAST: 15.0,
    Tier.MAIN: 45.0,
    Tier.HEAVY: 120.0,
}


def _get_timeout(tier: Tier) -> float:
    """Per-tier timeout in seconds. Reads ``llm.timeout_<tier>_seconds`` if set."""
    try:
        from src.brain.llm_router import _read_llm_config

        llm_cfg = _read_llm_config()
        override = llm_cfg.get(f"timeout_{tier.value}_seconds")
        if isinstance(override, (int, float)) and override > 0:
            return float(override)
    except Exception as exc:
        logger.debug(f"LLMClient: timeout override lookup failed ({exc!r}), using default")
    return _DEFAULT_TIMEOUT[tier]


def _fetch_key(provider: str) -> str | None:
    """Load the API key for ``provider`` from the OS keyring.

    Returns ``None`` for providers that do not need a key (Ollama, Aether Guest
    proxied locally) or when the user has not set one yet — the caller decides
    whether that should raise :class:`AuthError`.
    """
    if provider in ("ollama", "guest", "aether_guest"):
        return None

    try:
        from src.shared.secrets import get_key  # type: ignore[attr-defined]
    except ImportError:
        logger.debug("LLMClient: src.shared.secrets not yet available; falling back to env/config")
        return _fetch_key_legacy(provider)

    try:
        key = get_key(provider)
        if key:
            return key
    except Exception as exc:
        logger.warning(f"LLMClient: keyring lookup failed for '{provider}' ({exc!r})")

    return _fetch_key_legacy(provider)


def _fetch_key_legacy(provider: str) -> str | None:
    """Legacy fallback: read from the existing Settings / .env — used only while
    ``src.shared.secrets`` is still being built.
    """
    try:
        from src.shared.config import get_settings

        settings = get_settings()
        mapping = {
            "anthropic": "anthropic_api_key",
            "openai": "openai_api_key",
            "gemini": "google_api_key",
            "google": "google_api_key",
            "groq": "groq_api_key",
            "openrouter": "openrouter_api_key",
        }
        attr = mapping.get(provider)
        if attr is None:
            return None
        return getattr(settings, attr, None) or None
    except Exception as exc:
        logger.debug(f"LLMClient: legacy key lookup failed for '{provider}' ({exc!r})")
        return None


# ---------------------------------------------------------------------------
# Error mapping from litellm
# ---------------------------------------------------------------------------


def _map_litellm_error(exc: BaseException, *, provider: str, model: str) -> LLMError:
    """Translate any litellm / HTTP exception into our typed hierarchy.

    We check by class name rather than importing every litellm exception class,
    because litellm's exception surface changes across versions and we don't want
    to couple to a specific one. We also fall back on status codes and message
    text heuristics.
    """
    name = exc.__class__.__name__
    message = str(exc) or name
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)

    # Retry-After, if present
    retry_after: float | None = None
    ra = getattr(exc, "retry_after", None)
    if isinstance(ra, (int, float)):
        retry_after = float(ra)

    # Match both the builtin (asyncio.TimeoutError is TimeoutError in 3.11+) and
    # any litellm/HTTP library class whose name contains "Timeout".
    if isinstance(exc, builtins.TimeoutError) or "Timeout" in name:
        return TimeoutError(message, provider=provider, model=model)
    if "AuthenticationError" in name or "PermissionDeniedError" in name or status in (401, 403):
        return AuthError(message, provider=provider, model=model)
    if "RateLimitError" in name or status == 429:
        return RateLimitError(message, provider=provider, model=model, retry_after=retry_after)
    if "ServiceUnavailableError" in name or "APIConnectionError" in name or "InternalServerError" in name:
        return ProviderError(message, provider=provider, model=model)
    if isinstance(status, int) and 500 <= status < 600:
        return ProviderError(message, provider=provider, model=model)

    # Default: ProviderError is the safest bucket for "the provider failed somehow".
    return ProviderError(message, provider=provider, model=model)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def complete(
    messages: list[dict[str, Any]],
    tier: Tier,
    stream: bool = True,
    **kwargs: Any,
) -> AsyncIterator[Chunk]:
    """Stream a completion for ``messages`` on the given ``tier``.

    Args:
        messages: OpenAI-style chat messages: ``[{"role": str, "content": str | list}]``.
        tier: Abstract tier (FAST / MAIN / HEAVY). Resolved to a concrete model
            via :func:`llm_router.resolve_model` at call time.
        stream: If True (default), yield one Chunk per streamed delta. If False,
            make a single non-streamed call and yield exactly one Chunk.
        **kwargs: Passed through to ``litellm.acompletion`` — e.g. ``temperature``,
            ``max_tokens``, ``top_p``, ``stop``, ``response_format``.

    Yields:
        :class:`Chunk` objects. The last chunk carries ``finish_reason`` and
        ``usage`` when the provider reports them.

    Raises:
        AuthError: 401/403 from the provider — user must fix their API key.
        RateLimitError: 429 — back off and retry, or fall through.
        ProviderError: 5xx or other transient failure — fall through.
        TimeoutError: network or server timeout — fall through.
    """
    model = resolve_model(tier)
    provider = resolve_provider(tier)
    timeout = _get_timeout(tier)

    # Late import so the module loads even if litellm is missing during early P2 work.
    try:
        import litellm
    except ImportError as exc:
        raise ProviderError(
            "litellm is not installed — add it to pyproject.toml",
            provider=provider,
            model=model,
        ) from exc

    # Put the key into the env slot litellm expects for this provider. We set it
    # unconditionally per call so that a provider change in config is picked up
    # on the next call with zero cache-invalidation logic.
    key = _fetch_key(provider)
    env_var = _PROVIDER_ENV_KEY.get(provider)
    if env_var and key:
        os.environ[env_var] = key
    elif env_var and not key and provider not in ("ollama", "guest", "aether_guest"):
        # No key and the provider needs one. Fail fast with AuthError so the
        # fallback cascade can skip retrying this tier.
        raise AuthError(
            f"No API key configured for '{provider}' — add one in Sandbox -> LLM settings.",
            provider=provider,
            model=model,
        )

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "timeout": timeout,
        **kwargs,
    }
    # Ollama needs an explicit base_url; litellm respects OLLAMA_API_BASE but
    # being explicit keeps us independent of env state.
    if provider == "ollama":
        call_kwargs.setdefault("api_base", os.environ.get("OLLAMA_API_BASE", "http://localhost:11434"))

    logger.debug(f"LLMClient: calling {model} (tier={tier}, stream={stream}, timeout={timeout}s)")

    try:
        if stream:
            async for chunk in _iter_stream(litellm, call_kwargs, provider=provider, model=model):
                yield chunk
        else:
            async for chunk in _iter_single(litellm, call_kwargs, provider=provider, model=model):
                yield chunk
    except LLMError:
        raise
    except BaseException as exc:
        mapped = _map_litellm_error(exc, provider=provider, model=model)
        logger.warning(
            f"LLMClient: {model} failed -> {mapped.__class__.__name__}: {mapped}"
        )
        raise mapped from exc


# ---------------------------------------------------------------------------
# Streaming / non-streaming helpers
# ---------------------------------------------------------------------------


async def _iter_stream(
    litellm_mod: Any,
    call_kwargs: dict[str, Any],
    *,
    provider: str,
    model: str,
) -> AsyncIterator[Chunk]:
    """Stream deltas from ``litellm.acompletion``, yielding one Chunk per event.

    On the last event we also yield usage if the provider reports it. Some
    providers only attach usage on ``stream=True`` when ``stream_options=
    {"include_usage": True}`` is set — we request that opt-in whenever the
    caller didn't override it.
    """
    call_kwargs.setdefault("stream_options", {"include_usage": True})

    try:
        response = await litellm_mod.acompletion(**call_kwargs)
    except BaseException as exc:
        raise _map_litellm_error(exc, provider=provider, model=model) from exc

    last_finish: str | None = None
    last_usage: dict[str, int] | None = None

    async for event in response:
        try:
            # Usage on the terminal event (stream_options.include_usage).
            usage_obj = getattr(event, "usage", None)
            if usage_obj is not None:
                last_usage = _normalise_usage(usage_obj)

            choices = getattr(event, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            finish = getattr(choice, "finish_reason", None)

            if finish:
                last_finish = finish

            if content:
                yield Chunk(content=content, finish_reason=None, usage=None)
        except BaseException as exc:
            raise _map_litellm_error(exc, provider=provider, model=model) from exc

    # Terminal chunk — carries only metadata.
    yield Chunk(content="", finish_reason=last_finish or "stop", usage=last_usage)


async def _iter_single(
    litellm_mod: Any,
    call_kwargs: dict[str, Any],
    *,
    provider: str,
    model: str,
) -> AsyncIterator[Chunk]:
    """Non-streaming path — one litellm call, one yielded Chunk with full text + usage."""
    try:
        response = await litellm_mod.acompletion(**call_kwargs)
    except BaseException as exc:
        raise _map_litellm_error(exc, provider=provider, model=model) from exc

    try:
        choices = getattr(response, "choices", None) or []
        if not choices:
            yield Chunk(content="", finish_reason="error", usage=None)
            return
        choice = choices[0]
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        finish = getattr(choice, "finish_reason", None) or "stop"
        usage_obj = getattr(response, "usage", None)
        usage = _normalise_usage(usage_obj) if usage_obj is not None else None
    except BaseException as exc:
        raise _map_litellm_error(exc, provider=provider, model=model) from exc

    yield Chunk(content=content or "", finish_reason=finish, usage=usage)


def _normalise_usage(usage_obj: Any) -> dict[str, int]:
    """Extract ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens`` from
    whatever shape litellm hands us (dict, pydantic model, ModelResponse, etc.)."""
    if isinstance(usage_obj, dict):
        src = usage_obj
    elif hasattr(usage_obj, "model_dump"):
        src = usage_obj.model_dump()
    else:
        src = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0),
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0),
            "total_tokens": getattr(usage_obj, "total_tokens", 0),
        }

    def _as_int(v: Any) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "prompt_tokens": _as_int(src.get("prompt_tokens")),
        "completion_tokens": _as_int(src.get("completion_tokens")),
        "total_tokens": _as_int(src.get("total_tokens")),
    }
