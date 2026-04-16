"""Unit tests for the base system prompt module."""
from __future__ import annotations


def test_base_prompt_exists_as_string():
    from yigthinker.prompts.base import BASE_SYSTEM_PROMPT
    assert isinstance(BASE_SYSTEM_PROMPT, str)
    assert len(BASE_SYSTEM_PROMPT) > 200, "Base prompt must be substantive"


def test_base_prompt_has_action_first_directive():
    """The base prompt must tell the LLM to DO, not explain."""
    from yigthinker.prompts.base import BASE_SYSTEM_PROMPT
    lowered = BASE_SYSTEM_PROMPT.lower()
    # Must contain action-first language
    assert "default to action" in lowered or "action-first" in lowered, (
        "Base prompt must explicitly direct LLM to action-first behavior"
    )
    # Must mention artifact production
    assert "artifact" in lowered, (
        "Base prompt must direct LLM to produce artifacts"
    )


def test_base_prompt_mentions_tool_families():
    """The prompt must name the core tool families so LLM knows what's available."""
    from yigthinker.prompts.base import BASE_SYSTEM_PROMPT
    assert "df_load" in BASE_SYSTEM_PROMPT
    assert "report_generate" in BASE_SYSTEM_PROMPT
    assert "artifact_write" in BASE_SYSTEM_PROMPT


def test_base_prompt_mentions_finance_context():
    """The prompt positions Yigcore as a finance agent."""
    from yigthinker.prompts.base import BASE_SYSTEM_PROMPT
    lowered = BASE_SYSTEM_PROMPT.lower()
    assert "finance" in lowered or "financial" in lowered or "财务" in BASE_SYSTEM_PROMPT


def test_base_prompt_stays_under_size_budget():
    """The prompt docstring promises 'under 1000 tokens'. ~4 chars/token
    approximation => 4000 chars is a conservative upper bound."""
    from yigthinker.prompts.base import BASE_SYSTEM_PROMPT
    assert len(BASE_SYSTEM_PROMPT) < 4000, (
        f"Base prompt has grown to {len(BASE_SYSTEM_PROMPT)} chars "
        f"(>4000). Tighten it or update the size budget."
    )
