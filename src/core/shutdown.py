"""Graceful shutdown — ordered cleanup of all services on SIGTERM/SIGINT.

Ensures voice pipeline stops, scheduler flushes, ChromaDB persists,
and HTTP sessions close before the process exits.
"""

import asyncio
import signal

from loguru import logger

_shutdown_event = asyncio.Event()


def register_shutdown_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGTERM + SIGINT handlers for graceful shutdown."""

    def _schedule_shutdown() -> None:
        """Schedule shutdown coroutine on the event loop (thread-safe)."""
        loop.create_task(_shutdown_sequence())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _schedule_shutdown)
        except NotImplementedError:
            # Windows doesn't support loop.add_signal_handler — use signal.signal
            # with call_soon_threadsafe for thread safety (signal handlers run on main thread)
            signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(_schedule_shutdown))
    logger.info("Shutdown: signal handlers registered")


async def _shutdown_sequence() -> None:
    """Ordered shutdown: stop accepting input, flush, close resources."""
    if _shutdown_event.is_set():
        return  # Already shutting down
    _shutdown_event.set()
    logger.info("Shutdown: beginning graceful shutdown...")

    # 1. Stop voice pipeline (sync — runs in thread to avoid blocking event loop)
    try:
        from src.voice.pipeline import stop_voice_pipeline

        await asyncio.to_thread(stop_voice_pipeline)
        logger.info("Shutdown: voice pipeline stopped")
    except Exception as e:
        logger.warning(f"Shutdown: voice pipeline stop failed: {e}")

    # 2. Stop avatar subprocess
    try:
        from src.avatar.server import _cleanup_avatar

        _cleanup_avatar()
        logger.info("Shutdown: avatar subprocess stopped")
    except Exception as e:
        logger.warning(f"Shutdown: avatar cleanup failed: {e}")

    # 3. Close ChromaDB client
    try:
        from src.memory.store import _client as chroma_client

        if chroma_client is not None:
            chroma_client.clear_system_cache()
            logger.info("Shutdown: ChromaDB client cleaned up")
    except Exception as e:
        logger.warning(f"Shutdown: ChromaDB cleanup failed: {e}")

    # 4. Close shared HTTP sessions
    try:
        from src.shared.http_client import close_shared_session

        await close_shared_session()
        logger.info("Shutdown: HTTP sessions closed")
    except Exception as e:
        logger.warning(f"Shutdown: HTTP session close failed: {e}")

    # 5. Free GPU memory
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("Shutdown: GPU cache cleared")
    except Exception as e:
        logger.warning(f"Shutdown: GPU cleanup failed: {e}")

    # Cancel all remaining tasks so asyncio.gather in startup() unblocks
    logger.info("Shutdown: stopping event loop...")
    loop = asyncio.get_running_loop()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Shutdown: complete")


def is_shutting_down() -> bool:
    """Check if a shutdown is in progress."""
    return _shutdown_event.is_set()
