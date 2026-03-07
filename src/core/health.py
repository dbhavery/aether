"""Health check endpoint — reports status of all registered modules."""

import shutil
import time
from pathlib import Path

from fastapi import FastAPI
from loguru import logger

_registered_modules: dict[str, dict] = {}
_start_time = time.time()


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
    results = {}

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

    # I: drive
    try:
        i_drive = Path("./data/")
        if i_drive.exists():
            total, _used, free = shutil.disk_usage(str(i_drive))
            results["storage_i"] = {
                "status": "ok",
                "free_gb": round(free / (1024**3), 1),
            }
        else:
            results["storage_i"] = {"status": "unavailable"}
    except Exception as e:
        results["storage_i"] = {"status": "error", "error": str(e)[:100]}

    return results


def create_health_app() -> FastAPI:
    app = FastAPI(title="Aether Health", version="1.0.0")

    @app.get("/health")
    async def health():
        modules = get_module_statuses()
        all_ready = all(s == "ready" for s in modules.values())
        deps = await _check_dependencies()
        deps_ok = all(v.get("status") in ("ok", "unavailable") for v in deps.values())
        overall = "ok" if (all_ready and deps_ok) else "degraded"
        from src.core.metrics import get_metrics_summary

        return {
            "status": overall,
            "uptime_seconds": round(time.time() - _start_time, 1),
            "modules": modules,
            "dependencies": deps,
            "metrics": get_metrics_summary(),
        }

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    return app
