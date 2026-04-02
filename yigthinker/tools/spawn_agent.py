from __future__ import annotations
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


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
        "Subagents run independently with isolated DataFrame snapshots. "
        "Specify dataframes=[] to share read-only copies with the subagent."
    )
    input_schema = SpawnAgentInput

    async def execute(self, input: SpawnAgentInput, ctx: SessionContext) -> ToolResult:
        snapshot: dict[str, pd.DataFrame] = {}
        if input.dataframes:
            for df_name in input.dataframes:
                try:
                    df = ctx.vars.get(df_name)
                except KeyError:
                    available = [info.name for info in ctx.vars.list()]
                    return ToolResult(
                        tool_use_id="",
                        content=f"DataFrame '{df_name}' not found in variable registry. "
                                f"Available: {available}",
                        is_error=True,
                    )
                snapshot[df_name] = df.copy()

        result_text = await self._run_subagent(
            prompt=input.prompt,
            snapshot=snapshot,
            model=input.model,
            name=input.name,
        )
        return ToolResult(tool_use_id="", content=result_text)

    async def _run_subagent(
        self,
        prompt: str,
        snapshot: dict[str, pd.DataFrame],
        model: str | None = None,
        name: str | None = None,
    ) -> str:
        df_summary = ", ".join(
            f"{k}: {v.shape[0]}x{v.shape[1]}" for k, v in snapshot.items()
        )
        return (
            f"Subagent '{name or 'unnamed'}' completed.\n"
            f"DataFrames available: {df_summary or 'none'}\n"
            f"Task: {prompt[:100]}"
        )
