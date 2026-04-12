"""Scaffold test: confirms Plan 12-01 produced importable stub modules."""
from __future__ import annotations


def test_package_version() -> None:
    import yigthinker_mcp_powerautomate
    assert yigthinker_mcp_powerautomate.__version__ == "0.1.0"


def test_stub_modules_importable() -> None:
    # All 5 stub modules must be importable (Plan 12-01 stubs).
    from yigthinker_mcp_powerautomate import (
        auth,
        client,
        config,
        flow_builder,
        server,
    )
    # Touch attributes so the import is not optimized away.
    assert auth is not None
    assert client is not None
    assert flow_builder is not None
    assert config is not None
    assert server is not None


def test_tool_registry_empty() -> None:
    # Plan 12-01 ships TOOL_REGISTRY as an empty dict. Plan 12-05
    # will populate it with the 5 Power Automate tools per D-23.
    from yigthinker_mcp_powerautomate.tools import TOOL_REGISTRY
    assert isinstance(TOOL_REGISTRY, dict)
    assert len(TOOL_REGISTRY) == 0
