"""MCP low-level stdio server for UiPath Orchestrator integration.

Uses :class:`mcp.server.lowlevel.Server` (NOT FastMCP) because core Yigthinker's
``_MCPToolWrapper`` only understands :class:`TextContent` blocks (RESEARCH.md
Finding 6). Tool results are serialized as a single ``TextContent.text`` block
containing ``json.dumps(handler_result)`` per D-20.

Architectural invariants (locked decisions — do NOT deviate):

- **D-04:** low-level ``Server``, not FastMCP.
- **D-09:** :class:`UipathAuth` takes 5 fields — ``client_id``,
  ``client_secret``, ``tenant_name``, ``organization``, ``scope`` (space-
  separated string, not list).
- **D-13:** :class:`OrchestratorClient` takes exactly 2 args: ``auth`` and
  ``base_url``. The ``httpx.AsyncClient`` is created internally — never pass
  ``http=`` here.
- **D-15:** this module MUST NOT import anything from the core ``yigthinker``
  package (architect-not-executor invariant). The sanity acceptance check in
  PLAN 11-06 walks this module's AST to enforce.
- **D-20 + Finding 6:** every ``call_tool`` response is a single
  ``[TextContent(type="text", text=json.dumps(result))]`` list.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.lowlevel import Server
from mcp.types import TextContent, Tool
from pydantic import ValidationError

from .auth import UipathAuth
from .client import OrchestratorClient
from .config import UipathConfig
from .tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)


def build_server(config: UipathConfig) -> Server:
    """Construct a configured low-level MCP :class:`Server`.

    Registers ``list_tools`` and ``call_tool`` handlers driven by
    :data:`TOOL_REGISTRY`. Caller is responsible for running the returned
    server against a transport (see :func:`run_stdio`).

    The :class:`OrchestratorClient` is created lazily on the first
    ``call_tool`` invocation so that ``list_tools`` (the only method the
    smoke test exercises) does not create an ``httpx.AsyncClient`` and
    ``build_server`` itself stays cheap and side-effect-free.
    """
    app: Server = Server("yigthinker-mcp-uipath")

    # D-09: UipathAuth takes (client_id, client_secret, tenant_name,
    # organization, scope). ``scope`` is a SPACE-SEPARATED string, not a
    # list. The internal ``asyncio.Lock`` prevents thundering-herd token
    # refresh (Pitfall 4).
    auth = UipathAuth(
        client_id=config.client_id,
        client_secret=config.client_secret,
        tenant_name=config.tenant_name,
        organization=config.organization,
        scope=config.scope,
    )

    # D-13: OrchestratorClient takes EXACTLY (auth, base_url). The client
    # owns its own httpx.AsyncClient internally — do NOT pass ``http=``.
    state: dict[str, Any] = {"orch": None}

    async def _ensure_client() -> OrchestratorClient:
        if state["orch"] is None:
            state["orch"] = OrchestratorClient(auth=auth, base_url=config.base_url)
        return state["orch"]

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        tools: list[Tool] = []
        for name, (input_model, _handler) in TOOL_REGISTRY.items():
            schema = input_model.model_json_schema()
            description = (input_model.__doc__ or name).strip() or name
            tools.append(
                Tool(
                    name=name,
                    description=description,
                    inputSchema=schema,
                )
            )
        return tools

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        entry = TOOL_REGISTRY.get(name)
        if entry is None:
            payload = {"error": "unknown_tool", "name": name}
            return [TextContent(type="text", text=json.dumps(payload))]

        input_model, handler = entry
        try:
            parsed = input_model.model_validate(arguments or {})
        except ValidationError as exc:
            payload = {
                "error": "invalid_arguments",
                "tool": name,
                "detail": exc.errors(),
            }
            return [TextContent(type="text", text=json.dumps(payload, default=str))]

        try:
            orch = await _ensure_client()
            result = await handler(parsed, orch)
        except Exception as exc:  # noqa: BLE001 - last-resort guard, D-14 belt & suspenders
            logger.exception("Unhandled exception in tool %s", name)
            result = {"error": "internal_error", "tool": name, "detail": str(exc)}

        # D-20 + Finding 6: always a single TextContent block with
        # json.dumps(result). The ``default=str`` fallback protects against
        # stray datetime/Decimal values in handler returns.
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return app


async def run_stdio() -> None:
    """Boot the MCP server on stdio transport.

    Imported lazily so ``python -m yigthinker_mcp_uipath --help`` style probes
    never fail on a missing ``mcp`` SDK.
    """
    from mcp.server.stdio import stdio_server

    config = UipathConfig.from_env()
    app = build_server(config)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


__all__ = ["build_server", "run_stdio"]
