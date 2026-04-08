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
    agent_type: str | None = None
    allowed_tools: list[str] | None = None


class SpawnAgentTool:
    name = "spawn_agent"
    description = (
        "Spawn a subagent to handle a task in parallel. "
        "Use agent_type to load a predefined agent configuration from "
        ".yigthinker/agents/*.md files."
    )
    input_schema = SpawnAgentInput

    async def execute(self, input: SpawnAgentInput, ctx: SessionContext) -> ToolResult:
        # If agent_type is specified, load predefined config and merge
        system_prompt_prefix = ""
        effective_allowed_tools = input.allowed_tools
        effective_model = input.model

        if input.agent_type:
            from yigthinker.subagent.agent_types import load_agent_type
            try:
                agent_def = load_agent_type(input.agent_type)
            except FileNotFoundError as exc:
                return ToolResult(tool_use_id="", content=str(exc), is_error=True)
            except ValueError as exc:
                return ToolResult(tool_use_id="", content=str(exc), is_error=True)

            # Agent type's allowed_tools override if user didn't specify (D-11)
            if effective_allowed_tools is None and agent_def.allowed_tools is not None:
                effective_allowed_tools = agent_def.allowed_tools

            # Agent type's model override if user didn't specify
            if effective_model is None and agent_def.model is not None:
                effective_model = agent_def.model

            # System prompt: agent type body is the system prompt prefix (D-11)
            system_prompt_prefix = agent_def.system_prompt

        # Build the full prompt with agent type system prompt if present
        full_prompt = input.prompt
        if system_prompt_prefix:
            full_prompt = system_prompt_prefix + "\n\n---\n\nTask: " + input.prompt

        # Broadcast spawned event if on_tool_event is available
        _on_tool_event = getattr(ctx, "_on_tool_event", None)
        agent_name = input.name or input.agent_type or "subagent"

        if _on_tool_event:
            _on_tool_event("subagent_event", {
                "subagent_id": "",
                "subagent_name": agent_name,
                "event": "spawned",
                "detail": f"Task: {input.prompt[:100]}",
            })

        # Subagent execution is not yet fully wired (engine/manager from waves 1-3).
        # Return informative error for now; once engine is available it will run here.
        return ToolResult(
            tool_use_id="",
            content=(
                "spawn_agent is not yet fully implemented. Agent type loading and "
                "event broadcasting are wired. The execution engine will be available "
                "once the SubagentEngine module is integrated. "
                f"Would use prompt: {full_prompt[:200]}, "
                f"model: {effective_model}, "
                f"allowed_tools: {effective_allowed_tools}"
            ),
            is_error=True,
        )
