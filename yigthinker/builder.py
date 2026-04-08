from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from yigthinker.agent import AgentLoop
from yigthinker.tools.sql.connection import ConnectionPool

_SENTINEL = object()


@dataclass
class AppContext:
    """Shared application state built once at startup."""

    agent_loop: AgentLoop
    pool: ConnectionPool
    memory_manager: "MemoryManager | None" = None


async def build_app(
    settings: dict[str, Any],
    ask_fn: Callable | None = _SENTINEL,
) -> AppContext:
    """Build the full application stack. Must be called from async context.

    Replaces the old synchronous _build() from __main__.py.
    MCP loading is awaited directly -- no nested asyncio.run().

    Parameters
    ----------
    settings : dict
        Merged settings from load_settings().
    ask_fn : Callable | None
        Permission prompt function.  Default (sentinel) lazily imports
        the CLI prompt.  Pass ``None`` for daemon/gateway mode where
        stdin is unavailable.
    """
    from yigthinker.gates import gate
    from yigthinker.hooks.executor import HookExecutor
    from yigthinker.hooks.registry import HookRegistry
    from yigthinker.mcp.loader import MCPLoader
    from yigthinker.memory.auto_dream import AutoDream
    from yigthinker.memory.compact import CompactConfig, SmartCompact
    from yigthinker.memory.session_memory import MemoryManager
    from yigthinker.permissions import PermissionSystem
    from yigthinker.providers.factory import provider_from_settings
    from yigthinker.registry_factory import build_tool_registry
    from yigthinker.types import HookEvent, HookResult

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

    hook_registry = HookRegistry()
    hooks = HookExecutor(hook_registry)
    permissions = PermissionSystem(settings.get("permissions", {}))
    provider = provider_from_settings(settings)

    if ask_fn is _SENTINEL:
        from yigthinker.cli.ask_prompt import ask_user_permission
        resolved_ask_fn = ask_user_permission
    else:
        resolved_ask_fn = ask_fn

    agent_settings = settings.get("agent", {})
    max_iterations = agent_settings.get("max_iterations", 50)
    timeout_seconds = agent_settings.get("timeout_seconds", 300.0)

    agent = AgentLoop(
        provider=provider,
        tools=tools,
        hooks=hooks,
        permissions=permissions,
        ask_fn=resolved_ask_fn,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
    )

    # --- Spawn agent wiring ---
    spawn_tool = tools.get("spawn_agent")
    if hasattr(spawn_tool, "set_parent_components"):
        spawn_tool.set_parent_components(
            tools=tools,
            hooks=hooks,
            permissions=permissions,
            provider=provider,
        )

    # --- Memory subsystem ---
    memory_manager: MemoryManager | None = None

    if gate("session_memory", settings=settings):
        memory_cfg = settings.get("memory", {})
        memory_manager = MemoryManager(
            extract_frequency=memory_cfg.get("extract_frequency", 5),
            project_dir=Path.cwd(),
        )
        agent.set_memory_manager(memory_manager)

        compact = SmartCompact(CompactConfig())
        agent.set_compact(compact)

    if gate("auto_dream", settings=settings) and memory_manager is not None:
        auto_dream = AutoDream()

        async def dream_hook(event: HookEvent) -> HookResult:
            if auto_dream.should_run(event.session_id):
                asyncio.create_task(
                    auto_dream.run_background(
                        memory_manager.global_memory_path(),
                        event.session_id,
                        provider,
                    )
                )
            return HookResult.ALLOW

        hook_registry.register("SessionEnd", "*", dream_hook)

    return AppContext(agent_loop=agent, pool=pool, memory_manager=memory_manager)
