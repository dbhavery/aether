"""Windows toast notifications via winotify. No sound by default."""

import asyncio
from pathlib import Path

from loguru import logger

AETHER_ICON = str(Path(__file__).resolve().parent.parent.parent / "assets" / "aether_icon.ico")


async def show_notification(title: str, message: str, duration: str = "short") -> None:
    """Show a Windows toast notification. Fire-and-forget."""
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="Aether",
            title=title,
            msg=message[:250],
            duration=duration,
            icon=AETHER_ICON if Path(AETHER_ICON).exists() else "",
        )
        # No sound — the user's preference (no backchannels, no surprise audio)
        toast.set_audio(audio.Silent, loop=False)
        await asyncio.to_thread(toast.show)
        logger.debug(f"Notify (Windows): '{title}' -- '{message[:60]}'")
    except Exception as e:
        logger.error(f"Notify: Windows notification failed: {e}")
