from __future__ import annotations

import time

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class AgentStatusInput(BaseModel):
    pass


class AgentStatusTool:
    name = "agent_status"
    description = (
        "List all subagents in this session (running/completed/failed/cancelled) "
        "with their IDs, names, status, and elapsed time."
    )
    input_schema = AgentStatusInput

    async def execute(self, input: AgentStatusInput, ctx: SessionContext) -> ToolResult:
        if ctx.subagent_manager is None:
            return ToolResult(
                tool_use_id="",
                content="No subagents have been spawned in this session.",
            )
        subagents = ctx.subagent_manager.list_all()
        if not subagents:
            return ToolResult(
                tool_use_id="",
                content="No subagents have been spawned in this session.",
            )
        lines = []
        for sa in subagents:
            elapsed = time.monotonic() - sa.started_at
            lines.append(
                f"- {sa.name} ({sa.subagent_id[:8]}...): "
                f"{sa.status} ({elapsed:.1f}s)"
            )
        return ToolResult(tool_use_id="", content="\n".join(lines))
