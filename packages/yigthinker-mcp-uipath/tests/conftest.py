"""Shared pytest fixtures for the yigthinker-mcp-uipath test suite.

Test files in plans 11-02..11-06 import these fixtures by name. Do NOT change
fixture names without updating consumers.
"""
from __future__ import annotations

from typing import Any

import pytest

# Constants reused across test modules.
SAMPLE_TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token"
SAMPLE_BASE_URL = "https://cloud.uipath.com/acmecorp/DefaultTenant/orchestrator_"


@pytest.fixture
def sample_token_url() -> str:
    return SAMPLE_TOKEN_URL


@pytest.fixture
def sample_orchestrator_base_url() -> str:
    return SAMPLE_BASE_URL


@pytest.fixture
def sample_uipath_env() -> dict[str, str]:
    """Dummy env-var dict matching CONTEXT.md D-10 (resolved form).

    These are what server.py reads from os.environ at call time. Tests can
    ``monkeypatch.setenv(k, v)`` from this dict, or pass it directly to
    StdioServerParameters(env=...) for the smoke test in 11-06.
    """
    return {
        "UIPATH_BASE_URL": SAMPLE_BASE_URL,
        "UIPATH_ORGANIZATION": "acmecorp",
        "UIPATH_TENANT": "DefaultTenant",
        "UIPATH_CLIENT_ID": "test-client-id",
        "UIPATH_CLIENT_SECRET": "test-client-secret",
        "UIPATH_SCOPE": "OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring",
    }


@pytest.fixture
def sample_token_response() -> dict[str, Any]:
    """Mimics the UiPath /identity_/connect/token JSON body."""
    return {
        "access_token": "tok-test",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "OR.Execution OR.Jobs OR.Folders.Read OR.Queues OR.Monitoring",
    }


@pytest.fixture
def sample_folder_response() -> dict[str, Any]:
    """Mimics ``GET /odata/Folders?$filter=FullyQualifiedName eq '<path>'``."""
    return {"value": [{"Id": 42, "FullyQualifiedName": "Shared"}]}
