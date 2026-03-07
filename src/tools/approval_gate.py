"""Approval gate — high-impact actions require explicit confirmation from the user.

Never executes automatically. Always shows what will happen and waits for approval.
"""

import asyncio
import re
import uuid
from enum import StrEnum

from loguru import logger

from src.core.events import event_bus
from src.shared.types import EventType, AetherEvent


class ActionRisk(StrEnum):
    SAFE = "safe"  # No approval needed
    CONFIRM = "confirm"  # Ask once, proceed
    EXPLICIT = "explicit"  # Require "yes" / "confirm" / "go ahead"


# Actions that always require explicit approval
HIGH_IMPACT_ACTIONS: dict[str, ActionRisk] = {
    "send_email": ActionRisk.EXPLICIT,
    "make_phone_call": ActionRisk.EXPLICIT,
    "edit_system_file": ActionRisk.EXPLICIT,
    "delete_file": ActionRisk.EXPLICIT,
    "run_script": ActionRisk.EXPLICIT,
    "install_software": ActionRisk.EXPLICIT,
    "purchase": ActionRisk.EXPLICIT,
    "post_social_media": ActionRisk.EXPLICIT,
    "send_message": ActionRisk.CONFIRM,
    "create_calendar_event": ActionRisk.CONFIRM,
    "move_file": ActionRisk.CONFIRM,
    # File operations
    "write_to_file": ActionRisk.CONFIRM,
    "create_directory": ActionRisk.CONFIRM,
    # Shell commands
    "run_command": ActionRisk.CONFIRM,
    # PC control
    "type_text": ActionRisk.CONFIRM,
    "open_application": ActionRisk.CONFIRM,
    # Window management
    "minimize_window": ActionRisk.SAFE,
    "maximize_window": ActionRisk.SAFE,
    "close_window": ActionRisk.CONFIRM,
}

_pending_approvals: dict[str, asyncio.Future] = {}

# Words that indicate approval
APPROVAL_WORDS = {
    "yes",
    "yeah",
    "yep",
    "sure",
    "go ahead",
    "do it",
    "confirm",
    "approved",
    "ok",
    "okay",
}
REJECTION_WORDS = {
    "no",
    "nope",
    "cancel",
    "stop",
    "don't",
    "abort",
    "reject",
    "nevermind",
}


async def request_approval(action: str, description: str, details: dict) -> bool:
    """Pause execution and ask the user to approve before proceeding.

    Returns True if approved, False if rejected or timed out.
    """
    risk = HIGH_IMPACT_ACTIONS.get(action, ActionRisk.SAFE)
    if risk == ActionRisk.SAFE:
        return True

    approval_id = f"{action}_{uuid.uuid4().hex[:12]}"
    logger.info(f"ApprovalGate: requesting approval for '{action}': {description[:60]}")

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    _pending_approvals[approval_id] = future
    future.add_done_callback(lambda _: _pending_approvals.pop(approval_id, None))

    await event_bus.publish(
        AetherEvent(
            type=EventType.APPROVAL_REQUESTED,
            data={
                "approval_id": approval_id,
                "action": action,
                "description": description,
                "details": details,
                "risk": risk.value,
            },
            source_module="approval_gate",
        )
    )

    try:
        approved = await asyncio.wait_for(future, timeout=120)
        logger.info(f"ApprovalGate: {'approved' if approved else 'rejected'} — {action}")
        return approved
    except TimeoutError:
        logger.warning(f"ApprovalGate: timeout waiting for approval of '{action}' — rejecting")
        _pending_approvals.pop(approval_id, None)  # Clean up orphaned future
        return False


def resolve_approval(approval_id: str, approved: bool) -> None:
    """Called by Brain when the user responds yes/no to an approval request."""
    future = _pending_approvals.get(approval_id)
    if future and not future.done():
        future.set_result(approved)


def is_approval_response(text: str) -> bool | None:
    """Check if text is an approval or rejection. Returns True/False/None.

    Handles multi-word responses by stripping trailing punctuation
    and checking if any approval/rejection phrase is contained.
    """
    normalized = text.lower().strip().rstrip(".,!?")
    if normalized in APPROVAL_WORDS:
        return True
    if normalized in REJECTION_WORDS:
        return False
    # Check for approval/rejection words within longer text using word boundaries.
    # Check rejection FIRST so "don't do it" is correctly treated as rejection.
    for word in REJECTION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", normalized):
            return False
    for word in APPROVAL_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", normalized):
            return True
    return None


def get_pending_approval_ids() -> list[str]:
    """Return IDs of all pending approvals."""
    return [aid for aid, f in _pending_approvals.items() if not f.done()]
