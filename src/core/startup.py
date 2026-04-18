"""Startup orchestration — v1.0 public release.

Launches Aether services in the correct order:
  1. Health server (so a watchdog / installer can see us immediately).
  2. Core handlers: brain, memory, personas, onboarding wizard.
  3. Voice pipeline (if configured).
  4. Avatar subsystem (if configured and hardware available).
  5. WebSocket server (accepts client connections).

Onboarding is NOT blocking at startup: the WebSocket server always boots, and the
frontend detects whether the wizard needs to run by calling GET /health (which
reports `onboarding_complete`) or by reading the config directly.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import uvicorn
from loguru import logger

from src.core.health import create_health_app, register_module, update_module_status
from src.core.server import start_websocket_server
from src.shared.config import get_settings, get_yaml_config, is_onboarding_complete
from src.shared.logging_config import setup_logging


# Keep references to background tasks so they aren't garbage-collected.
_background_tasks: list[asyncio.Task[None]] = []


async def _supervised(coro, name: str) -> None:
    """Run a coroutine with exception logging and module-status reporting."""
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(f"startup: background task '{name}' crashed")
        with contextlib.suppress(Exception):
            update_module_status(name, "error")


def _port_in_use(host: str, port: int) -> bool:
    """Return True if another process already holds (host, port)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False


async def startup() -> None:
    """Boot the Aether backend. Called from src.main."""
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info("=== Aether — Starting Up ===")
    logger.info(f"WebSocket port: {settings.websocket_port}")
    logger.info(f"Health port:    {settings.health_port}")

    for name, port in (("health", settings.health_port), ("websocket", settings.websocket_port)):
        if _port_in_use("127.0.0.1", port):
            logger.error(f"startup: port {port} ({name}) already in use — another instance running?")
            raise SystemExit(2)

    register_module("core", "ready")

    # 1. Health server comes up first so external supervisors can observe us.
    health_config = uvicorn.Config(
        create_health_app(),
        host=settings.server_host,
        port=settings.health_port,
        log_level="warning",
    )
    health_server = uvicorn.Server(health_config)
    _background_tasks.append(asyncio.create_task(_supervised(health_server.serve(), "health_server")))
    await asyncio.sleep(0.3)
    logger.info(f"startup: health server listening on port {settings.health_port}")

    # 2. Core feature handlers — always registered regardless of onboarding state.
    from src.brain.handler import register_brain_handlers
    from src.memory.handler import register_memory_handlers
    from src.onboarding.handler import register_wizard_handlers
    from src.onboarding.probe_handler import register_probe_handlers

    register_memory_handlers()
    register_brain_handlers()
    register_wizard_handlers()
    register_probe_handlers()
    logger.info("startup: core handlers registered (memory, brain, onboarding, probes)")

    # Personas loader — scans bundled and user persona packs.
    try:
        from src.personas import get_persona_manager

        persona_manager = get_persona_manager()
        persona_count = len(persona_manager.list_all())
        logger.info(f"startup: persona manager ready ({persona_count} packs loaded)")
        register_module("personas", "ready")
    except Exception:
        logger.exception("startup: persona manager failed to load")
        register_module("personas", "error")

    # 3. Memory embeddings check — non-blocking warning if unavailable.
    try:
        from src.memory.embeddings import ensure_embedding_model

        if not await ensure_embedding_model():
            logger.warning("startup: embedding model unavailable — memory search disabled")
    except Exception as e:
        logger.debug(f"startup: embedding check skipped ({e})")

    # 4. Voice + avatar only if onboarding is done. Before that, user can still
    #    reach the WebSocket from the frontend to complete the wizard.
    if is_onboarding_complete():
        await _start_voice_and_avatar()
    else:
        logger.info("startup: onboarding incomplete — skipping voice + avatar startup until wizard finishes")
        register_module("voice", "pending_onboarding")
        register_module("avatar", "pending_onboarding")

    logger.info("startup: handlers registered; launching WebSocket server")
    await start_websocket_server()


async def _start_voice_and_avatar() -> None:
    """Boot voice pipeline and avatar subsystem (called after onboarding)."""
    config = get_yaml_config()

    voice_mode = config.get("voice", {}).get("mode", "off")
    if voice_mode != "off":
        try:
            from src.voice.pipeline import start_voice_pipeline
            from src.voice.tts_handler import register_tts_handlers

            register_module("voice", "starting")
            _background_tasks.append(asyncio.create_task(_supervised(start_voice_pipeline(), "voice")))
            register_tts_handlers()
            logger.info(f"startup: voice pipeline scheduled (mode={voice_mode})")
        except Exception:
            logger.exception("startup: voice subsystem failed to schedule")
            update_module_status("voice", "error")
    else:
        logger.info("startup: voice disabled in config — skipping")
        register_module("voice", "disabled")

    avatar_enabled = config.get("avatar", {}).get("enabled", False)
    if avatar_enabled:
        try:
            from src.avatar.handler import initialize_avatar, register_avatar_handlers
            from src.avatar.server import start_avatar_server

            register_avatar_handlers()

            async def _boot_avatar() -> None:
                try:
                    engine = await start_avatar_server()
                    if engine == "none":
                        logger.warning("startup: avatar enabled but no backend available")
                    else:
                        logger.info(f"startup: avatar server ready (engine={engine})")
                except Exception as e:
                    logger.error(f"startup: avatar server crashed: {e}")
                await initialize_avatar()

            _background_tasks.append(asyncio.create_task(_supervised(_boot_avatar(), "avatar")))
        except Exception:
            logger.exception("startup: avatar subsystem failed to schedule")
            update_module_status("avatar", "error")
    else:
        logger.info("startup: avatar disabled in config — skipping")
        register_module("avatar", "disabled")
