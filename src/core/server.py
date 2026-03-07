"""WebSocket server — the central connection hub for all clients."""

import asyncio
import json
import uuid
from urllib.parse import parse_qs, urlparse

import websockets
from loguru import logger

from src.core.auth import verify_token
from src.core.events import event_bus
from src.core.health import register_module, update_module_status
from src.core.rate_limiter import check_rate_limit, clear_bucket
from src.shared.config import get_settings
from src.shared.types import EventType, InteractionMode, AetherEvent
from src.tools.approval_gate import resolve_approval

_connected_clients: set = set()


async def broadcast(message: dict) -> None:
    if not _connected_clients:
        return
    data = json.dumps(message)
    disconnected = set()
    # Copy the set to avoid RuntimeError if _handle_client modifies it during iteration
    for client in list(_connected_clients):
        try:
            await client.send(data)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
        except Exception as e:
            logger.error(f"Server: broadcast error to client: {e}")
            disconnected.add(client)
    _connected_clients.difference_update(disconnected)


MAX_MESSAGE_SIZE = 1_000_000  # 1MB max message size (upgraded from 50KB)
MAX_CLIENTS = 10


async def _handle_client(websocket) -> None:
    if len(_connected_clients) >= MAX_CLIENTS:
        logger.warning(f"Server: rejecting client — max connections ({MAX_CLIENTS}) reached")
        await websocket.close(4000, "Max connections reached")
        return

    # --- Auth check: extract token from query string or Authorization header ---
    # websockets 15+: request info is on websocket.request
    request = getattr(websocket, "request", None)
    token = None
    if request is not None:
        path = getattr(request, "path", "") or ""
        headers = getattr(request, "headers", None) or {}
    else:
        # Fallback for older websockets API
        path = getattr(websocket, "path", "") or ""
        headers = getattr(websocket, "request_headers", None) or {}
    if "?" in path:
        qs = parse_qs(urlparse(path).query)
        token = qs.get("token", [None])[0]
    if not token:
        auth_header = headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not token or not verify_token(token):
        logger.warning(f"Server: rejected unauthenticated connection from {websocket.remote_address}")
        await websocket.close(4001, "Unauthorized")
        return

    connection_id = str(uuid.uuid4())
    _connected_clients.add(websocket)
    client_addr = websocket.remote_address
    logger.info(f"Server: authenticated client connected from {client_addr}. Total clients: {len(_connected_clients)}")
    try:
        async for raw_message in websocket:
            try:
                if len(raw_message) > MAX_MESSAGE_SIZE:
                    logger.warning(f"Server: message too large ({len(raw_message)} bytes) from {client_addr}")
                    continue

                # Rate limit check
                if not check_rate_limit(connection_id):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "Rate limit exceeded. Please slow down.",
                            }
                        )
                    )
                    continue

                message = json.loads(raw_message)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    continue

                if msg_type == "approval_response":
                    approval_id = message.get("approval_id", "")
                    approved = message.get("approved", False)
                    if approval_id:
                        resolve_approval(approval_id, approved)
                        logger.info(f"Server: approval '{approval_id}' -> {'approved' if approved else 'rejected'}")
                    continue

                if msg_type in ("message", "user_message"):
                    text = message.get("text", "")
                    if len(text) > 10_000:
                        logger.warning(f"Server: message text truncated ({len(text)} chars) from {client_addr}")
                        text = text[:10_000]
                    # Validate interaction mode — reject invalid values
                    raw_mode = message.get("mode", InteractionMode.TEXT)
                    try:
                        mode = InteractionMode(raw_mode) if isinstance(raw_mode, str) else raw_mode
                    except ValueError:
                        logger.warning(f"Server: invalid mode '{raw_mode}' from {client_addr}, defaulting to TEXT")
                        mode = InteractionMode.TEXT
                    event = AetherEvent(
                        type=EventType.USER_MESSAGE,
                        data={
                            "text": text,
                            "timestamp": message.get("timestamp", ""),
                            "mode": mode,
                        },
                        source_module="websocket_server",
                    )
                    await event_bus.publish(event)
                elif msg_type == "settings_changed":
                    event = AetherEvent(
                        type=EventType.SETTINGS_CHANGED,
                        data=message.get("changes", {}),
                        source_module="desktop_settings",
                    )
                    await event_bus.publish(event)
                    logger.info("Server: settings changed, notifying modules")
                else:
                    logger.warning(f"Server: unknown message type '{msg_type}' from {client_addr}")

            except json.JSONDecodeError as e:
                logger.error(f"Server: invalid JSON from {client_addr}: {e}")
            except Exception as e:
                logger.error(f"Server: error handling message from {client_addr}: {e}")

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Server: client {client_addr} disconnected cleanly")
    except Exception as e:
        logger.error(f"Server: unexpected error with client {client_addr}: {e}")
    finally:
        clear_bucket(connection_id)
        _connected_clients.discard(websocket)
        logger.info(f"Server: removed {client_addr}. Total clients: {len(_connected_clients)}")


