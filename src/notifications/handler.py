"""Notification handler — bridges EventBus to Windows + FCM delivery."""

from loguru import logger

from src.core.events import event_bus
from src.notifications.fcm_notify import send_push_notification
from src.notifications.windows_notify import show_notification
from src.persona.busy_detector import get_busy_detector
from src.shared.types import EventType, AetherEvent


async def on_agent_task_complete(event: AetherEvent) -> None:
    """Notify the user when an agent task completes."""
    # Respect busy/sleep detection — same as on_notification_request
    try:
        detector = get_busy_detector()
        if not detector.should_notify("normal"):
            availability = detector.get_availability()
            logger.info(f"Notify: agent complete suppressed (The user is {availability})")
            return
    except Exception as e:
        logger.debug(f"Notify: busy detector unavailable ({e}), allowing notification")

    intent = event.data.get("intent", "task")
    await show_notification("Aether", f"Finished: {intent}")
    await send_push_notification("Aether", f"Finished: {intent}")


async def on_notification_request(event: AetherEvent) -> None:
    title = event.data.get("title", "Aether")
    message = event.data.get("message", "")
    if not message:
        return

    # Check if The user is available before sending notification
    priority = event.data.get("priority", "normal")
    try:
        detector = get_busy_detector()
        if not detector.should_notify(priority):
            availability = detector.get_availability()
            logger.info(f"Notify: suppressed (The user is {availability}, priority={priority})")
            return
    except Exception as e:
        logger.debug(f"Notify: busy detector unavailable ({e}), allowing notification")

    # Show Windows notification
    await show_notification(title, message)
    # Also push to Android (non-blocking, best-effort)
    await send_push_notification(title, message)


async def on_proactive_message(event: AetherEvent) -> None:
    """Deliver proactive messages (daily interview, etc.) as notifications too."""
    text = event.data.get("text", "")
    if not text:
        return

    # Respect busy/sleep detection
    try:
        detector = get_busy_detector()
        if not detector.should_notify("normal"):
            availability = detector.get_availability()
            logger.info(f"Notify: proactive message suppressed (The user is {availability})")
            return
    except Exception as e:
        logger.debug(f"Notify: busy detector unavailable ({e}), allowing notification")

    await show_notification("Aether", text)
    await send_push_notification("Aether", text)


def register_notification_handlers() -> None:
    event_bus.subscribe(EventType.NOTIFICATION_REQUEST, on_notification_request)
    event_bus.subscribe(EventType.AGENT_TASK_COMPLETE, on_agent_task_complete)
    event_bus.subscribe(EventType.PROACTIVE_MESSAGE, on_proactive_message)
    logger.info("Notifications: handlers registered")
