"""Module entry point: ``python -m yigthinker_mcp_powerautomate``.

Boots the MCP stdio server wired in :mod:`yigthinker_mcp_powerautomate.server`.
Logging is routed to stderr so stdout stays clean for the MCP stdio protocol.
"""
from __future__ import annotations

import asyncio
import logging
import sys


def main() -> None:
    """CLI entry point — called by ``python -m yigthinker_mcp_powerautomate`` and by
    the ``yigthinker-mcp-powerautomate`` console script declared in ``pyproject.toml``.
    """
    # MCP servers log to stderr so stdout stays clean for the protocol.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    try:
        from .server import run_stdio

        asyncio.run(run_stdio())
    except KeyboardInterrupt:
        sys.exit(0)
    except RuntimeError as exc:
        print(f"yigthinker-mcp-powerautomate: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
