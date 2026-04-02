from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from yigthinker.hooks.executor import HookExecutor
from yigthinker.permissions import PermissionSystem
from yigthinker.providers.base import LLMProvider
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import HookAction, HookEvent, Message, ToolResult

_ITERATION_LIMIT_SYSTEM_MSG = (
    "[SYSTEM] You have reached the maximum number of tool call iterations. "
    "Please summarize your findings so far and provide the best answer you "
    "can with the information gathered."
)


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        hooks: HookExecutor,
        permissions: PermissionSystem,
        ask_fn: Callable[[str, dict], Awaitable[Any]] | None = None,
        max_iterations: int = 50,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._hooks = hooks
        self._permissions = permissions
        self._ask_fn = ask_fn
        self._max_iterations = max_iterations
        self._timeout_seconds = timeout_seconds

    async def run(self, user_input: str, ctx: SessionContext) -> str:
        messages: list[Message] = list(ctx.messages)
        messages.append(Message(role="user", content=user_input))
        tool_schemas = self._tools.export_schemas()
        iteration = 0

        try:
            async with asyncio.timeout(self._timeout_seconds):
                while True:
                    iteration += 1

                    if iteration > self._max_iterations:
                        messages.append(
                            Message(role="user", content=_ITERATION_LIMIT_SYSTEM_MSG)
                        )
                        response = await self._provider.chat(messages, [])
                        text = response.text or "(Agent loop reached iteration limit)"
                        messages.append(Message(role="assistant", content=text))
                        ctx.messages = messages
                        return text

                    response = await self._provider.chat(messages, tool_schemas)

                    if response.stop_reason == "end_turn" or not response.tool_uses:
                        messages.append(Message(role="assistant", content=response.text))
                        ctx.messages = messages
                        return response.text

                    content_blocks: list[dict] = []
                    if response.text:
                        content_blocks.append({"type": "text", "text": response.text})
                    for tool_use in response.tool_uses:
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tool_use.id,
                                "name": tool_use.name,
                                "input": tool_use.input,
                            }
                        )
                    messages.append(Message(role="assistant", content=content_blocks))

                    tool_results: list[dict] = []
                    for tool_use in response.tool_uses:
                        result = await self._execute_tool(tool_use.name, tool_use.input, tool_use.id, ctx)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": str(result.content),
                                "is_error": result.is_error,
                            }
                        )
                    messages.append(Message(role="user", content=tool_results))
        except TimeoutError:
            ctx.messages = messages
            return "(Agent loop timed out. Partial results may be available in the variable registry.)"

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        ctx: SessionContext,
    ) -> ToolResult:
        pre_event = HookEvent(
            event_type="PreToolUse",
            session_id=ctx.session_id,
            transcript_path=ctx.transcript_path,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        hook_result = await self._hooks.run(pre_event)
        if hook_result.action == HookAction.BLOCK:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Blocked: {hook_result.message}",
                is_error=True,
            )

        decision = self._permissions.check(tool_name, tool_input)
        if decision == "deny":
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Permission denied for tool '{tool_name}'",
                is_error=True,
            )
        if decision == "ask" and self._ask_fn is not None:
            from yigthinker.cli.ask_prompt import PermissionAnswer

            answer = await self._ask_fn(tool_name, tool_input)
            if answer == PermissionAnswer.DENY:
                return ToolResult(
                    tool_use_id=tool_use_id,
                    content=f"User denied tool '{tool_name}'",
                    is_error=True,
                )
            if answer == PermissionAnswer.ALLOW_ALL:
                self._permissions._allow.append(tool_name)

        try:
            tool = self._tools.get(tool_name)
            input_obj = tool.input_schema(**tool_input)
            result = await tool.execute(input_obj, ctx)
            result.tool_use_id = tool_use_id
        except Exception as exc:
            result = ToolResult(tool_use_id=tool_use_id, content=str(exc), is_error=True)

        post_event = HookEvent(
            event_type="PostToolUse",
            session_id=ctx.session_id,
            transcript_path=ctx.transcript_path,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=result,
        )
        await self._hooks.run(post_event)
        return result
