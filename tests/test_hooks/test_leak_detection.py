import os
import pytest
from unittest.mock import patch
from yigthinker.hooks.leak_detection import LeakDetector, leak_detection_hook
from yigthinker.types import HookAction, HookEvent, ToolResult


@pytest.fixture(autouse=True)
def reset_detector_singleton():
    """Ensure each test starts with a fresh detector."""
    import yigthinker.hooks.leak_detection as m
    m._detector = None
    yield
    m._detector = None


@pytest.fixture
def detector():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-realkey1234567890"}):
        return LeakDetector()


def test_detector_redacts_exact_env_value(detector):
    content = "The key is sk-ant-api03-realkey1234567890 here"
    redacted, detections = detector.scan(content)
    assert "sk-ant-api03-realkey1234567890" not in redacted
    assert "[REDACTED:ANTHROPIC_API_KEY]" in redacted
    assert "ANTHROPIC_API_KEY" in detections


def test_detector_redacts_openai_pattern(detector):
    content = "Found key: sk-proj-abc123def456ghi789jkl012mno_ABCDEFGHIJ"
    redacted, detections = detector.scan(content)
    assert "sk-proj-" not in redacted
    assert "OPENAI_PROJECT_KEY" in detections[0]


def test_detector_ignores_short_values():
    with patch.dict(os.environ, {"SHORT_KEY": "abc"}):
        d = LeakDetector()
    content = "abc is fine"
    redacted, _ = d.scan(content)
    assert redacted == content  # no redaction for values < 8 chars


def test_detector_allows_clean_content(detector):
    content = "Revenue grew 15% year-over-year"
    redacted, detections = detector.scan(content)
    assert redacted == content
    assert detections == []


def test_detector_longest_first_ordering(monkeypatch):
    """Longer secret values must be redacted first."""
    import yigthinker.hooks.leak_detection as m
    # Manually inject overlapping secrets into a fresh detector
    d = m.LeakDetector()
    d._secrets = {
        "SHORT_SECRET": "secret_abc",
        "LONG_SECRET": "secret_abc_extra_chars",
    }
    redacted, detections = d.scan("token: secret_abc_extra_chars end")
    # Longest should match first
    assert "[REDACTED:LONG_SECRET]" in redacted
    assert "secret_abc" not in redacted  # no partial replacement
    assert detections[0] == "LONG_SECRET"


def test_detector_handles_multiple_secrets():
    """Multiple secrets in one string should all be redacted."""
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "sk-ant-realkey1234567890abcdef",
        "DATABASE_URL": "postgres://user:p@ssw0rd_longenough@host:5432/db",
    }):
        import yigthinker.hooks.leak_detection as m
        d = m._get_detector()
        content = "Anthropic: sk-ant-realkey1234567890abcdef and DB: postgres://user:p@ssw0rd_longenough@host:5432/db"
        redacted, detections = d.scan(content)
        assert "sk-ant-realkey" not in redacted
        assert "p@ssw0rd_longenough" not in redacted
        assert "ANTHROPIC_API_KEY" in detections
        assert "DATABASE_URL" in detections


@pytest.mark.asyncio
async def test_hook_allows_none_result():
    event = HookEvent(
        event_type="PostToolUse",
        session_id="s1",
        transcript_path="",
        tool_name="sql_query",
        tool_result=None,
    )
    hook_result = await leak_detection_hook(event)
    assert hook_result.action == HookAction.ALLOW


@pytest.mark.asyncio
async def test_hook_replaces_result_on_detection():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-realkey12345678901234567890123456"}):
        result = ToolResult(
            tool_use_id="t1",
            content="API key: sk-realkey12345678901234567890123456",
        )
        event = HookEvent(
            event_type="PostToolUse",
            session_id="s1",
            transcript_path="",
            tool_name="sql_query",
            tool_result=result,
        )
        hook_result = await leak_detection_hook(event)
        assert hook_result.action == HookAction.REPLACE_RESULT
        assert "sk-realkey" not in hook_result.replacement


@pytest.mark.asyncio
async def test_hook_allows_clean_result():
    result = ToolResult(tool_use_id="t1", content="All clear")
    event = HookEvent(
        event_type="PostToolUse",
        session_id="s1",
        transcript_path="",
        tool_name="sql_query",
        tool_result=result,
    )
    hook_result = await leak_detection_hook(event)
    assert hook_result.action == HookAction.ALLOW


@pytest.mark.asyncio
async def test_hook_skips_error_results():
    result = ToolResult(tool_use_id="t1", content="error", is_error=True)
    event = HookEvent(
        event_type="PostToolUse",
        session_id="s1",
        transcript_path="",
        tool_name="sql_query",
        tool_result=result,
    )
    hook_result = await leak_detection_hook(event)
    assert hook_result.action == HookAction.ALLOW
