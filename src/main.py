"""Aether — main entry point.

Usage:
    python -m src.main          # Run the server directly
    python -m src.core.watchdog # Run via watchdog (auto-restart on crash)
"""

import asyncio
import multiprocessing
import os
import sys

# On Windows, torch.multiprocessing uses 'spawn' which re-imports __main__.
# Without freeze_support(), the spawned child runs run() again as a full server.
multiprocessing.freeze_support()

# Ensure valid stdout/stderr BEFORE any imports that might write to them.
# Under pythonw.exe (especially as a subprocess), these can be None or broken.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")  # noqa: SIM115
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115

from loguru import logger  # noqa: E402  # must be after stdout/stderr guard

from src.shared.logging_config import setup_logging  # noqa: E402


async def main() -> None:
    """Start all Aether services."""
    from src.core.shutdown import register_shutdown_handlers
    from src.core.startup import startup

    loop = asyncio.get_running_loop()
    register_shutdown_handlers(loop)
    await startup()


def run() -> None:
    """Synchronous entry point for CLI and launchers."""
    # Set up logging EARLY so any crash is captured in the log file,
    # especially important when running under pythonw.exe (no console).
    setup_logging("DEBUG")

    # NOTE: winloop disabled — it was causing duplicate process spawning on Windows.
    # The child process re-ran src.main, creating two servers fighting over audio.
    # TODO: investigate winloop 0.5.0 + torch multiprocessing interaction.
    # try:
    #     import winloop
    #     winloop.install()
    #     logger.info("winloop installed — async performance boost active")
    # except ImportError:
    #     logger.debug("winloop not available — using default event loop")

    # Acquire single-instance lock before starting
    from src.core.instance_lock import acquire_instance_lock

    if not acquire_instance_lock():
        logger.error("Another Aether instance is already running. Exiting.")
        sys.exit(2)

    logger.info("Aether main entry point starting")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception:
        logger.exception("Fatal error in main")
        sys.exit(1)


if __name__ == "__main__":
    run()
