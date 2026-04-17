"""Unit tests for RPAController — mocked LLMProvider, WorkflowRegistry, RPAStateStore."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from yigthinker.presence.gateway.rpa_controller import (
    RPAController,
    MAX_ATTEMPTS_24H,
    MAX_LLM_CALLS_DAY,
)
from yigthinker.presence.gateway.rpa_state import RPAStateStore


def _fake_payload(**overrides: Any) -> dict:
    p = {
        "callback_id": "cb-test-1",
        "workflow_name": "wf-a",
        "version": 1,
        "checkpoint_id": "ckpt-1",
        "attempt_number": 1,
        "error_type": "ConnectionError",
        "error_message": "Connection refused",
        "traceback": "Traceback (most recent call last):\n...",
        "step_context": {"name": "step_1", "inputs_summary": {}},
    }
    p.update(overrides)
    return p


@pytest.fixture
def controller(tmp_path: Path):
    state = RPAStateStore(db_path=tmp_path / "state.db")
    registry = MagicMock()
    registry.load_index.return_value = {"workflows": {}}
    provider = MagicMock()
    provider.chat = AsyncMock()
    c = RPAController(state=state, registry=registry, provider=provider)
    yield c
    state.close()


# ───────────── Plan 10-02 coverage: real extraction LLM call + dedup + breaker ─────────────

async def test_extraction_calls_provider_and_returns_decision(controller: RPAController) -> None:
    """Plan 10-02: extraction path calls provider.chat exactly once and parses the JSON response."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "fix_applied", "instruction": "Retry after brief delay.", "retry_delay_s": 5, "reason": "transient_network"}',
        tool_uses=[],
    )
    decision = await controller.handle_callback(_fake_payload())
    assert decision["action"] == "fix_applied"
    assert decision["retry_delay_s"] == 5
    assert decision["reason"] == "transient_network"
    controller._provider.chat.assert_called_once()


async def test_callback_dedup_returns_cached(controller: RPAController) -> None:
    """Duplicate callback_id returns the same decision without re-processing."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "Unknown error.", "reason": "unclassified"}',
        tool_uses=[],
    )
    d1 = await controller.handle_callback(_fake_payload(callback_id="dup-1"))
    d2 = await controller.handle_callback(_fake_payload(callback_id="dup-1"))
    assert d1 == d2
    # Provider called exactly once — second call hits the dedup cache.
    assert controller._provider.chat.call_count == 1


async def test_circuit_breaker_checkpoint_attempts(controller: RPAController) -> None:
    """4th attempt on same (wf, ckpt) within 24h → escalate + reason='breaker_exceeded'."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "x", "reason": "programming_error"}',
        tool_uses=[],
    )
    for i in range(MAX_ATTEMPTS_24H):
        d = await controller.handle_callback(_fake_payload(callback_id=f"cb-{i}"))
        # First 3 hit the real extraction path (mocked) → escalate/programming_error
        assert d["action"] == "escalate"
    # 4th attempt trips breaker BEFORE calling LLM
    d4 = await controller.handle_callback(_fake_payload(callback_id="cb-4"))
    assert d4["action"] == "escalate"
    assert d4["reason"] == "breaker_exceeded"


