"""Structured logging for Aether using loguru."""

import sys
from pathlib import Path

from loguru import logger


def _get_log_path() -> Path:
    """Resolve log directory from config. Lazy to avoid import-time issues."""
    try:
        from src.shared.config import get_settings

        return Path(get_settings().aether_data_path) / "logs"
    except Exception:
        # Fallback if config isn't available yet — log next to the project root
        return Path(__file__).resolve().parent.parent.parent / "logs"


def setup_logging(log_level: str = "DEBUG") -> None:
    logger.remove()
    # Only add stderr sink if it's a real stream (not under pythonw.exe subprocess)
    if sys.stderr is not None and hasattr(sys.stderr, "write"):
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
            colorize=True,
        )

    # Write logs to persistent data drive (path from config)
    log_path = _get_log_path()
    log_path.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path / "aether_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
    )
    logger.info("Logging initialized")
