from __future__ import annotations
import re
from dataclasses import dataclass
from yigthinker.types import HookEvent, HookResult, HookAction, Message
from yigthinker.advisor.prompts import ADVISOR_SYSTEM_PROMPT


@dataclass
class AdvisorConfig:
    enabled: bool = False
    model: str = "claude-haiku-4-5-20251001"
    matcher: str = r"sql_query|df_transform|df_merge|forecast_timeseries|forecast_regression"


class AdvisorHook:
    def __init__(self, config: AdvisorConfig, provider) -> None:
        self._config = config
        self._provider = provider
        self._matcher = re.compile(config.matcher)

    async def run(self, event: HookEvent) -> HookResult:
        if not self._config.enabled:
            return HookResult(action=HookAction.ALLOW)

        if not self._matcher.fullmatch(event.tool_name):
            return HookResult(action=HookAction.ALLOW)

        tool_summary = f"Tool: {event.tool_name}\nInput: {event.tool_input}"
        response = await self._provider.chat(
            messages=[Message(role="user", content=tool_summary)],
            tools=[],
            system=ADVISOR_SYSTEM_PROMPT,
        )

        text = response.text.strip()
        if text.upper().startswith("APPROVE"):
            return HookResult(action=HookAction.ALLOW)

        reason = text[len("BLOCK:"):].strip() if text.upper().startswith("BLOCK") else text
        return HookResult(action=HookAction.BLOCK, message=reason)
