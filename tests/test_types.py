from yigthinker.types import (
    ToolResult, ToolUse, HookAction, HookResult, HookEvent, Message, LLMResponse
)

def test_tool_result_defaults():
    r = ToolResult(tool_use_id="id1", content="ok")
    assert r.is_error is False

def test_hook_result_allow_singleton():
    r = HookResult.ALLOW
    assert r.action == HookAction.ALLOW
    assert r.message == ""

def test_hook_result_block():
    r = HookResult.block("no access")
    assert r.action == HookAction.BLOCK
    assert r.message == "no access"

def test_hook_result_warn():
    r = HookResult.warn("be careful")
    assert r.action == HookAction.WARN

def test_hook_event_defaults():
    e = HookEvent(event_type="PreToolUse", session_id="s1", transcript_path="/tmp/t.jsonl")
    assert e.tool_name == ""
    assert e.tool_result is None

def test_llm_response_defaults():
    r = LLMResponse(stop_reason="end_turn")
    assert r.text == ""
    assert r.tool_uses == []
