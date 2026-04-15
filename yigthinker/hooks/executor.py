from __future__ import annotations
from yigthinker.types import HookAction, HookAggregateResult, HookEvent
from yigthinker.hooks.registry import HookRegistry


class HookExecutor:
    def __init__(self, registry: HookRegistry, capabilities: dict[str, bool] | None = None) -> None:
        self._registry = registry
        self._capabilities = capabilities or {}

    async def run(self, event: HookEvent) -> HookAggregateResult:
        """Run all matching hooks. Return aggregated result."""
        hooks = self._registry.get_hooks_for(event.event_type, event.tool_name)
        agg = HookAggregateResult()

        for hook_fn in hooks:
            result = await hook_fn(event)

            if result.action == HookAction.BLOCK:
                agg.action = HookAction.BLOCK
                agg.message = result.message
                return agg  # short-circuit

            if result.action == HookAction.WARN:
                if agg.action != HookAction.BLOCK:
                    agg.action = HookAction.WARN
                    agg.message = result.message

            if result.action == HookAction.INJECT_SYSTEM:
                if self._capabilities.get("inject_system", True):
                    agg.injections.append(result.message)

            if result.action == HookAction.SUPPRESS_OUTPUT:
                if self._capabilities.get("suppress_output", True):
                    agg.suppress = True

            if result.action == HookAction.REPLACE_RESULT:
                if self._capabilities.get("replace_result", True):
                    agg.replacement = result.replacement

        return agg
