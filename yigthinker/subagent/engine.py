from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yigthinker.hooks.executor import HookExecutor
from yigthinker.permissions import PermissionSystem
from yigthinker.providers.base import LLMProvider
from yigthinker.providers.factory import provider_from_settings
from yigthinker.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from yigthinker.agent import AgentLoop

# Tools that must never appear in a child ToolRegistry
_EXCLUDED_TOOLS = frozenset({"spawn_agent", "agent_status", "agent_cancel"})


class SubagentEngine:
    """Factory that creates child AgentLoops with isolated SessionContexts."""

    def __init__(
        self,
        parent_tools: ToolRegistry,
        parent_hooks: HookExecutor,
        parent_permissions: PermissionSystem,
        parent_provider: LLMProvider,
        parent_settings: dict[str, Any],
    ) -> None:
        self._parent_tools = parent_tools
        self._parent_hooks = parent_hooks
        self._parent_permissions = parent_permissions
        self._parent_provider = parent_provider
        self._parent_settings = parent_settings

    def create_child_loop(
        self,
        allowed_tools: list[str] | None = None,
        model: str | None = None,
    ) -> AgentLoop:
        from yigthinker.agent import AgentLoop

        child_registry = self._build_child_registry(allowed_tools)

        if model is not None:
            child_settings = dict(self._parent_settings)
            child_settings["model"] = model
            provider = provider_from_settings(child_settings)
        else:
            provider = self._parent_provider

        spawn_cfg = self._parent_settings.get("spawn_agent", {})
        max_iterations = spawn_cfg.get("max_iterations", 20)
        timeout = spawn_cfg.get("timeout", 120.0)

        return AgentLoop(
            provider=provider,
            tools=child_registry,
            hooks=self._parent_hooks,
            permissions=self._parent_permissions,
            ask_fn=None,
            max_iterations=max_iterations,
            timeout_seconds=timeout,
        )

    def _build_child_registry(
        self,
        allowed_tools: list[str] | None,
    ) -> ToolRegistry:
        child = ToolRegistry()

        if allowed_tools is not None:
            for name in allowed_tools:
                if name in _EXCLUDED_TOOLS:
                    continue
                child.register(self._parent_tools.get(name))
        else:
            for name in self._parent_tools.names():
                if name in _EXCLUDED_TOOLS:
                    continue
                child.register(self._parent_tools.get(name))

        return child
