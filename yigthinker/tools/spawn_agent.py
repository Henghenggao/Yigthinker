from __future__ import annotations

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.types import ToolResult


class SpawnAgentInput(BaseModel):
    prompt: str
    model: str | None = None
    background: bool = False
    name: str | None = None
    dataframes: list[str] | None = None
    team_memory: bool = False


class SpawnAgentTool:
    name = "spawn_agent"
    description = (
        "Spawn a subagent to handle a task in parallel. "
        "(Status: NOT YET IMPLEMENTED -- will return an error)"
    )
    input_schema = SpawnAgentInput

    async def execute(self, input: SpawnAgentInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(
            tool_use_id="",
            content=(
                "spawn_agent is not yet implemented. This tool will be available in a "
                "future release. Please accomplish the task using the available tools directly."
            ),
            is_error=True,
        )
