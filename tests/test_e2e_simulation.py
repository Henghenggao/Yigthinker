"""
End-to-end simulation: new user first run.

Simulates a complete session without a real LLM API key:
  1. User runs setup (provider=Anthropic, model=Sonnet, key saved to tmp dir)
  2. Settings loader picks up the saved key and injects it into environment
  3. Agent loop runs with a mock LLM provider (real tools, fake LLM)
  4. LLM "decides" to load a CSV, profile it, then reply with summary

All tools execute for real (pandas, SQLite etc.) — only the LLM is mocked.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.registry_factory import build_tool_registry
from yigthinker.session import SessionContext
from yigthinker.settings import has_api_key, load_settings
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.types import LLMResponse, ToolUse


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_settings(directory: Path, data: dict) -> None:
    path = directory / ".yigthinker" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_csv(tmp_path: Path) -> Path:
    """Write a small financial CSV for the agent to load."""
    csv_path = tmp_path / "revenue.csv"
    df = pd.DataFrame({
        "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "revenue": [120_000, 135_000, 142_000, 128_000, 155_000, 163_000],
        "costs":   [ 80_000,  88_000,  91_000,  85_000,  99_000, 104_000],
    })
    df["profit"] = df["revenue"] - df["costs"]
    df.to_csv(csv_path, index=False)
    return csv_path


# ── Step 1: Setup wizard saves key + model ─────────────────────────────────────

def test_setup_wizard_saves_settings(tmp_path):
    """
    Simulate: user runs `yigthinker setup`, picks Anthropic + Sonnet 4.5,
    enters a fake API key. Key and model are saved to settings.json.
    """
    settings_path = tmp_path / ".yigthinker" / "settings.json"
    settings_path.parent.mkdir(parents=True)

    # Fake key the "user" pastes in
    fake_key = "sk-ant-test-" + "x" * 32

    from yigthinker.presence.cli.setup_wizard import _save_user_settings

    # Directly call the save function as if setup wizard completed
    with patch("yigthinker.presence.cli.setup_wizard._user_settings_path", return_value=settings_path):
        _save_user_settings({
            "model": "claude-sonnet-4-5",
            "anthropic_api_key": fake_key,
        })

    saved = json.loads(settings_path.read_text())
    assert saved["model"] == "claude-sonnet-4-5"
    assert saved["anthropic_api_key"] == fake_key
    print(f"\n[setup] Saved to {settings_path}")
    print(f"[setup] model={saved['model']}, key={fake_key[:16]}...")


# ── Step 2: Settings loader promotes key into environment ──────────────────────

def test_settings_loader_injects_key(tmp_path):
    """
    Simulate: on next launch, load_settings() reads the saved key and sets
    ANTHROPIC_API_KEY in os.environ so the provider can authenticate.
    """
    fake_key = "sk-ant-test-" + "y" * 32
    _write_settings(tmp_path, {
        "model": "claude-sonnet-4-5",
        "anthropic_api_key": fake_key,
    })

    # Remove key from environment to start clean
    os.environ.pop("ANTHROPIC_API_KEY", None)

    with patch("yigthinker.settings.Path") as mock_path_cls:
        # Forward Path(...) calls to the real Path so managed_path works normally
        mock_path_cls.side_effect = lambda *a, **kw: Path(*a, **kw)
        # Patch Path.home() to return our tmp dir
        mock_path_cls.home.return_value = tmp_path
        settings = load_settings(project_dir=tmp_path / "nonexistent")

    # Key should now be in environment
    assert os.environ.get("ANTHROPIC_API_KEY") == fake_key
    assert settings["model"] == "claude-sonnet-4-5"
    assert has_api_key(settings)
    print(f"\n[settings] ANTHROPIC_API_KEY injected: {fake_key[:16]}...")

    # Cleanup
    os.environ.pop("ANTHROPIC_API_KEY", None)


# ── Step 3: Full agent session (real tools, mock LLM) ─────────────────────────

@pytest.mark.asyncio
async def test_full_user_session_load_and_profile(tmp_path):
    """
    Simulate a complete user session:

      User: "Load revenue.csv and show me a profile of the data"

      LLM turn 1: calls df_load(path=..., var_name="revenue")
      LLM turn 2: calls df_profile(var_name="revenue")
      LLM turn 3: end_turn with a summary text

    All three tools execute with real pandas logic.
    The result is printed to stdout to show what a real user would see.
    """
    csv_path = _make_csv(tmp_path)

    # Build the real tool registry (all 21 tools, no connections needed)
    pool = ConnectionPool()
    tools = build_tool_registry(pool=pool)
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({
        "allow": ["df_load", "df_profile", "df_transform", "schema_inspect"],
    })

    # Mock LLM: 3 turns — load CSV, profile it, then summarise
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        # Turn 1: load the CSV
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id="t1",
                name="df_load",
                input={"source": str(csv_path), "var_name": "revenue"},
            )],
        ),
        # Turn 2: profile the loaded DataFrame
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id="t2",
                name="df_profile",
                input={"var_name": "revenue"},
            )],
        ),
        # Turn 3: end with a natural language summary
        LLMResponse(
            stop_reason="end_turn",
            text=(
                "I loaded revenue.csv (6 rows x 4 columns). "
                "Revenue ranges from $120,000 to $163,000. "
                "Average monthly profit is $51,833."
            ),
            tool_uses=[],
        ),
    ])

    agent = AgentLoop(
        provider=mock_llm,
        tools=tools,
        hooks=hooks,
        permissions=perms,
    )
    ctx = SessionContext(settings={"model": "claude-sonnet-4-5", "workspace_dir": str(tmp_path)})

    # ── Run the session ──
    print("\n" + "=" * 60)
    print("USER: Load revenue.csv and show me a profile of the data")
    print("=" * 60)

    result = await agent.run(
        "Load revenue.csv and show me a profile of the data",
        ctx,
    )

    print(f"\nAGENT: {result}\n")

    # ── Assertions ──

    # The DataFrame is in VarRegistry after df_load
    assert "revenue" in ctx.vars
    df = ctx.vars.get("revenue")
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (6, 4)
    assert list(df.columns) == ["month", "revenue", "costs", "profit"]

    # Profit values are correct
    assert df["profit"].sum() == (
        (120_000 - 80_000) + (135_000 - 88_000) + (142_000 - 91_000) +
        (128_000 - 85_000) + (155_000 - 99_000) + (163_000 - 104_000)
    )

    # Agent replied with a summary
    assert "revenue" in result.lower()
    assert "profit" in result.lower()

    # LLM was called exactly 3 times (load → profile → summarise)
    assert mock_llm.chat.call_count == 3

    # Conversation history is intact
    assert len(ctx.messages) > 0

    print("[PASS] DataFrame loaded correctly")
    print(f"[PASS] Shape: {df.shape}")
    print(f"[PASS] Total profit: ${df['profit'].sum():,.0f}")
    print(f"[PASS] LLM turns: {mock_llm.chat.call_count}")
    print(f"[PASS] Messages in history: {len(ctx.messages)}")


# ── Step 4: Sandbox security — confirm exploit is blocked ─────────────────────

@pytest.mark.asyncio
async def test_sandbox_blocks_dunder_escape(tmp_path):
    """
    Simulate: a malicious prompt tries to escape the df_transform sandbox
    via __globals__ object introspection. The AST pre-pass should block it.
    """
    pool = ConnectionPool()
    tools = build_tool_registry(pool=pool)
    hooks = HookExecutor(HookRegistry())
    perms = PermissionSystem({"allow": ["df_load", "df_transform"]})

    csv_path = _make_csv(tmp_path)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=[
        # Load CSV first
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id="t1",
                name="df_load",
                input={"source": str(csv_path), "var_name": "revenue"},
            )],
        ),
        # Then try to escape sandbox via __globals__
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id="t2",
                name="df_transform",
                input={
                    "input_var": "revenue",
                    "code": "g = pd.read_csv.__globals__; result = df",
                },
            )],
        ),
        LLMResponse(stop_reason="end_turn", text="Done", tool_uses=[]),
    ])

    agent = AgentLoop(
        provider=mock_llm,
        tools=tools,
        hooks=hooks,
        permissions=perms,
    )
    ctx = SessionContext()
    await agent.run("transform the data", ctx)

    # The transform result in messages should contain rejection, not success
    # Check that the tool result for the malicious call was an error
    tool_results = [
        msg for msg in ctx.messages
        if isinstance(msg.content, list)
        and any(b.get("type") == "tool_result" for b in msg.content if isinstance(b, dict))
    ]
    assert tool_results, "Expected tool result messages in history"

    # Find the df_transform result
    for msg in tool_results:
        for block in msg.content:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") == "t2":
                assert block["is_error"] is True
                assert "__globals__" in block["content"] or "blocked" in block["content"].lower()
                print(f"\n[SECURITY] Sandbox correctly blocked: {block['content']}")
                return

    pytest.fail("Did not find the df_transform tool result in message history")
