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


def test_tool_registry_empty() -> None:
    from yigthinker_mcp_uipath.tools import TOOL_REGISTRY
    assert isinstance(TOOL_REGISTRY, dict)
    assert TOOL_REGISTRY == {}


def test_main_entry_raises_until_06() -> None:
    # Plan 11-06 will replace this NotImplementedError with the real server.
    # Until then, calling main() must raise loudly so accidental Plan 11-01
    # ship-and-call does not silently succeed.
    from yigthinker_mcp_uipath.server import main
    import pytest as _pytest
    with _pytest.raises(NotImplementedError):
        main()
