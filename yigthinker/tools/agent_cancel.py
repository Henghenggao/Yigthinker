from __future__ import annotations

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class AgentCancelInput(BaseModel):
    subagent_id: str


class AgentCancelTool:
    name = "agent_cancel"
    description = "Cancel a running background subagent by its ID."
    input_schema = AgentCancelInput

    async def execute(self, input: AgentCancelInput, ctx: SessionContext) -> ToolResult:
        if ctx.subagent_manager is None:
            return ToolResult(
                tool_use_id="",
                content="No subagents have been spawned in this session.",
                is_error=True,
            )
        if ctx.subagent_manager.cancel(input.subagent_id):
            return ToolResult(
                tool_use_id="",
                content=f"Subagent {input.subagent_id[:8]}... cancelled.",
            )
        return ToolResult(
            tool_use_id="",
            content=(
                f"Cannot cancel subagent {input.subagent_id[:8]}...: "
                "not found or not running."
            ),
            is_error=True,
        )
