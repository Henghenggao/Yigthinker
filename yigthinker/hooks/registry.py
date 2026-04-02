from __future__ import annotations
from typing import Callable, Awaitable
from yigthinker.types import HookEvent, HookResult

HookFn = Callable[[HookEvent], Awaitable[HookResult]]


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: list[tuple[str, str, HookFn]] = []

    def register(self, event_type: str, matcher: str, fn: HookFn) -> None:
        self._hooks.append((event_type, matcher, fn))

    def get_hooks_for(self, event_type: str, tool_name: str) -> list[HookFn]:
        return [
            fn
            for ev, matcher, fn in self._hooks
            if ev == event_type and self._matches(matcher, tool_name)
        ]

    def hook(self, event_type: str, matcher: str = "*") -> Callable[[HookFn], HookFn]:
        """Decorator: @registry.hook('PreToolUse', matcher='sql_query')"""
        def decorator(fn: HookFn) -> HookFn:
            self.register(event_type, matcher, fn)
            return fn
        return decorator

    def _matches(self, matcher: str, tool_name: str) -> bool:
        if matcher == "*":
            return True
        return tool_name in matcher.split("|")
