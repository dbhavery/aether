"""Startup orchestration — launches all services in correct order."""

import asyncio
import contextlib
import socket

import uvicorn
from loguru import logger

from src.core.health import create_health_app, register_module
from src.core.server import start_websocket_server
from src.shared.config import get_settings, get_yaml_config
from src.shared.logging_config import setup_logging

# Keep references to background tasks to prevent garbage collection
_background_tasks: list = []


async def _supervised(coro, name: str) -> None:
    """Wrapper that logs exceptions from background tasks instead of losing them."""
    try:
        await coro
    except Exception:
        logger.exception(f"Startup: background task '{name}' crashed")
        with contextlib.suppress(Exception):
            from src.core.health import update_module_status

            update_module_status(name, "error")


def _port_in_use(host: str, port: int) -> bool:
    """Check if a port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


async def startup() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("=== Aether — Starting Up ===")
    logger.info(f"WebSocket port: {settings.websocket_port}")
    logger.info(f"Health port: {settings.health_port}")
    logger.info(f"Data path: {settings.aether_data_path}")

    # Bail early if another instance is already running on our ports
    for port_name, port_num in [
        ("health", settings.health_port),
        ("websocket", settings.websocket_port),
        ("data_server", settings.data_server_port),
    ]:
        if _port_in_use("127.0.0.1", port_num):
            logger.error(f"Startup: port {port_num} ({port_name}) already in use — another instance running?")
            raise SystemExit(2)

    # Register core module
    register_module("core", "ready")

    # Start health server IMMEDIATELY so the VBS launcher / watchdog can see us
    health_app = create_health_app()
    health_config = uvicorn.Config(
        health_app,
        host=settings.server_host,
        port=settings.health_port,
        log_level="warning",
    )
    health_server = uvicorn.Server(health_config)
    _background_tasks.append(asyncio.create_task(_supervised(health_server.serve(), "health_server")))
    # Give uvicorn a moment to bind the port
    await asyncio.sleep(0.5)
    logger.info(f"Health server listening on port {settings.health_port}")

    # Mark stale agent tasks from previous run as FAILED
    from src.agents.task_registry import mark_stale_running_as_failed

    await mark_stale_running_as_failed()

    # Register module handlers
    from src.brain.handler import register_brain_handlers
    from src.memory.handler import register_memory_handlers
    from src.tools.handler import register_tools_handlers

    register_memory_handlers()
    register_brain_handlers()
    register_tools_handlers()

    # Verify embedding model is available for memory operations
    from src.memory.embeddings import ensure_embedding_model

    if not await ensure_embedding_model():
        logger.warning("Startup: nomic-embed-text not found — memory search may fail")

    # Voice pipeline (Module 02)
    from src.voice.pipeline import start_voice_pipeline

    register_module("voice_in", "starting")
    _background_tasks.append(asyncio.create_task(_supervised(start_voice_pipeline(), "voice_in")))

    # TTS handler (Module 03)
    from src.voice.tts_handler import register_tts_handlers

    register_module("voice_out", "ready")
    register_tts_handlers()

    # Avatar (Module 06)
    from src.avatar.handler import initialize_avatar, register_avatar_handlers

    register_avatar_handlers()

    # Start avatar server in background so it doesn't block WS startup (~50s)
    # initialize_avatar() runs AFTER server start to avoid race condition
    config = get_yaml_config()
    if config.get("avatar", {}).get("enabled", False):
        from src.avatar.server import start_avatar_server

        async def _start_avatar_then_init() -> None:
            try:
                engine = await start_avatar_server()
                if engine == "none":
                    logger.warning("Startup: avatar enabled but no backend available — continuing without avatar")
                else:
                    logger.info(f"Startup: avatar server started (engine={engine})")
            except Exception as e:
                logger.error(f"Startup: avatar server failed to start: {e}")
            # Now that server is (possibly) ready, check availability and broadcast
            await initialize_avatar()

        _background_tasks.append(asyncio.create_task(_supervised(_start_avatar_then_init(), "avatar")))
    else:
        # Avatar disabled — still register module status
        _background_tasks.append(asyncio.create_task(_supervised(initialize_avatar(), "avatar")))

    # Notifications & Cron (Module 12)
    from src.notifications.handler import register_notification_handlers
    from src.notifications.scheduler import start_scheduler

    register_module("notifications", "starting")
    register_notification_handlers()
    start_scheduler()
    from src.core.health import update_module_status

    update_module_status("notifications", "ready")

    # Persona: Memory Corrections (Module C)
    from src.persona.memory_corrections import register_memory_correction_handler

    register_memory_correction_handler()

    # Persona: Busy Detector subscribes to USER_MESSAGE
    from src.persona.busy_detector import register_busy_detector_events

    register_busy_detector_events()

    # Persona: Proactive Scheduler (morning/evening notifications)
    from src.persona.proactive import get_proactive_scheduler

    get_proactive_scheduler().start()

    # Data Storage Server (Module B — port 8766)
    from src.data_server.app import create_data_server_app

    register_module("data_server", "starting")
    data_app = create_data_server_app()
    update_module_status("data_server", "ready")

    # Start metrics logger (hourly)
    from src.core.metrics import log_metrics_periodically

    _background_tasks.append(asyncio.create_task(_supervised(log_metrics_periodically(), "metrics")))

    logger.info("All module handlers registered. Starting servers.")

    # Data Storage Server
    data_config = uvicorn.Config(
        data_app,
        host=settings.server_host,
        port=settings.data_server_port,
        log_level="warning",
    )
    data_server = uvicorn.Server(data_config)

    # Run remaining servers concurrently (health already running)
    # NOT wrapped in _supervised() — FIRST_EXCEPTION must see raw exceptions
    ws_task = asyncio.create_task(start_websocket_server())
    data_task = asyncio.create_task(data_server.serve())
    done, pending = await asyncio.wait(
        [ws_task, data_task],
        return_when=asyncio.FIRST_EXCEPTION,
    )
    for task in done:
        if task.cancelled():
            logger.warning("Startup: server task cancelled")
            continue
        exc = task.exception()
        if exc:
            logger.error(f"Startup: server crashed: {exc}")
            from src.core.health import update_module_status

            update_module_status("websocket_server" if task is ws_task else "data_server", "error")
    for task in pending:
        task.cancel()
