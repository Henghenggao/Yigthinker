from __future__ import annotations

from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.types import HookAction, HookEvent, HookResult


def test_inject_system_creates_correct_action():
    result = HookResult.inject_system("RBAC: EMEA only")
    assert result.action == HookAction.INJECT_SYSTEM
    assert result.message == "RBAC: EMEA only"


def test_suppress_creates_correct_action():
    result = HookResult.suppress()
    assert result.action == HookAction.SUPPRESS_OUTPUT


def test_replace_creates_correct_action():
    result = HookResult.replace({"masked": True})
    assert result.action == HookAction.REPLACE_RESULT
    assert result.replacement == {"masked": True}

def make_event(tool_name: str = "sql_query") -> HookEvent:
    return HookEvent(event_type="PreToolUse", session_id="s1", transcript_path="", tool_name=tool_name)


async def test_executor_aggregates_injections():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook1(event: HookEvent) -> HookResult:
        return HookResult.inject_system("Only EMEA data")

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook2(event: HookEvent) -> HookResult:
        return HookResult.inject_system("User is read-only")

    executor = HookExecutor(reg)
    agg = await executor.run(make_event())
    assert agg.action == HookAction.ALLOW
    assert agg.injections == ["Only EMEA data", "User is read-only"]


async def test_executor_block_takes_priority():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook1(event: HookEvent) -> HookResult:
        return HookResult.inject_system("context")

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook2(event: HookEvent) -> HookResult:
        return HookResult.block("forbidden")

    executor = HookExecutor(reg)
    agg = await executor.run(make_event())
    assert agg.action == HookAction.BLOCK
    assert agg.message == "forbidden"


async def test_executor_suppress_overrides_replace():
    reg = HookRegistry()

    @reg.hook("PostToolUse", matcher="sql_query")
    async def hook1(event: HookEvent) -> HookResult:
        return HookResult.replace({"masked": True})

    @reg.hook("PostToolUse", matcher="sql_query")
    async def hook2(event: HookEvent) -> HookResult:
        return HookResult.suppress()

    executor = HookExecutor(reg)
    event = HookEvent(event_type="PostToolUse", session_id="s1", transcript_path="", tool_name="sql_query")
    agg = await executor.run(event)
    assert agg.suppress is True


async def test_executor_replace_last_wins():
    reg = HookRegistry()

    @reg.hook("PostToolUse", matcher="sql_query")
    async def hook1(event: HookEvent) -> HookResult:
        return HookResult.replace({"version": 1})

    @reg.hook("PostToolUse", matcher="sql_query")
    async def hook2(event: HookEvent) -> HookResult:
        return HookResult.replace({"version": 2})

    executor = HookExecutor(reg)
    event = HookEvent(event_type="PostToolUse", session_id="s1", transcript_path="", tool_name="sql_query")
    agg = await executor.run(event)
    assert agg.replacement == {"version": 2}


async def test_capability_gate_disables_inject():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook1(event: HookEvent) -> HookResult:
        return HookResult.inject_system("should be ignored")

    executor = HookExecutor(reg, capabilities={"inject_system": False})
    agg = await executor.run(make_event())
    assert agg.injections == []