async def test_circuit_breaker_llm_cap(controller: RPAController) -> None:
    """11th LLM call for same workflow in UTC day → escalate with reason='breaker_exceeded'."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "x", "reason": "programming_error"}',
        tool_uses=[],
    )
    # Each handle_callback increments llm_calls counter (D-07)
    for i in range(MAX_LLM_CALLS_DAY):
        await controller.handle_callback(_fake_payload(
            callback_id=f"cb-llm-{i}", checkpoint_id=f"ckpt-{i}",  # avoid breaker on attempts
        ))
    d = await controller.handle_callback(_fake_payload(
        callback_id="cb-llm-11", checkpoint_id="ckpt-new",
    ))
    assert d["action"] == "escalate"
    assert d["reason"] == "breaker_exceeded"


# ───────────── Plan 10-01 coverage: handle_report full ─────────────

async def test_report_writes_registry(controller: RPAController) -> None:
    """handle_report calls save_index with the partial patch shape."""
    controller._registry.load_index.return_value = {
        "workflows": {
            "wf-a": {
                "status": "active",
                "run_count_30d": 0,
                "failure_count_30d": 0,
                "last_run": None,
            }
        }
    }
    result = await controller.handle_report({
        "workflow_name": "wf-a",
        "version": 1,
        "run_id": "run-1",
        "started_at": "2026-04-10T10:00:00+00:00",
        "finished_at": "2026-04-10T10:05:00+00:00",
        "status": "success",
        "error_summary": None,
    })
    assert result == {"ok": True}
    controller._registry.save_index.assert_called_once()
    patch = controller._registry.save_index.call_args[0][0]
    assert "workflows" in patch
    assert "wf-a" in patch["workflows"]
    entry = patch["workflows"]["wf-a"]
    assert entry["last_run"] == "2026-04-10T10:05:00+00:00"
    assert entry["last_run_status"] == "success"
    assert entry["run_count_30d"] == 1
    assert entry["failure_count_30d"] == 0


async def test_report_failure_increments_failure_counter(controller: RPAController) -> None:
    controller._registry.load_index.return_value = {
        "workflows": {
            "wf-a": {
                "status": "active",
                "run_count_30d": 5,
                "failure_count_30d": 1,
                "last_run": "2026-04-09T10:00:00+00:00",
            }
        }
    }
    await controller.handle_report({
        "workflow_name": "wf-a",
        "version": 1,
        "run_id": "run-2",
        "started_at": "2026-04-10T10:00:00+00:00",
        "finished_at": "2026-04-10T10:05:00+00:00",
        "status": "failure",
        "error_summary": "Boom",
    })
    patch = controller._registry.save_index.call_args[0][0]
    entry = patch["workflows"]["wf-a"]
    assert entry["run_count_30d"] == 6
    assert entry["failure_count_30d"] == 2


async def test_report_no_llm_call(controller: RPAController) -> None:
    """handle_report NEVER calls the LLM provider."""
    controller._registry.load_index.return_value = {
        "workflows": {
            "wf-a": {
                "status": "active",
                "run_count_30d": 0,
                "failure_count_30d": 0,
                "last_run": None,
            }
        }
    }
    await controller.handle_report({
        "workflow_name": "wf-a",
        "version": 1,
        "run_id": "run-1",
        "started_at": "2026-04-10T10:00:00+00:00",
        "finished_at": "2026-04-10T10:05:00+00:00",
        "status": "success",
        "error_summary": None,
    })
    controller._provider.chat.assert_not_called()


async def test_lazy_30d_rollover(controller: RPAController) -> None:
    """When existing last_run is > 30 days old, counters reset to 1 (D-10)."""
    controller._registry.load_index.return_value = {
        "workflows": {
            "wf-a": {
                "status": "active",
                "run_count_30d": 50,
                "failure_count_30d": 10,
                "last_run": "2026-03-01T10:00:00+00:00",
            }
        }
    }
    await controller.handle_report({
        "workflow_name": "wf-a",
        "version": 1,
        "run_id": "run-new",
        "started_at": "2026-04-10T10:00:00+00:00",
        "finished_at": "2026-04-10T10:05:00+00:00",
        "status": "success",
        "error_summary": None,
    })
    patch = controller._registry.save_index.call_args[0][0]
    entry = patch["workflows"]["wf-a"]
    # Window rolled over → counts reset based on this write
    assert entry["run_count_30d"] == 1
    assert entry["failure_count_30d"] == 0


# ────── Plan 10-02: extraction-only LLM callback ──────

async def test_extraction_no_tools(controller: RPAController) -> None:
    """D-05: provider.chat is called with tools=[] and system=EXTRACTION_SYSTEM."""
    from yigthinker.types import LLMResponse
    from yigthinker.presence.gateway.extraction_prompt import EXTRACTION_SYSTEM
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "Unknown error.", "reason": "unclassified"}',
        tool_uses=[],
    )
    await controller.handle_callback(_fake_payload(callback_id="cb-no-tools"))

    controller._provider.chat.assert_called_once()
    call = controller._provider.chat.call_args
    # tools=[] required (either positional or kwarg)
    kwargs = call.kwargs
    args = call.args
    tools_arg = kwargs.get("tools") if "tools" in kwargs else (args[1] if len(args) > 1 else None)
    assert tools_arg == [], f"Expected tools=[], got {tools_arg!r}"
    # system prompt must be EXTRACTION_SYSTEM
    system_arg = kwargs.get("system") if "system" in kwargs else (args[2] if len(args) > 2 else None)
    assert system_arg == EXTRACTION_SYSTEM


async def test_extraction_parse_fallback_malformed_json(controller: RPAController) -> None:
    """CORR-04b: unparseable LLM JSON → silent escalate with reason='extraction_failed'. No heuristic fallback."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="This is not JSON at all. The error looks like a network issue maybe.",
        tool_uses=[],
    )
    decision = await controller.handle_callback(_fake_payload(callback_id="cb-malformed"))
    assert decision["action"] == "escalate"
    assert decision["reason"] == "extraction_failed"
    # NO keyword heuristic: even though the text mentioned "network", we escalate
    assert decision.get("retry_delay_s") is None


