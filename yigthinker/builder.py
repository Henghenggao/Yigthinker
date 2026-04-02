from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yigthinker.agent import AgentLoop
from yigthinker.tools.sql.connection import ConnectionPool


@dataclass
class AppContext:
    """Shared application state built once at startup."""

    agent_loop: AgentLoop
    pool: ConnectionPool


async def build_app(settings: dict[str, Any]) -> AppContext:
    """Build the full application stack. Must be called from async context.

    Replaces the old synchronous _build() from __main__.py.
    MCP loading is awaited directly -- no nested asyncio.run().
    """
    from yigthinker.cli.ask_prompt import ask_user_permission
    from yigthinker.hooks.executor import HookExecutor
    from yigthinker.hooks.registry import HookRegistry
    from yigthinker.mcp.loader import MCPLoader
    from yigthinker.permissions import PermissionSystem
    from yigthinker.providers.factory import provider_from_settings
    from yigthinker.registry_factory import build_tool_registry

    pool = ConnectionPool()
    for name, cfg in settings.get("connections", {}).items():
        pool.add_from_config(name, cfg)

    tools = build_tool_registry(pool=pool)

    mcp_config = Path.cwd() / ".mcp.json"
    if mcp_config.exists():
        try:
            loader = MCPLoader(mcp_json_path=mcp_config, registry=tools)
            await loader.load()
        except ModuleNotFoundError:
            raise RuntimeError(
                "MCP servers configured in .mcp.json but 'mcp' package is not installed. "
                "Run: pip install mcp"
            ) from None

    hooks = HookExecutor(HookRegistry())
    permissions = PermissionSystem(settings.get("permissions", {}))
    provider = provider_from_settings(settings)

    agent_settings = settings.get("agent", {})
    max_iterations = agent_settings.get("max_iterations", 50)
    timeout_seconds = agent_settings.get("timeout_seconds", 300.0)

    agent = AgentLoop(
        provider=provider,
        tools=tools,
        hooks=hooks,
        permissions=permissions,
        ask_fn=ask_user_permission,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
    )
    return AppContext(agent_loop=agent, pool=pool)
