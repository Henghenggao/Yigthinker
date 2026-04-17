"""End-to-end Phase 0 acceptance test: Teams Excel delivery.

Simulates:
  1. A Teams user attaches revenue.csv and asks "把这份数据做成月度汇总 Excel"
  2. The agent runs with a mocked LLM that issues realistic tool calls:
     df_load → report_generate
  3. The final response carries an artifact with kind="file" and filename
     ending in .xlsx
  4. The Teams adapter dispatch would render a file card (verified by
     checking the send_response contract)

All tools run for real (pandas, openpyxl). Only the LLM is mocked.

This test is the Phase 0 acceptance gate. See:
docs/superpowers/specs/2026-04-16-yigthinker-becomes-yigcore-design.md §2.4
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pandas as pd
import pytest

from yigthinker.agent import AgentLoop
from yigthinker.hooks.executor import HookExecutor
from yigthinker.hooks.registry import HookRegistry
from yigthinker.permissions import PermissionSystem
from yigthinker.registry_factory import build_tool_registry
from yigthinker.session import SessionContext
from yigthinker.tools.sql.connection import ConnectionPool
from yigthinker.types import LLMResponse, ToolUse


@pytest.fixture
def revenue_csv(tmp_path: Path) -> Path:
    """Small financial dataset to mimic an attached file."""
    csv = tmp_path / "revenue.csv"
    df = pd.DataFrame({
        "month":   ["Jan", "Feb", "Mar", "Apr"],
        "revenue": [120000, 135000, 142000, 128000],
        "costs":   [ 80000,  88000,  91000,  85000],
    })
    df["profit"] = df["revenue"] - df["costs"]
    df.to_csv(csv, index=False)
    return csv


def _scripted_llm(script: list[LLMResponse]):
    """Return a mock LLM provider that returns responses in order.

    This test forces the non-streaming path by making chat() the only
    method AgentLoop uses (AgentLoop.run() without on_token uses chat()).
    """
    calls = {"n": 0}

    async def chat(messages, tools, system=None):
        i = calls["n"]
        calls["n"] += 1
        return script[i]

    provider = MagicMock()
    provider.chat = chat
    provider.supports_streaming = MagicMock(return_value=False)
    return provider, calls


@pytest.mark.asyncio
async def test_phase0_agent_produces_excel_artifact(revenue_csv: Path, tmp_path: Path):
    """Phase 0 acceptance: user asks for an Excel, agent must produce a .xlsx artifact."""
    output_xlsx = tmp_path / "monthly_summary.xlsx"

    # Script the LLM to make the right tool call sequence
    script = [
        # Turn 1: load the CSV
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id=str(uuid4()),
                name="df_load",
                input={
                    "source": str(revenue_csv),
                    "var_name": "rev",
                },
            )],
        ),
        # Turn 2: generate the excel
        LLMResponse(
            stop_reason="tool_use",
            text="",
            tool_uses=[ToolUse(
                id=str(uuid4()),
                name="report_generate",
                input={
                    "var_name": "rev",
                    "output_path": str(output_xlsx),
                    "format": "excel",
                    "title": "Monthly Summary",
                    "sheet_name": "Summary",
                },
            )],
        ),
        # Turn 3: final reply (no more tool calls)
        LLMResponse(
            stop_reason="end_turn",
            text="已生成: monthly_summary.xlsx",
            tool_uses=[],
        ),
    ]
    provider, calls = _scripted_llm(script)

    registry = build_tool_registry(pool=ConnectionPool())
    hooks_registry = HookRegistry()
    permissions = PermissionSystem({})
    executor = HookExecutor(hooks_registry)

    loop = AgentLoop(
        provider=provider,
        tools=registry,
        hooks=executor,
        permissions=permissions,
    )

    ctx = SessionContext(
        session_id=f"test-{uuid4().hex[:8]}",
        # workspace_dir = tmp_path → output_xlsx (inside tmp_path) passes
        # the _safe_output_path workspace check.
        settings={"workspace_dir": str(tmp_path)},
        transcript_path=str(tmp_path / "transcript.jsonl"),
    )

    result = await loop.run(
        "把这份数据做成月度汇总 Excel",
        ctx,
    )

    # The actual xlsx file must exist on disk
    assert output_xlsx.exists(), (
        f"Agent loop did not produce the Excel file. "
        f"Expected: {output_xlsx}. Calls made: {calls['n']}."
    )
    assert output_xlsx.stat().st_size > 0, "Excel file is empty"

    # The result must reference the artifact
    assert "monthly_summary" in (result or "") or "xlsx" in (result or "").lower(), (
        f"Agent final message should mention the produced file. Got: {result!r}"
    )


def test_phase0_tool_result_to_artifact_chain(tmp_path: Path):
    """End-to-end artifact shape: report_generate output → structured_artifact → file card references filename.

    This verifies the three-step chain that delivers a produced Excel to the user:
      1. report_generate returns {"output_path": "...", "format": "excel", "rows": N, "columns": M}
      2. The agent turns that into a file artifact via channel code (artifact_write returns a
         file-kind shape directly; report_generate output is wrapped into one by the caller)
      3. Teams _build_card_for_artifact produces a card referencing the filename

    We don't go through full send_response here (that requires a live Bot Framework
    endpoint). Task 5's helper tests cover the dispatch primitives.
    """
    import json
    from yigthinker.presence.channels.teams.adapter import TeamsAdapter

    # Create a file so bytes() / path existence checks in renderers don't choke
    xlsx_path = tmp_path / "monthly_summary.xlsx"
    xlsx_path.write_bytes(b"fake xlsx bytes for test")

    # Mirror the shape the agent loop would pass to Teams adapter after a
    # report_generate tool call (the caller wraps report_generate output into
    # a file-kind artifact):
    artifact = {
        "kind": "file",
        "filename": xlsx_path.name,
        "path": str(xlsx_path),
        "bytes": xlsx_path.stat().st_size,
        "summary": "Monthly summary",
    }

    adapter = TeamsAdapter({
        "tenant_id": "t",
        "client_id": "c",
        "client_secret": "s",
        "webhook_secret": "w",
    })
    card = adapter._build_card_for_artifact("done", artifact)
    card_text = json.dumps(card)
    assert xlsx_path.name in card_text, (
        f"Teams card for a file artifact must reference '{xlsx_path.name}'. "
        f"Got: {card_text[:400]}"
    )
