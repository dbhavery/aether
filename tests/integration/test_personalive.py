"""Integration tests for PersonaLive avatar server.
Auto-skips when PersonaLive server is not running on port 8770.
"""

import pytest

PERSONALIVE_URL = "http://localhost:8770"


def _personalive_running() -> bool:
    """Check if PersonaLive server (specifically) is listening on port 8770."""
    try:
        import httpx

        r = httpx.get("http://localhost:8770/health", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return data.get("engine") == "personalive"
    except Exception:
        return False
    return False


@pytest.fixture(autouse=True)
def skip_if_not_running():
    if not _personalive_running():
        pytest.skip("PersonaLive server not running on port 8770 (or different engine detected)")


def test_health():
    import httpx

    r = httpx.get(f"{PERSONALIVE_URL}/health", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "loading")
    assert data["engine"] == "personalive"


def test_set_mode():
    import httpx

    for mode in ["idle", "listening", "speaking"]:
        r = httpx.post(f"{PERSONALIVE_URL}/mode", json={"mode": mode}, timeout=5)
        assert r.status_code == 200
        assert r.json()["mode"] == mode


def test_speaking_toggle():
    import httpx

    r = httpx.post(f"{PERSONALIVE_URL}/speaking", json={"speaking": True}, timeout=5)
    assert r.json()["mode"] == "speaking"
    r = httpx.post(f"{PERSONALIVE_URL}/speaking", json={"speaking": False}, timeout=5)
    assert r.json()["mode"] == "idle"


def test_stream_responds():
    import httpx

    with httpx.stream("GET", f"{PERSONALIVE_URL}/stream", timeout=10) as resp:
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "multipart" in content_type
        # Read at least one frame boundary
        for chunk in resp.iter_bytes():
            if b"--frame" in chunk:
                break


def test_benchmark_fps():
    import httpx

    r = httpx.get(f"{PERSONALIVE_URL}/benchmark", timeout=120)
    assert r.status_code == 200
    fps = r.json()["fps"]
    assert fps >= 0


def test_audio_chunk_accepted():
    import base64

    import httpx

    # Send 100ms of silence at 16kHz (int16)
    silence = bytes(3200)
    r = httpx.post(
        f"{PERSONALIVE_URL}/audio_chunk",
        json={"audio_b64": base64.b64encode(silence).decode()},
        timeout=5,
    )
    assert r.status_code == 200
    assert "queued" in r.json()
