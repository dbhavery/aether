"""Health check endpoint — reports status of all registered modules."""

from __future__ import annotations

import shutil
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from src.core.auth import get_token_for_client
from src.shared.config import get_config, is_onboarding_complete
from src.shared.paths import get_data_dir

_registered_modules: dict[str, dict] = {}
_start_time = time.time()

# --- /auth/token rate limit: 10 requests / minute / client IP, in-memory. ---
_TOKEN_RATE_LIMIT_WINDOW_SECONDS = 60.0
_TOKEN_RATE_LIMIT_MAX_REQUESTS = 10
_token_request_history: dict[str, deque[float]] = defaultdict(deque)


def register_module(name: str, status: str = "starting") -> None:
    _registered_modules[name] = {"status": status, "registered_at": time.time()}
    logger.info(f"Health: module '{name}' registered with status '{status}'")


def update_module_status(name: str, status: str) -> None:
    if name in _registered_modules:
        _registered_modules[name]["status"] = status
        logger.debug(f"Health: module '{name}' status → '{status}'")


def get_module_statuses() -> dict:
    """Return a copy of all module statuses."""
    return {name: info["status"] for name, info in _registered_modules.items()}


async def _check_dependencies() -> dict:
    """Check external dependencies and return their status."""
    results: dict[str, dict] = {}

    # Ollama
    try:
        import httpx

        from src.shared.config import get_settings

        ollama_url = get_settings().ollama_base_url
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            models = r.json().get("models", [])
            results["ollama"] = {"status": "ok", "models": len(models)}
    except Exception as e:
        results["ollama"] = {"status": "error", "error": str(e)[:100]}

    # GPU / VRAM
    try:
        import torch

        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() // (1024**2)
            total = torch.cuda.get_device_properties(0).total_memory // (1024**2)
            results["gpu"] = {
                "status": "ok",
                "vram_used_mb": allocated,
                "vram_total_mb": total,
            }
        else:
            results["gpu"] = {"status": "unavailable"}
    except Exception:
        results["gpu"] = {"status": "unavailable"}

    # Local storage — user data directory headroom.
    try:
        data_dir = get_data_dir()
        _total, _used, free = shutil.disk_usage(str(data_dir))
        results["storage"] = {
            "status": "ok",
            "data_dir": str(data_dir),
            "free_gb": round(free / (1024**3), 1),
        }
    except Exception as e:
        results["storage"] = {"status": "error", "error": str(e)[:100]}

    return results


def _client_ip(request: Request) -> str:
    """Return the best-effort client IP for rate-limit bucketing."""
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _check_token_rate_limit(ip: str) -> bool:
    """Return True if the caller is within the rate limit, False otherwise.

    Sliding-window counter — O(n) on window size, bounded by 10.
    """
    now = time.monotonic()
    history = _token_request_history[ip]
    cutoff = now - _TOKEN_RATE_LIMIT_WINDOW_SECONDS
    while history and history[0] < cutoff:
        history.popleft()
    if len(history) >= _TOKEN_RATE_LIMIT_MAX_REQUESTS:
        return False
    history.append(now)
    return True


def create_health_app() -> FastAPI:
    app = FastAPI(title="Aether Health", version="1.0.0")

    @app.get("/health")
    async def health() -> dict:
        modules = get_module_statuses()
        all_ready = all(s == "ready" for s in modules.values())
        deps = await _check_dependencies()
        deps_ok = all(v.get("status") in ("ok", "unavailable") for v in deps.values())
        overall = "ok" if (all_ready and deps_ok) else "degraded"
        from src.core.metrics import get_metrics_summary

        try:
            config = get_config()
            persona_active: str | None = config.persona.active or None
        except Exception as exc:
            logger.debug(f"Health: could not read persona from config: {exc!r}")
            persona_active = None

        try:
            onboarding_done = is_onboarding_complete()
        except Exception as exc:
            logger.debug(f"Health: could not read onboarding state: {exc!r}")
            onboarding_done = False

        return {
            "status": overall,
            "uptime_seconds": round(time.time() - _start_time, 1),
            "modules": modules,
            "dependencies": deps,
            "metrics": get_metrics_summary(),
            "onboarding_complete": onboarding_done,
            "persona_active": persona_active,
        }

    @app.get("/ping")
    async def ping() -> dict:
        return {"pong": True}

    @app.get("/auth/token")
    async def auth_token(request: Request) -> JSONResponse:
        ip = _client_ip(request)
        if not _check_token_rate_limit(ip):
            logger.warning(f"Health: /auth/token rate limit exceeded for {ip}")
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded"},
            )
        try:
            token = get_token_for_client()
        except Exception as exc:
            logger.error(f"Health: /auth/token failed to produce a token: {exc!r}")
            return JSONResponse(
                status_code=500,
                content={"error": "token_unavailable"},
            )
        return JSONResponse(status_code=200, content={"token": token})

    return app
