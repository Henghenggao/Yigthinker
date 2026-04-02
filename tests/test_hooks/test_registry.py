import pytest
from yigthinker.hooks.registry import HookRegistry
from yigthinker.types import HookEvent, HookResult


async def allow_fn(event: HookEvent) -> HookResult:
    return HookResult.ALLOW


def make_event(tool_name: str = "sql_query") -> HookEvent:
    return HookEvent(event_type="PreToolUse", session_id="s1", transcript_path="", tool_name=tool_name)


def test_register_and_get_hooks():
    reg = HookRegistry()
    reg.register("PreToolUse", "sql_query", allow_fn)
    hooks = reg.get_hooks_for("PreToolUse", "sql_query")
    assert allow_fn in hooks


def test_wildcard_matches_all():
    reg = HookRegistry()
    reg.register("PreToolUse", "*", allow_fn)
    assert allow_fn in reg.get_hooks_for("PreToolUse", "anything")
    assert allow_fn in reg.get_hooks_for("PreToolUse", "sql_query")


def test_pipe_separated_matcher():
    reg = HookRegistry()
    reg.register("PreToolUse", "sql_query|df_transform", allow_fn)
    assert allow_fn in reg.get_hooks_for("PreToolUse", "sql_query")
    assert allow_fn in reg.get_hooks_for("PreToolUse", "df_transform")
    assert allow_fn not in reg.get_hooks_for("PreToolUse", "chart_create")


def test_wrong_event_type_not_returned():
    reg = HookRegistry()
    reg.register("PostToolUse", "*", allow_fn)
    assert allow_fn not in reg.get_hooks_for("PreToolUse", "sql_query")


def test_decorator_syntax():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="echo")
    async def my_hook(event: HookEvent) -> HookResult:
        return HookResult.ALLOW

    assert my_hook in reg.get_hooks_for("PreToolUse", "echo")
