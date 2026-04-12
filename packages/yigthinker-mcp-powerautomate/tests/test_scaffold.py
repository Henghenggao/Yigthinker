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


def test_tool_registry_populated() -> None:
    # Plan 12-05 populates TOOL_REGISTRY with 5 Power Automate tools per D-23.
    from yigthinker_mcp_powerautomate.tools import TOOL_REGISTRY
    assert isinstance(TOOL_REGISTRY, dict)
    assert set(TOOL_REGISTRY.keys()) == {
        "pa_deploy_flow",
        "pa_trigger_flow",
        "pa_flow_status",
        "pa_pause_flow",
        "pa_list_connections",
    }
    # Each entry is a (InputModel, handler) tuple.
    for name, entry in TOOL_REGISTRY.items():
        assert isinstance(entry, tuple), f"{name}: expected tuple"
        assert len(entry) == 2, f"{name}: expected 2-tuple"
        model_cls, handler_fn = entry
        assert isinstance(model_cls, type), f"{name}: first element must be a type"
        assert callable(handler_fn), f"{name}: second element must be callable"
