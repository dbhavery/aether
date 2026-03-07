"""Tests for Data Server authentication."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestDataServerAuth:
    """Verify that Data Server requires auth on sensitive endpoints."""

    def _get_test_client(self):
        with patch("src.data_server.app._init_db"):
            from src.data_server.app import create_data_server_app

            app = create_data_server_app()
            return TestClient(app)

    def test_health_endpoint_is_public(self):
        client = self._get_test_client()
        response = client.get("/health")
        assert response.status_code == 200

    def test_items_endpoint_requires_auth(self):
        client = self._get_test_client()
        response = client.get("/items")
        assert response.status_code == 401

    def test_search_endpoint_requires_auth(self):
        client = self._get_test_client()
        response = client.get("/search?q=test")
        assert response.status_code == 401

    def test_valid_token_passes_auth_check(self):
        """With valid token, auth dependency should not raise 401."""
        import asyncio

        from src.core.auth import get_or_create_token
        from src.data_server.app import _verify_auth

        token = get_or_create_token()
        request = MagicMock()
        request.url.path = "/items"
        request.headers.get.return_value = f"Bearer {token}"
        request.query_params.get.return_value = ""
        # Should not raise
        asyncio.get_event_loop().run_until_complete(_verify_auth(request))

    def test_items_with_invalid_token(self):
        client = self._get_test_client()
        response = client.get("/items", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 401
