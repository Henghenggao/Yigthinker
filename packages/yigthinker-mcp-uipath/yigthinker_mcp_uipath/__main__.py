"""Module entry point: ``python -m yigthinker_mcp_uipath``.

Delegates to ``yigthinker_mcp_uipath.server.main`` which is wired in Plan 11-06.
Until then this module raises NotImplementedError so the import does not silently
succeed against an empty server.
"""
from __future__ import annotations


def main() -> None:
    from yigthinker_mcp_uipath.server import main as _server_main
    _server_main()


if __name__ == "__main__":
    main()
