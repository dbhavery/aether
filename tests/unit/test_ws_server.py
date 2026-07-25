"""Tests for WebSocket server auth and rate limiting — import-level verification.

These tests verify that the auth and rate_limiter modules can be imported
and that their core functions are accessible with expected signatures.
No real WebSocket connections are created.
"""

import importlib


class TestRateLimiterImport:
    """Verify the rate_limiter module is importable and has expected API."""

    def test_rate_limiter_imported(self):
        """The rate_limiter module should import without error."""
        mod = importlib.import_module("src.core.rate_limiter")
        assert mod is not None

    def test_rate_limiter_has_check_function(self):
        """check_rate_limit must exist and be callable."""
        from src.core.rate_limiter import check_rate_limit

        assert callable(check_rate_limit)

    def test_rate_limiter_has_clear_function(self):
        """clear_bucket must exist and be callable."""
        from src.core.rate_limiter import clear_bucket

        assert callable(clear_bucket)

    def test_rate_limiter_allows_first_message(self):
        """A fresh connection should not be rate-limited on the first message."""
        from src.core.rate_limiter import check_rate_limit, clear_bucket

        test_id = "test-import-check-001"
        try:
            result = check_rate_limit(test_id)
            assert result is True, "First message from a new connection should be allowed"
        finally:
            clear_bucket(test_id)


class TestAuthModuleImport:
    """Verify the auth module is importable and has expected API."""

    def test_auth_module_imported(self):
        """The auth module should import without error."""
        mod = importlib.import_module("src.core.auth")
        assert mod is not None

    def test_auth_has_verify_token(self):
        """verify_token must exist and be callable."""
        from src.core.auth import verify_token

        assert callable(verify_token)

    def test_auth_has_get_or_create_token(self):
        """get_or_create_token must exist and be callable."""
        from src.core.auth import get_or_create_token

        assert callable(get_or_create_token)

    def test_auth_has_rotate_token(self):
        """rotate_token must exist and be callable."""
        from src.core.auth import rotate_token

        assert callable(rotate_token)

    def test_verify_token_rejects_empty(self):
        """verify_token should return False for an empty string."""
        from src.core.auth import verify_token

        assert verify_token("") is False