# Subscribe to response events and broadcast to all clients
async def _on_response_ready(event: AetherEvent) -> None:
    await broadcast(
        {
            "type": "response",
            "text": event.data.get("text", ""),
            "emotion": event.data.get("emotion", "neutral"),
            "timestamp": event.timestamp,
            "is_interim": event.data.get("is_interim", False),
        }
    )


async def _on_wake_word(event: AetherEvent) -> None:
    await broadcast({"type": "wake_word", "listening": True})


async def _on_proactive_message(event: AetherEvent) -> None:
    """Broadcast proactive messages (daily interview, reminders) to all clients."""
    await broadcast(
        {
            "type": "proactive",
            "text": event.data.get("text", ""),
            "category": event.data.get("category", "general"),
            "timestamp": event.timestamp,
        }
    )


async def _on_settings_changed(event: AetherEvent) -> None:
    """Reload config when settings are changed from desktop."""
    from src.shared.config import reload_yaml_config

    try:
        reload_yaml_config()
        logger.info("Server: YAML config reloaded after settings change")
    except Exception as e:
        logger.error(f"Server: failed to reload config: {e}")


async def _on_approval_requested(event: AetherEvent) -> None:
    """Broadcast approval requests to desktop so the user can approve/reject."""
    await broadcast(
        {
            "type": "approval_request",
            "approval_id": event.data.get("approval_id", ""),
            "action": event.data.get("action", ""),
            "description": event.data.get("description", ""),
            "risk": event.data.get("risk", "confirm"),
        }
    )


async def _on_transcript_ready(event: AetherEvent) -> None:
    """Broadcast transcript to desktop for real-time display."""
    await broadcast(
        {
            "type": "transcript",
            "text": event.data.get("text", ""),
            "confidence": event.data.get("confidence", 0),
            "timestamp": event.timestamp,
        }
    )


async def _on_speaker_verified(event: AetherEvent) -> None:
    """Broadcast speaker verification result to desktop."""
    await broadcast(
        {
            "type": "speaker_verified",
            "is_don": event.data.get("is_don", True),
            "score": event.data.get("score", 0),
            "timestamp": event.timestamp,
        }
    )


async def _on_module_ready(event: AetherEvent) -> None:
    if event.data.get("module") == "avatar":
        await broadcast(
            {
                "type": "avatar_stream",
                "url": event.data.get("stream_url", ""),
                "available": event.data.get("available", False),
            }
        )


async def start_websocket_server() -> None:
    settings = get_settings()
    register_module("websocket_server", "starting")
    event_bus.subscribe(EventType.RESPONSE_TEXT_READY, _on_response_ready)
    event_bus.subscribe(EventType.WAKE_WORD_DETECTED, _on_wake_word)
    event_bus.subscribe(EventType.TRANSCRIPT_READY, _on_transcript_ready)
    event_bus.subscribe(EventType.SPEAKER_VERIFIED, _on_speaker_verified)
    event_bus.subscribe(EventType.MODULE_READY, _on_module_ready)
    event_bus.subscribe(EventType.PROACTIVE_MESSAGE, _on_proactive_message)
    event_bus.subscribe(EventType.SETTINGS_CHANGED, _on_settings_changed)
    event_bus.subscribe(EventType.APPROVAL_REQUESTED, _on_approval_requested)
    port = settings.websocket_port
    logger.info(f"Server: starting WebSocket server on port {port}")
    host = settings.server_host
    async with websockets.serve(_handle_client, host, port, max_size=MAX_MESSAGE_SIZE):
        update_module_status("websocket_server", "ready")
        logger.info(f"Server: WebSocket server listening on ws://{host}:{port}")
        await asyncio.Future()  # run forever
