"""WebSocket server — the central connection hub for all clients.

Protocol
--------
Every inbound JSON frame has the shape::

    {"type": "<event-name>", "data": {...}, "request_id": "<optional>"}

The server converts each frame into an ``AetherEvent`` and publishes it on
the shared EventBus. Request/response correlation is carried by
``request_id``: handlers echo it back on the corresponding result event, and
the broadcaster copies it into the outgoing JSON payload so browser clients
can match replies to requests.

Two legacy message types are still recognised for backwards compatibility:
``"ping"`` returns ``"pong"`` inline (never reaches the bus); ``"message"``
is aliased to ``user_message``. Everything else flows through the generic
bridge — unknown types are logged and dropped without closing the socket.

Auth
----
Connections from localhost (127.0.0.1, ::1) skip the token check so the
default Next.js dev flow doesn't need to fetch a token first. Non-localhost
connections still require a valid token (query string or Authorization
header) as before.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import websockets
from loguru import logger

from src.core.auth import verify_token
from src.core.events import event_bus
from src.core.health import register_module, update_module_status
from src.core.rate_limiter import check_rate_limit, clear_bucket
from src.shared.config import get_settings
from src.shared.types import AetherEvent, EventType

_connected_clients: set = set()

MAX_MESSAGE_SIZE = 1_000_000  # 1MB max frame
MAX_CLIENTS = 10

# Event types the server re-broadcasts to all connected WebSocket clients.
_BROADCAST_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.RESPONSE_TEXT_CHUNK,
    EventType.RESPONSE_TEXT_READY,
    EventType.RESPONSE_START,
    EventType.RESPONSE_END,
    EventType.WIZARD_STEP_RESULT,
    EventType.ONBOARDING_COMPLETE,
    EventType.WIZARD_STATE_RESULT,
    EventType.LLM_KEY_TEST_RESULT,
    EventType.OLLAMA_PROBE_RESULT,
    EventType.VOICE_HARDWARE_PROBE_RESULT,
    EventType.PERSONA_CHANGED,
    EventType.PROVIDER_CHANGED,
    EventType.AVATAR_STATE_CHANGED,
    EventType.MODULE_READY,
    EventType.ERROR,
)

# Localhost hosts that bypass the token check.
_LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})

_LOCAL_SOURCE = "websocket_client"


async def broadcast(message: dict) -> None:
    """Send ``message`` as JSON to every connected client. Drops the dead ones."""
    if not _connected_clients:
        return
    data = json.dumps(message)
    disconnected = set()
    # Copy the set — a send failure will mutate _connected_clients via the
    # connection handler's finally block.
    for client in list(_connected_clients):
        try:
            await client.send(data)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
        except Exception as exc:
            logger.error(f"Server: broadcast error to client: {exc!r}")
            disconnected.add(client)
    _connected_clients.difference_update(disconnected)


# ---------------------------------------------------------------------------
# Connection handling.
# ---------------------------------------------------------------------------


def _is_localhost(websocket) -> bool:
    """Return True iff this websocket is a loopback connection."""
    remote = getattr(websocket, "remote_address", None)
    if not remote:
        return False
    host = remote[0]
    if not isinstance(host, str):
        return False
    return host in _LOCAL_HOSTS


def _extract_token(websocket) -> str:
    """Pull a bearer token from query string or Authorization header, or ""."""
    request = getattr(websocket, "request", None)
    if request is not None:
        path = getattr(request, "path", "") or ""
        headers = getattr(request, "headers", None) or {}
    else:
        path = getattr(websocket, "path", "") or ""
        headers = getattr(websocket, "request_headers", None) or {}

    if "?" in path:
        qs = parse_qs(urlparse(path).query)
        token = qs.get("token", [""])[0] or ""
        if token:
            return token

    auth_header = headers.get("Authorization", "") if hasattr(headers, "get") else ""
    if auth_header:
        return auth_header.removeprefix("Bearer ").strip()
    return ""


async def _reject(websocket, code: int, reason: str) -> None:
    """Close the socket and log the reason."""
    logger.warning(f"Server: rejecting client from {websocket.remote_address} — {reason}")
    await websocket.close(code, reason)


async def _handle_client(websocket) -> None:
    if len(_connected_clients) >= MAX_CLIENTS:
        await _reject(websocket, 4000, f"Max connections ({MAX_CLIENTS}) reached")
        return

    client_addr = websocket.remote_address
    if _is_localhost(websocket):
        logger.debug(f"Server: localhost connection from {client_addr} — skipping token check")
    else:
        token = _extract_token(websocket)
        if not token or not verify_token(token):
            await _reject(websocket, 4001, "Unauthorized")
            return

    connection_id = str(uuid.uuid4())
    _connected_clients.add(websocket)
    logger.info(
        f"Server: client connected from {client_addr} "
        f"(id={connection_id[:8]}, total={len(_connected_clients)})"
    )

    try:
        async for raw_message in websocket:
            await _dispatch_inbound(websocket, connection_id, raw_message)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Server: client {client_addr} disconnected cleanly")
    except Exception as exc:
        logger.error(f"Server: unexpected error with client {client_addr}: {exc!r}")
    finally:
        clear_bucket(connection_id)
        _connected_clients.discard(websocket)
        logger.info(
            f"Server: removed {client_addr} "
            f"(id={connection_id[:8]}, remaining={len(_connected_clients)})"
        )


async def _dispatch_inbound(websocket, connection_id: str, raw_message: Any) -> None:
    """Parse one inbound frame and route it through the generic bridge."""
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8", errors="replace")

    if len(raw_message) > MAX_MESSAGE_SIZE:
        logger.warning(f"Server: message too large ({len(raw_message)} bytes) from {connection_id[:8]}")
        return

    if not check_rate_limit(connection_id):
        try:
            await websocket.send(
                json.dumps({"type": "error", "data": {"message": "Rate limit exceeded."}})
            )
        except Exception:
            pass
        return

    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        logger.error(f"Server: invalid JSON from {connection_id[:8]}: {exc!r}")
        return

    if not isinstance(message, dict):
        logger.warning(f"Server: ignored non-object frame from {connection_id[:8]}")
        return

    msg_type = message.get("type", "")
    if not isinstance(msg_type, str) or not msg_type:
        logger.warning(f"Server: frame from {connection_id[:8]} missing 'type'")
        return

    # --- Legacy / inline special cases ------------------------------------
    if msg_type == "ping":
        try:
            await websocket.send(json.dumps({"type": "pong"}))
        except Exception as exc:
            logger.debug(f"Server: pong send failed: {exc!r}")
        return

    # "message" is the pre-contract legacy alias for USER_MESSAGE.
    if msg_type == "message":
        msg_type = EventType.USER_MESSAGE.value

    # --- Generic bridge ---------------------------------------------------
    try:
        event_type = EventType(msg_type)
    except ValueError:
        logger.warning(f"Server: unknown message type '{msg_type}' from {connection_id[:8]}")
        return

    data = message.get("data")
    if data is None:
        # Back-compat: older clients put payload fields at the top level.
        data = {k: v for k, v in message.items() if k not in {"type", "data", "request_id"}}
    if not isinstance(data, dict):
        logger.warning(f"Server: '{msg_type}' data must be an object, got {type(data).__name__}")
        return

    request_id = message.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        logger.warning(f"Server: '{msg_type}' request_id must be a string; ignoring")
        request_id = None

    if request_id is not None:
        # Stash request_id into data too so handlers that predate the field
        # on AetherEvent can still recover it.
        data = {**data, "request_id": request_id}

    event = AetherEvent(
        type=event_type,
        data=data,
        source_module=_LOCAL_SOURCE,
        request_id=request_id,
    )
    await event_bus.publish(event)


# ---------------------------------------------------------------------------
# Outbound: broadcast selected EventBus events to every connected client.
# ---------------------------------------------------------------------------


async def _broadcast_event(event: AetherEvent) -> None:
    """Serialize ``event`` in the frontend's expected shape and broadcast it."""
    request_id = event.request_id
    if request_id is None:
        # Handlers that stuff request_id into data (pre-native-field path)
        # still work — pick it up here.
        raw = event.data.get("request_id") if isinstance(event.data, dict) else None
        if isinstance(raw, str):
            request_id = raw

    payload: dict[str, Any] = {
        "type": event.type.value if isinstance(event.type, EventType) else str(event.type),
        "data": event.data if isinstance(event.data, dict) else {},
        "timestamp": event.timestamp,
    }
    if request_id is not None:
        payload["request_id"] = request_id
    await broadcast(payload)


