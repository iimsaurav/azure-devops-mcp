"""Tests for authentication method detection and header generation."""

import base64
from unittest.mock import MagicMock, patch

import pytest

from azure_devops_mcp.auth import (
    _detect_auth_method,
    _get_pat_header,
    get_auth_header,
)


class TestDetectAuthMethod:
    """Test that the correct auth method is auto-detected from env vars."""

    def test_pat_takes_highest_priority(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_PAT", "my-pat-token")
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "some-secret")
        monkeypatch.setenv("AZURE_USE_MANAGED_IDENTITY", "true")
        assert _detect_auth_method() == "pat"

    def test_client_credentials_when_both_set(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "some-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "some-tenant-id")
        assert _detect_auth_method() == "client_credentials"

    def test_client_credentials_needs_both_vars(self, monkeypatch):
        """Only AZURE_CLIENT_ID without AZURE_CLIENT_SECRET should NOT trigger client_credentials."""
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_USE_MANAGED_IDENTITY", raising=False)
        assert _detect_auth_method() == "device_code"

    def test_managed_identity_true(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("AZURE_USE_MANAGED_IDENTITY", "true")
        assert _detect_auth_method() == "managed_identity"

    def test_managed_identity_yes(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("AZURE_USE_MANAGED_IDENTITY", "yes")
        assert _detect_auth_method() == "managed_identity"

    def test_managed_identity_one(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("AZURE_USE_MANAGED_IDENTITY", "1")
        assert _detect_auth_method() == "managed_identity"

    def test_managed_identity_false_falls_through(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("AZURE_USE_MANAGED_IDENTITY", "false")
        assert _detect_auth_method() == "device_code"

    def test_defaults_to_device_code(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_USE_MANAGED_IDENTITY", raising=False)
        assert _detect_auth_method() == "device_code"


class TestPatHeader:
    """Test PAT (Basic auth) header generation."""

    def test_pat_header_format(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_PAT", "test-pat-123")
        header = _get_pat_header()

        expected_encoded = base64.b64encode(b":test-pat-123").decode("utf-8")
        assert header == {"Authorization": f"Basic {expected_encoded}"}

    def test_pat_header_missing_raises(self, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        with pytest.raises(ValueError, match="AZURE_DEVOPS_PAT"):
            _get_pat_header()


class TestGetAuthHeader:
    """Test the public get_auth_header() function dispatches correctly."""

    def test_pat_returns_basic_header(self, monkeypatch):
        monkeypatch.setenv("AZURE_DEVOPS_PAT", "my-token")
        header = get_auth_header()
        assert "Basic" in header["Authorization"]

    @patch("azure_devops_mcp.auth._get_device_code_token")
    def test_device_code_returns_bearer(self, mock_token, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_USE_MANAGED_IDENTITY", raising=False)
        mock_token.return_value = "fake-bearer-token"

        header = get_auth_header()
        assert header == {"Authorization": "Bearer fake-bearer-token"}

    @patch("azure_devops_mcp.auth._get_client_credentials_token")
    def test_client_credentials_returns_bearer(self, mock_token, monkeypatch):
        monkeypatch.delenv("AZURE_DEVOPS_PAT", raising=False)
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-id")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant")
        mock_token.return_value = "fake-cc-token"

        header = get_auth_header()
        assert header == {"Authorization": "Bearer fake-cc-token"}
