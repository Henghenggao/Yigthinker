from yigthinker.types import (
    ToolResult, HookAction, HookResult, HookEvent, LLMResponse, ThinkingConfig
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


def test_thinking_config_defaults():
    tc = ThinkingConfig()
    assert tc.enabled is False
    assert tc.budget_tokens == 10000


def test_thinking_config_enabled():
    tc = ThinkingConfig(enabled=True, budget_tokens=5000)
    assert tc.enabled is True
    assert tc.budget_tokens == 5000


def test_llm_response_has_thinking_blocks():
    r = LLMResponse(stop_reason="end_turn", text="hi", thinking_blocks=[{"type": "thinking", "thinking": "I reasoned"}])
    assert len(r.thinking_blocks) == 1
    assert r.thinking_blocks[0]["thinking"] == "I reasoned"


def test_llm_response_thinking_blocks_default_empty():
    r = LLMResponse(stop_reason="end_turn", text="hi")
    assert r.thinking_blocks == []
