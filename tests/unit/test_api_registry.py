"""Tests for api_registry and key_store modules."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from src.shared.api_registry import (
    AuthMethod,
    ServiceCategory,
    ServiceDefinition,
    all_services,
    get_service,
    get_service_status,
    get_services_by_category,
)
from src.shared.key_store import delete_key, get_key, mask_key, set_key

if TYPE_CHECKING:
    from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
# api_registry tests
# ═══════════════════════════════════════════════════════════════════


class TestServiceDefinitions:
    """Validate that every registered service has the required fields."""

    def test_all_services_have_required_fields(self) -> None:
        services = all_services()
        assert len(services) > 0, "No services registered"
        for svc in services:
            assert svc.name, f"Service missing name: {svc}"
            assert svc.display_name, f"Service {svc.name} missing display_name"
            assert svc.env_var, f"Service {svc.name} missing env_var"
            assert svc.description, f"Service {svc.name} missing description"
            assert isinstance(svc.auth_method, AuthMethod), f"Service {svc.name} has invalid auth_method"
            assert isinstance(svc.category, ServiceCategory), f"Service {svc.name} has invalid category"

    def test_no_duplicate_keys(self) -> None:
        services = all_services()
        names = [svc.name for svc in services]
        assert len(names) == len(set(names)), (
            f"Duplicate service names found: {[n for n in names if names.count(n) > 1]}"
        )

    def test_get_service_returns_correct(self) -> None:
        svc = get_service("elevenlabs")
        assert svc is not None
        assert svc.name == "elevenlabs"
        assert svc.display_name == "ElevenLabs"
        assert svc.env_var == "ELEVENLABS_API_KEY"
        assert svc.category == ServiceCategory.VOICE

    def test_get_service_returns_none_for_unknown(self) -> None:
        svc = get_service("xyz_nonexistent_service")
        assert svc is None

    def test_categories_populated(self) -> None:
        llm_services = get_services_by_category(ServiceCategory.LLM)
        assert len(llm_services) > 0, "LLM category has no services"

        voice_services = get_services_by_category(ServiceCategory.VOICE)
        assert len(voice_services) > 0, "Voice category has no services"

    def test_gateway_services_status(self) -> None:
        """GATEWAY services should report configured based on env, not key file."""
        services = all_services()
        gateway_svcs = [s for s in services if s.auth_method == AuthMethod.GATEWAY]
        assert len(gateway_svcs) > 0, "No GATEWAY services registered"

        for svc in gateway_svcs:
            # Clear the env var so key_present is False
            old_val = os.environ.pop(svc.env_var, None)
            try:
                status = get_service_status(svc.name)
                assert status is not None
                assert status.name == svc.name
                # GATEWAY services with no env var → not configured
                assert status.key_present is False
                # connected is None because no test_fn ran
                assert status.connected is None
            finally:
                if old_val is not None:
                    os.environ[svc.env_var] = old_val


class TestServiceStatus:
    """Test get_service_status behavior."""

    def test_status_with_test_fn_success(self) -> None:
        """A service with a passing test_fn should report connected=True."""
        from src.shared.api_registry import _SERVICES, _register

        test_svc = ServiceDefinition(
            name="_test_pass_svc",
            display_name="Test Passing",
            auth_method=AuthMethod.API_KEY,
            env_var="_TEST_PASS_KEY",
            category=ServiceCategory.TOOLS,
            description="Temporary service for testing.",
            test_fn=lambda: (True, "All good"),
        )
        _register(test_svc)
        os.environ[test_svc.env_var] = "fake-key-123"
        try:
            status = get_service_status("_test_pass_svc")
            assert status is not None
            assert status.connected is True
            assert status.message == "All good"
        finally:
            os.environ.pop("_TEST_PASS_KEY", None)
            _SERVICES.pop("_test_pass_svc", None)

    def test_status_with_test_fn_failure(self) -> None:
        """A service with a failing test_fn should report connected=False."""
        from src.shared.api_registry import _SERVICES, _register

        test_svc = ServiceDefinition(
            name="_test_fail_svc",
            display_name="Test Failing",
            auth_method=AuthMethod.API_KEY,
            env_var="_TEST_FAIL_KEY",
            category=ServiceCategory.TOOLS,
            description="Temporary service for testing.",
            test_fn=lambda: (False, "Connection refused"),
        )
        _register(test_svc)
        os.environ[test_svc.env_var] = "fake-key-456"
        try:
            status = get_service_status("_test_fail_svc")
            assert status is not None
            assert status.connected is False
            assert status.message == "Connection refused"
        finally:
            os.environ.pop("_TEST_FAIL_KEY", None)
            _SERVICES.pop("_test_fail_svc", None)

    def test_status_unknown_service(self) -> None:
        status = get_service_status("totally_unknown_service")
        assert status is None


# ═══════════════════════════════════════════════════════════════════
# key_store tests
# ═══════════════════════════════════════════════════════════════════


class TestKeyStore:
    """Test key_store set/get/delete/mask operations.

    Uses a temporary .env file to avoid touching the real one.
    """

    @pytest.fixture(autouse=True)
    def _use_temp_env(self, tmp_path: Path) -> None:
        """Redirect key_store to a temporary .env file for each test."""
        self._env_file = tmp_path / ".env"
        self._env_file.write_text("", encoding="utf-8")
        self._patch = patch.dict(
            os.environ,
            {"AETHER_ENV_PATH": str(self._env_file)},
            clear=False,
        )
        self._patch.start()
        yield
        self._patch.stop()

    def test_set_and_get_key(self) -> None:
        # Clear any pre-existing env value
        os.environ.pop("TEST_API_KEY_XYZ", None)

        set_key("TEST_API_KEY_XYZ", "sk-secret-12345")

        # Verify os.environ was updated
        assert os.environ.get("TEST_API_KEY_XYZ") == "sk-secret-12345"

        # Verify file was written
        content = self._env_file.read_text(encoding="utf-8")
        assert "TEST_API_KEY_XYZ=sk-secret-12345" in content

        # Verify get_key returns the value
        assert get_key("TEST_API_KEY_XYZ") == "sk-secret-12345"

        # Cleanup
        os.environ.pop("TEST_API_KEY_XYZ", None)

    def test_delete_key(self) -> None:
        os.environ.pop("TEST_DEL_KEY", None)

        set_key("TEST_DEL_KEY", "value-to-delete")
        assert get_key("TEST_DEL_KEY") == "value-to-delete"

        removed = delete_key("TEST_DEL_KEY")
        assert removed is True

        # Verify removed from env
        assert os.environ.get("TEST_DEL_KEY") is None

        # Verify removed from file
        content = self._env_file.read_text(encoding="utf-8")
        assert "TEST_DEL_KEY" not in content

        # get_key should return None
        assert get_key("TEST_DEL_KEY") is None

    def test_delete_key_not_present(self) -> None:
        removed = delete_key("NONEXISTENT_KEY_ABC")
        assert removed is False

    def test_mask_key(self) -> None:
        # "sk-abc123xyz" is 12 chars; visible_chars=4 → hidden=8
        # Last 4 chars are "3xyz", first 8 replaced with bullets
        result = mask_key("sk-abc123xyz")
        assert result == "••••••••3xyz"
        assert result.endswith("3xyz")
        assert result.count("•") == 8

    def test_mask_key_none(self) -> None:
        assert mask_key(None) == "(not set)"

    def test_mask_key_empty(self) -> None:
        assert mask_key("") == "(not set)"

    def test_mask_key_short(self) -> None:
        # Value shorter than visible_chars → all bullets
        result = mask_key("abc")
        assert result == "•••"

    def test_set_key_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            set_key("", "value")
        with pytest.raises(ValueError):
            set_key("KEY", "")

    def test_set_key_overwrites_existing(self) -> None:
        os.environ.pop("TEST_OVERWRITE", None)

        set_key("TEST_OVERWRITE", "first-value")
        assert get_key("TEST_OVERWRITE") == "first-value"

        set_key("TEST_OVERWRITE", "second-value")
        assert get_key("TEST_OVERWRITE") == "second-value"

        # File should contain only one line for this key
        content = self._env_file.read_text(encoding="utf-8")
        assert content.count("TEST_OVERWRITE") == 1

        os.environ.pop("TEST_OVERWRITE", None)
