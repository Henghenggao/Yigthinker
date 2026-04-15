from yigthinker.hooks.registry import HookRegistry
from yigthinker.hooks.executor import HookExecutor
from yigthinker.types import HookEvent, HookResult, HookAction


def make_event() -> HookEvent:
    return HookEvent(event_type="PreToolUse", session_id="s1", transcript_path="", tool_name="sql_query")


async def test_allow_hook_returns_allow():
    reg = HookRegistry()

    @reg.hook("PreToolUse", matcher="sql_query")
    async def hook(event: HookEvent) -> HookResult:
        return HookResult.ALLOW

    executor = HookExecutor(reg)
    result = await executor.run(make_event())
    assert result.action == HookAction.ALLOW


async def test_block_hook_stops_execution():
    reg = HookRegistry()
    ran_second = []

    @reg.hook("PreToolUse", matcher="sql_query")
    async def blocker(event: HookEvent) -> HookResult:
        return HookResult.block("no access")

    @reg.hook("PreToolUse", matcher="sql_query")
    async def second(event: HookEvent) -> HookResult:
        ran_second.append(True)
        return HookResult.ALLOW

    executor = HookExecutor(reg)
    result = await executor.run(make_event())
    assert result.action == HookAction.BLOCK
    assert result.message == "no access"
    assert ran_second == []  # never ran


async def test_no_hooks_returns_allow():
    reg = HookRegistry()
    executor = HookExecutor(reg)
    result = await executor.run(make_event())
    assert result.action == HookAction.ALLOW
