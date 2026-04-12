"""Shared pytest fixtures for the yigthinker-mcp-powerautomate test suite.

Test files in plans 12-02..12-06 import these fixtures by name. Do NOT change
fixture names without updating consumers.

Auth mocking: MSAL is mocked via ``monkeypatch`` / ``unittest.mock.patch``
on ``msal.ConfidentialClientApplication.acquire_token_for_client`` (D-26),
NOT via ``respx``, because MSAL uses its own internal HTTP stack.
"""
from __future__ import annotations

from typing import Any

import pytest

# Constants reused across test modules.
SAMPLE_BASE_URL = "https://api.flow.microsoft.com"
SAMPLE_TENANT_ID = "test-tenant-id"


@pytest.fixture
def sample_pa_env() -> dict[str, str]:
    """Dummy env-var dict matching CONTEXT.md D-10/D-11 (resolved form).

    These are what config.py reads from os.environ at call time. Tests can
    ``monkeypatch.setenv(k, v)`` from this dict.

    POWERAUTOMATE_SCOPE and POWERAUTOMATE_AUTHORITY are intentionally omitted
    to exercise the default fallback code path.
    """
    return {
        "POWERAUTOMATE_TENANT_ID": SAMPLE_TENANT_ID,
        "POWERAUTOMATE_CLIENT_ID": "test-client-id",
        "POWERAUTOMATE_CLIENT_SECRET": "test-client-secret",
        "POWERAUTOMATE_BASE_URL": SAMPLE_BASE_URL,
        # POWERAUTOMATE_SCOPE intentionally omitted -- tests default fallback
        # POWERAUTOMATE_AUTHORITY intentionally omitted -- tests default fallback
    }


@pytest.fixture
def sample_msal_token_response() -> dict[str, Any]:
    """Mimics a successful MSAL acquire_token_for_client response."""
    return {
        "access_token": "tok-test",
        "expires_in": 3600,
        "token_type": "Bearer",
    }


@pytest.fixture
def sample_msal_error_response() -> dict[str, Any]:
    """Mimics an MSAL error response (e.g. admin consent not granted)."""
    return {
        "error": "AADSTS65001",
        "error_description": "The user or administrator has not consented",
    }


@pytest.fixture
def sample_base_url() -> str:
    """Return the sample Power Automate base URL."""
    return SAMPLE_BASE_URL
