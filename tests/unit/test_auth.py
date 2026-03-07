"""Tests for WebSocket authentication module."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_token_path(tmp_path):
    """Use a temp directory for token storage during tests."""
    token_file = tmp_path / "ws_token.txt"
    with patch("src.core.auth._token_path", token_file):
        yield token_file


def test_get_or_create_token_creates_new(mock_token_path):
    from src.core.auth import get_or_create_token

    token = get_or_create_token()
    assert len(token) == 64  # 32 bytes hex = 64 chars
    assert mock_token_path.exists()
    assert mock_token_path.read_text(encoding="utf-8") == token


def test_get_or_create_token_reads_existing(mock_token_path):
    mock_token_path.write_text("existing_token_abc123", encoding="utf-8")
    from src.core.auth import get_or_create_token

    token = get_or_create_token()
    assert token == "existing_token_abc123"  # noqa: S105  # test fixture


def test_verify_token_accepts_valid(mock_token_path):
    from src.core.auth import get_or_create_token, verify_token

    token = get_or_create_token()
    assert verify_token(token) is True


def test_verify_token_rejects_invalid(mock_token_path):
    from src.core.auth import get_or_create_token, verify_token

    get_or_create_token()  # ensure token exists
    assert verify_token("wrong_token_abc123") is False


def test_verify_token_rejects_empty(mock_token_path):
    from src.core.auth import verify_token

    assert verify_token("") is False


def test_get_token_for_client_returns_same(mock_token_path):
    from src.core.auth import get_or_create_token, get_token_for_client

    token1 = get_or_create_token()
    token2 = get_token_for_client()
    assert token1 == token2
