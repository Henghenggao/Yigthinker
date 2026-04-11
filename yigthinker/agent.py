from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from yigthinker.hooks.executor import HookExecutor
from yigthinker.permissions import PermissionSystem
from yigthinker.providers.base import LLMProvider
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import HookAction, HookEvent, LLMResponse, Message, StreamEvent, ToolResult, ToolUse

if TYPE_CHECKING:
    from yigthinker.memory.compact import SmartCompact
    from yigthinker.memory.session_memory import MemoryManager

_ITERATION_LIMIT_SYSTEM_MSG = (
    "[SYSTEM] You have reached the maximum number of tool call iterations. "
    "Please summarize your findings so far and provide the best answer you "
    "can with the information gathered."
)


def _serialize_tool_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except TypeError:
        return str(content)


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
        self._memory_manager: MemoryManager | None = None
        self._compact: SmartCompact | None = None
        self._background_tasks: set[asyncio.Task] = set()
        # Phase 10 / BHV-02 (CORR-02): per-run callback invoked inside the system
        # prompt assembly block on iteration == 1. Wired by builder.py; never by
        # SessionStart hooks (HookResult has no context-injection variant).
        self._startup_alert_provider: Callable[[], str | None] | None = None

    def set_memory_manager(self, mm: MemoryManager) -> None:
        self._memory_manager = mm

    def set_compact(self, compact: SmartCompact) -> None:
        self._compact = compact

    def set_startup_alert_provider(
        self,
        fn: Callable[[], str | None] | None,
    ) -> None:
        """Register a BHV-02 startup alert provider (called once per run).

        The provider is invoked inside the first iteration of the main loop as part
        of system_prompt assembly. Returning a non-empty string prepends that string
        to system_prompt as a `[Workflow Health Alert]` block. Returning None or an
        empty string skips the alert.

        The provider is wrapped in try/except inside `run()` -- a crashing provider
        MUST NOT break `AgentLoop.run()`.
        """
        self._startup_alert_provider = fn

    async def run(
        self,
        user_input: str,
        ctx: SessionContext,
        on_tool_event: Callable[[str, dict], None] | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        messages: list[Message] = list(ctx.messages)
        messages.append(Message(role="user", content=user_input))
        ctx._on_tool_event = on_tool_event  # type: ignore[attr-defined]
        tool_schemas = self._tools.export_schemas()
        iteration = 0

        # Fire SessionStart before the main loop
        start_event = HookEvent(
            event_type="SessionStart",
            session_id=ctx.session_id,
            transcript_path=ctx.transcript_path,
        )
        await self._hooks.run(start_event)

        result_text = ""
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
                        result_text = text
                        break

                    # Token budget check before LLM call — fire PreCompact if exceeded
                    system_prompt: str | None = None
                    if self._memory_manager is not None:
                        loaded = self._memory_manager.load_memory()
                        if loaded:
                            system_prompt = ctx.context_manager.build_memory_section(loaded)

                    # Drain background subagent notifications (D-08)
                    if ctx.subagent_manager is not None:
                        notifications = ctx.subagent_manager.drain_notifications()
                        if notifications:
                            notif_text = "\n".join(notifications)
                            if system_prompt:
                                system_prompt += f"\n\n[Subagent Notifications]\n{notif_text}"
                            else:
                                system_prompt = f"[Subagent Notifications]\n{notif_text}"

                    # Phase 10 / BHV-01: automation awareness directive (D-23 / D-24).
                    # Always render on every iteration -- the directive is stateless.
                    try:
                        directive = ctx.context_manager.build_automation_directive(
                            getattr(ctx, "settings", None) or {}
                        )
                    except Exception:
                        directive = None
                    if directive:
                        if system_prompt:
                            system_prompt += f"\n\n{directive}"
                        else:
                            system_prompt = directive

                    # Phase 10 / BHV-02 (CORR-02): first-iteration startup alert provider.
                    # Called EXACTLY ONCE per run, gated on iteration == 1, defensively wrapped.
                    if iteration == 1 and self._startup_alert_provider is not None:
                        try:
                            alert = self._startup_alert_provider()
                        except Exception:
                            alert = None  # Pitfall 3: provider exceptions NEVER break the run
                        if alert:
                            if system_prompt:
                                system_prompt = f"{alert}\n\n{system_prompt}"
                            else:
                                system_prompt = alert

                    if self._compact is not None:
                        token_est = self._estimate_tokens(messages)
                        if token_est > ctx.context_manager.history_budget:
                            pre_compact_event = HookEvent(
                                event_type="PreCompact",
                                session_id=ctx.session_id,
                                transcript_path=ctx.transcript_path,
                            )
                            await self._hooks.run(pre_compact_event)
                            memory_content = self._memory_manager.load_memory() if self._memory_manager else ""
                            vars_summary = self._format_vars_summary(ctx)
                            messages = await self._compact.run(messages, memory_content, token_est, vars_summary)

                    if on_token is not None:
                        accumulated_text = ""
                        tool_uses_from_stream: list[ToolUse] = []
                        stop_reason = "end_turn"

                        try:
                            async for event in self._provider.stream(messages, tool_schemas, system=system_prompt):
                                if event.type == "text":
                                    accumulated_text += event.text
                                    on_token(event.text)
                                elif event.type == "tool_use" and event.tool_use is not None:
                                    tool_uses_from_stream.append(event.tool_use)
                                elif event.type == "done":
                                    stop_reason = event.stop_reason or "end_turn"
                                elif event.type == "error":
                                    break
                        except Exception:
                            pass

                        response = LLMResponse(
                            stop_reason=stop_reason,
                            text=accumulated_text,
                            tool_uses=tool_uses_from_stream,
                        )
                    else:
                        response = await self._provider.chat(messages, tool_schemas, system=system_prompt)

                    if response.stop_reason == "end_turn" or not response.tool_uses:
                        messages.append(Message(role="assistant", content=response.text))
                        result_text = response.text
                        break

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
                        result = await self._execute_tool(tool_use.name, tool_use.input, tool_use.id, ctx, on_tool_event)
                        result_content = _serialize_tool_content(result.content)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": result_content,
                                "is_error": result.is_error,
                            }
                        )
                    messages.append(Message(role="user", content=tool_results))

                    # Memory extraction after tool calls
                    if self._memory_manager is not None:
                        self._memory_manager.record_turn()
                        if self._memory_manager.should_extract():
                            messages_snapshot = list(messages)  # shallow copy per Pitfall 1
                            extraction_coro = self._run_extraction(messages_snapshot)
                            task = asyncio.create_task(extraction_coro)
                            scheduled_coro = None
                            get_coro = getattr(task, "get_coro", None)
                            if callable(get_coro):
                                try:
                                    scheduled_coro = get_coro()
                                except Exception:
                                    scheduled_coro = None
                            if scheduled_coro is not extraction_coro:
                                extraction_coro.close()
                            self._background_tasks.add(task)
                            task.add_done_callback(self._background_tasks.discard)

        except TimeoutError:
            result_text = "(Agent loop timed out. Partial results may be available in the variable registry.)"
        finally:
            ctx.messages = messages
            end_event = HookEvent(
                event_type="SessionEnd",
                session_id=ctx.session_id,
                transcript_path=ctx.transcript_path,
            )
            await self._hooks.run(end_event)

        return result_text

    async def _run_extraction(self, messages_snapshot: list[Message]) -> None:
        """Fire-and-forget extraction. Errors are silently suppressed."""
        try:
            if self._memory_manager is not None:
                await self._memory_manager.extract_memories(messages_snapshot, self._provider)
        except Exception:
            pass  # Never surface extraction errors to user

    def _estimate_tokens(self, messages: list[Message]) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(str(m.content)) for m in messages)
        return total_chars // 4

    def _format_vars_summary(self, ctx: SessionContext) -> str:
        """Format VarRegistry contents for compaction context."""
        infos = ctx.vars.list()
        if not infos:
            return ""
        lines = []
        for info in infos:
            lines.append(f"{info.name}: {info.shape[0]}x{info.shape[1]} ({info.var_type})")
        return "\n".join(lines)

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        ctx: SessionContext,
        on_tool_event: Callable[[str, dict], None] | None = None,
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

        decision = self._permissions.check(tool_name, tool_input, session_id=ctx.session_id)
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
                self._permissions.allow_for_session(tool_name, ctx.session_id)

        if on_tool_event is not None:
            on_tool_event("tool_call", {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_id": tool_use_id,
            })

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

        if on_tool_event is not None:
            serialized_content = _serialize_tool_content(result.content)
            on_tool_event("tool_result", {
                "tool_id": tool_use_id,
                "content": serialized_content,
                "is_error": result.is_error,
            })

        return result
