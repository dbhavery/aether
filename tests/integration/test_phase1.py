"""Phase 1 integration tests — full pipeline validation.

These tests require a running Aether server. They skip automatically
when the server is not reachable.
"""

import asyncio
import json
import socket
import time

import pytest
import websockets


def _server_reachable(host: str = "localhost", port: int = 8765, timeout: float = 1.0) -> bool:
    """Check if the Aether server is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


server_required = pytest.mark.skipif(not _server_reachable(), reason="Aether server not running on localhost:8765")


@server_required
@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_text_conversation_pipeline():
    """Full pipeline: user types -> Aether responds with memory stored."""
    from src.core.auth import get_or_create_token

    token = get_or_create_token()
    async with websockets.connect(f"ws://localhost:8765?token={token}") as ws:
        # Test ping
        await ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert pong["type"] == "pong"

        # Test conversation
        await ws.send(
            json.dumps(
                {
                    "type": "message",
                    "text": "Hello Aether, my name is User.",
                    "timestamp": str(time.time()),
                }
            )
        )

        # Collect responses (may receive interim + final)
        responses = []
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)
                responses.append(msg)
                if msg.get("type") == "response" and not msg.get("is_interim"):
                    break
            except TimeoutError:
                break

        assert len(responses) > 0, "No response received"
        final = [r for r in responses if r.get("type") == "response" and not r.get("is_interim")]
        assert len(final) > 0, "No final response received"
        assert len(final[0]["text"]) > 0, "Response text is empty"
        print(f"\nAether said: {final[0]['text']}")


@server_required
@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_health_endpoint():
    """Health endpoint returns valid JSON."""
    import aiohttp

    async with aiohttp.ClientSession() as session, session.get("http://localhost:8767/health") as resp:
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] in ("ok", "degraded"), f"Unexpected status: {data['status']}"
        assert "modules" in data
        assert "uptime_seconds" in data
