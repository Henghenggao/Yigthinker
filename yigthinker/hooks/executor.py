from __future__ import annotations
from yigthinker.types import HookEvent, HookResult, HookAction
from yigthinker.hooks.registry import HookRegistry


class HookExecutor:
    def __init__(self, registry: HookRegistry) -> None:
        self._registry = registry

    async def run(self, event: HookEvent) -> HookResult:
        """Run all matching hooks. Return on first BLOCK; accumulate WARNs."""
        hooks = self._registry.get_hooks_for(event.event_type, event.tool_name)
        last = HookResult.ALLOW
        for hook_fn in hooks:
            result = await hook_fn(event)
            if result.action == HookAction.BLOCK:
                return result
            if result.action == HookAction.WARN:
                last = result
        return last
