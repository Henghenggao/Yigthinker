from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.subagent.manager import SubagentManager
from yigthinker.types import ToolResult

if TYPE_CHECKING:
    from yigthinker.tools.registry import ToolRegistry


class SpawnAgentInput(BaseModel):
    prompt: str
    model: str | None = None
    background: bool = False
    name: str | None = None
    dataframes: list[str] | None = None
    allowed_tools: list[str] | None = None
    agent_type: str | None = None
    team_memory: bool = False


class SpawnAgentTool:
    name = "spawn_agent"
    description = (
        "Spawn a child agent to handle a subtask in isolation. "
        "The child runs with its own context and returns only its final result. "
        "Specify allowed_tools to restrict the child's capabilities, "
        "or omit to inherit all parent tools except spawn_agent."
    )
    input_schema = SpawnAgentInput

    def __init__(self, tools: ToolRegistry | None = None) -> None:
        self._tools = tools

    async def execute(self, input: SpawnAgentInput, ctx: SessionContext) -> ToolResult:
        # Ensure SubagentManager exists on ctx
        if ctx.subagent_manager is None:
            max_concurrent = (
                ctx.settings.get("spawn_agent", {}).get("max_concurrent", 3)
            )
            ctx.subagent_manager = SubagentManager(max_concurrent)

        # Check concurrency limit
        if not ctx.subagent_manager.can_spawn():
            limit = ctx.subagent_manager._max_concurrent
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Cannot spawn: concurrent subagent limit ({limit}) reached. "
                    "Wait for running subagents to complete or cancel one."
                ),
                is_error=True,
            )

        # Validate allowed_tools against parent registry
        if input.allowed_tools is not None and self._tools is not None:
            available = set(self._tools.names())
            invalid = [t for t in input.allowed_tools if t not in available]
            if invalid:
                return ToolResult(
                    tool_use_id="",
                    content=(
                        f"Invalid tool names in allowed_tools: {invalid}. "
                        f"Available tools: {sorted(available)}"
                    ),
                    is_error=True,
                )

        # Structural stub -- full foreground/background execution wired in Plan 04
        return ToolResult(
            tool_use_id="",
            content=(
                "spawn_agent structure validated. "
                "Full execution available after lifecycle wiring."
            ),
            is_error=True,
        )
