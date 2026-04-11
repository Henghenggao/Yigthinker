"""Scaffold test: confirms Plan 11-01 produced importable stub modules."""
from __future__ import annotations


def test_package_version() -> None:
    import yigthinker_mcp_uipath
    assert yigthinker_mcp_uipath.__version__ == "0.1.0"


def test_stub_modules_importable() -> None:
    # All 4 stub modules must be importable (Plan 11-01 stubs).
    from yigthinker_mcp_uipath import auth, client, nupkg, server
    # Touch attributes so the import is not optimized away.
    assert auth is not None
    assert client is not None
    assert nupkg is not None
    assert server is not None


def test_tool_registry_populated() -> None:
    # Plan 11-01 shipped TOOL_REGISTRY as an empty dict. Plan 11-05
    # populates it with the 5 UiPath tools per D-19. Once 11-05 has landed,
    # the registry MUST contain exactly these 5 tools — no more, no less.
    from yigthinker_mcp_uipath.tools import TOOL_REGISTRY
    assert isinstance(TOOL_REGISTRY, dict)
    assert set(TOOL_REGISTRY.keys()) == {
        "ui_deploy_process",
        "ui_trigger_job",
        "ui_job_history",
        "ui_manage_trigger",
        "ui_queue_status",
    }
    # Each entry must be a (input_model_cls, async_handler) tuple.
    for name, (model_cls, handler) in TOOL_REGISTRY.items():
        assert isinstance(model_cls, type), (
            f"{name}: input model must be a class"
        )
        assert callable(handler), f"{name}: handler must be callable"


def test_main_entry_raises_until_06() -> None:
    # Plan 11-06 will replace this NotImplementedError with the real server.
    # Until then, calling main() must raise loudly so accidental Plan 11-01
    # ship-and-call does not silently succeed.
    from yigthinker_mcp_uipath.server import main
    import pytest as _pytest
    with _pytest.raises(NotImplementedError):
        main()
