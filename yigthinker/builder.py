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
    pattern_store: "PatternStore | None" = None  # Phase 10 / 10-03
    # Phase 10 / 10-01: expose RPA state store + workflow registry so
    # GatewayServer.start() can assemble an RPAController after build_app
    # has already resolved the LLM provider.
    rpa_state: "Any | None" = None
    workflow_registry: "Any | None" = None


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

    # --- Workflow subsystem ---
    workflow_registry = None
    if gate("workflow", settings=settings):
        try:
            from yigthinker.tools.workflow.registry import WorkflowRegistry
            workflow_registry = WorkflowRegistry()
        except ModuleNotFoundError:
            pass  # jinja2/croniter not installed

    # --- Behavior subsystem (Phase 10 / 10-03) ---
    pattern_store = None
    if gate("behavior", settings=settings):
        from yigthinker.memory.patterns import PatternStore
        pattern_store = PatternStore()

    # --- RPA state (Phase 10 / 10-01) ---
    rpa_state: Any | None = None
    try:
        from yigthinker.gateway.rpa_state import RPAStateStore
        gateway_cfg = settings.get("gateway", {})
        rpa_cfg = gateway_cfg.get("rpa", {})
        db_path_str = rpa_cfg.get("db_path", "~/.yigthinker/rpa/state.db")
        db_path = Path(db_path_str).expanduser()
        rpa_state = RPAStateStore(db_path=db_path)
    except Exception:
        # If RPAStateStore cannot be built, gateway RPA endpoints return 503.
        rpa_state = None

    tools = build_tool_registry(
        pool=pool,
        workflow_registry=workflow_registry,
        pattern_store=pattern_store,
    )

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
        auto_dream = AutoDream(pattern_store=pattern_store)

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

    # --- Phase 10 / BHV-02 (CORR-02): workflow health startup alert provider ---
    if gate("behavior", settings=settings) and workflow_registry is not None:
        try:
            from yigthinker.tools.workflow.workflow_manage import (
                WorkflowManageInput,
                WorkflowManageTool,
            )
        except ModuleNotFoundError:
            pass  # jinja2/croniter not installed -- no workflow tools, no alert
        else:
            _workflow_manage = WorkflowManageTool(registry=workflow_registry)
            _behavior_cfg = settings.get("behavior", {}) or {}
            _thresholds = _behavior_cfg.get("health_check_threshold", {}) or {}

            def _startup_alert_provider() -> str | None:
                """BHV-02: compute workflow health alerts. Returns None on any failure.

                Called once per AgentLoop.run at iteration == 1. Closure captures
                _workflow_manage, _thresholds. Must NEVER raise -- AgentLoop.run wraps
                the call in try/except as a second line of defense, but this function
                is the primary catcher.
                """
                try:
                    result = _workflow_manage._health_check(
                        WorkflowManageInput(action="health_check"),
                    )
                    if result.is_error:
                        return None
                    content = result.content if isinstance(result.content, dict) else {}
                    rows = content.get("workflows", [])
                    problems: list[str] = []
                    alert_on_overdue = _thresholds.get("alert_on_overdue", True)
                    threshold_pct = _thresholds.get("alert_on_failure_rate_pct")
                    for row in rows:
                        if alert_on_overdue and row.get("overdue"):
                            problems.append(
                                f"  * {row.get('name', '?')}: overdue "
                                f"(last_run={row.get('last_run')}, "
                                f"schedule={row.get('schedule')})"
                            )
                        if threshold_pct is not None:
                            rate = row.get("failure_rate_pct")
                            if rate is not None and rate >= threshold_pct:
                                problems.append(
                                    f"  * {row.get('name', '?')}: "
                                    f"{rate:.0f}% failure rate in last 30d "
                                    f"({row.get('failure_count_30d')}/"
                                    f"{row.get('run_count_30d')} runs failed)"
                                )
                    if not problems:
                        return None
                    header = (
                        f"[Workflow Health Alert] "
                        f"{len(problems)} active workflow(s) need attention:"
                    )
                    footer = "Use workflow_manage(action=\"inspect\", ...) for details."
                    return "\n".join([header, *problems, footer])
                except Exception:
                    return None

            agent.set_startup_alert_provider(_startup_alert_provider)

    return AppContext(
        agent_loop=agent,
        pool=pool,
        memory_manager=memory_manager,
        pattern_store=pattern_store,
        rpa_state=rpa_state,
        workflow_registry=workflow_registry,
    )