# Reload YAML config on settings change. Kept from the previous server.
async def _on_settings_changed(event: AetherEvent) -> None:
    from src.shared.config import reload_yaml_config

    try:
        reload_yaml_config()
        logger.info("Server: YAML config reloaded after settings change")
    except Exception as exc:
        logger.error(f"Server: failed to reload config: {exc!r}")
    # Also broadcast so other clients hear the change.
    await _broadcast_event(event)


# ---------------------------------------------------------------------------
# Startup.
# ---------------------------------------------------------------------------

_subscriptions_registered = False


def _register_broadcast_subscriptions() -> None:
    """Subscribe the broadcaster to every event the frontend cares about.

    Idempotent — running twice leaves a single handler per event type.
    """
    global _subscriptions_registered
    if _subscriptions_registered:
        return
    for event_type in _BROADCAST_EVENT_TYPES:
        event_bus.subscribe(event_type, _broadcast_event)
    event_bus.subscribe(EventType.SETTINGS_CHANGED, _on_settings_changed)
    _subscriptions_registered = True
    logger.debug(f"Server: registered {len(_BROADCAST_EVENT_TYPES) + 1} broadcast subscriptions")


async def start_websocket_server() -> None:
    settings = get_settings()
    register_module("websocket_server", "starting")

    _register_broadcast_subscriptions()

    port = settings.websocket_port
    host = settings.server_host
    logger.info(f"Server: starting WebSocket server on {host}:{port}")
    async with websockets.serve(_handle_client, host, port, max_size=MAX_MESSAGE_SIZE):
        update_module_status("websocket_server", "ready")
        logger.info(f"Server: WebSocket server listening on ws://{host}:{port}")
        await asyncio.Future()  # run forever