async def test_extraction_parse_fallback_markdown_fenced(controller: RPAController) -> None:
    """Layered fallback: strip ```json fences and still parse successfully."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='```json\n{"action": "skip", "instruction": "Optional file missing.", "reason": "missing_optional_file"}\n```',
        tool_uses=[],
    )
    decision = await controller.handle_callback(_fake_payload(callback_id="cb-fenced"))
    assert decision["action"] == "skip"
    assert decision["reason"] == "missing_optional_file"


async def test_extraction_unknown_action_escalates(controller: RPAController) -> None:
    """CORR-04b: LLM returns valid JSON but with an unknown 'action' value → escalate."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "try_harder", "instruction": "Just retry forever", "reason": "optimism"}',
        tool_uses=[],
    )
    decision = await controller.handle_callback(_fake_payload(callback_id="cb-unknown-action"))
    assert decision["action"] == "escalate"
    assert decision["reason"] == "extraction_failed"


async def test_extraction_empty_text_escalates(controller: RPAController) -> None:
    """Empty LLM response → escalate with reason='extraction_failed'."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text="",
        tool_uses=[],
    )
    decision = await controller.handle_callback(_fake_payload(callback_id="cb-empty"))
    assert decision["action"] == "escalate"
    assert decision["reason"] == "extraction_failed"


async def test_extraction_truncates_long_traceback(controller: RPAController) -> None:
    """D-05 budget: traceback in user message is capped at 2000 chars to keep extraction prompt small."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "x", "reason": "programming_error"}',
        tool_uses=[],
    )
    big_tb = "TracebackLineX\n" * 500   # ~7000 chars
    await controller.handle_callback(_fake_payload(callback_id="cb-big-tb", traceback=big_tb))
    call = controller._provider.chat.call_args
    kwargs = call.kwargs
    args = call.args
    messages_arg = kwargs.get("messages") if "messages" in kwargs else (args[0] if args else None)
    assert messages_arg is not None and len(messages_arg) == 1
    user_content = messages_arg[0].content if hasattr(messages_arg[0], "content") else messages_arg[0]["content"]
    assert len(user_content) < 5000, f"User message should be truncated, got {len(user_content)} chars"


async def test_breaker_prevents_llm_call(controller: RPAController) -> None:
    """Regression: when breaker trips, provider.chat is NOT called (10-01 behavior preserved in 10-02)."""
    from yigthinker.types import LLMResponse
    controller._provider.chat.return_value = LLMResponse(
        stop_reason="end_turn",
        text='{"action": "escalate", "instruction": "x", "reason": "programming_error"}',
        tool_uses=[],
    )
    # Fire MAX_ATTEMPTS_24H attempts on the same checkpoint first
    for i in range(MAX_ATTEMPTS_24H):
        await controller.handle_callback(_fake_payload(callback_id=f"cb-pre-{i}"))
    precall_count = controller._provider.chat.call_count
    # 4th attempt must trip breaker and NOT call LLM
    d = await controller.handle_callback(_fake_payload(callback_id="cb-tripped"))
    assert d["reason"] == "breaker_exceeded"
    assert controller._provider.chat.call_count == precall_count, (
        "provider.chat must not be called when breaker trips"
    )
