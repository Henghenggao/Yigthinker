from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from yigthinker.hooks.executor import HookExecutor
from yigthinker.permissions import PermissionSystem
from yigthinker.providers.base import LLMProvider
from yigthinker.session import SessionContext
from yigthinker.tools.registry import ToolRegistry
from yigthinker.types import HookAction, HookEvent, LLMResponse, Message, ToolResult, ToolUse

if TYPE_CHECKING:
    from yigthinker.memory.compact import SmartCompact
    from yigthinker.memory.session_memory import MemoryManager

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 8000

_ITERATION_LIMIT_SYSTEM_MSG = (
    "[SYSTEM] You have reached the maximum number of tool call iterations. "
    "Please summarize your findings so far and provide the best answer you "
    "can with the information gathered."
)

# quick-260416-j3y-04: when the wall-clock budget reaches this fraction, inject
# a single steering message ahead of the next LLM call so the model has a chance
# to wrap up gracefully instead of being killed mid-iteration.
SOFT_DEADLINE_FRACTION: float = 0.8

_SOFT_DEADLINE_MSG = (
    "[SYSTEM] You have used 80% of your time budget. Do NOT start new tool "
    "calls — summarize what you have and end the turn."
)

# Cap on how many variables are summarized in the timeout recovery message.
# Keeps the trailing text usable even when the session produced dozens of DFs.
_TIMEOUT_VAR_SUMMARY_LIMIT: int = 20


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
        fallback_provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._hooks = hooks
        self._permissions = permissions
        self._ask_fn = ask_fn
        self._max_iterations = max_iterations
        self._timeout_seconds = timeout_seconds
        self._fallback_provider = fallback_provider
        self._max_tokens_recovery_count = 0
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
        *,
        timeout_override: float | None = None,
    ) -> str:
        """Run the agent loop.

        ``timeout_override`` (quick-260416-j3y-04): when set, the wall-clock
        budget for this single run uses the override instead of
        ``self._timeout_seconds``. Gateway passes a per-channel value so IM
        surfaces (e.g. Teams) can tolerate longer waits than the CLI REPL.
        """
        self._max_tokens_recovery_count = 0
        messages: list[Message] = list(ctx.messages)
        messages.append(Message(role="user", content=user_input))
        ctx._pending_injections = None  # P1-5: clear stale injections from prior run
        ctx._on_tool_event = on_tool_event
        tool_schemas = self._tools.export_schemas()
        iteration = 0

        # Fire SessionStart before the main loop
        start_event = HookEvent(
            event_type="SessionStart",
            session_id=ctx.session_id,
            transcript_path=ctx.transcript_path,
        )
        await self._hooks.run(start_event)

        # quick-260416-j3y-04: soft-deadline bookkeeping.
        effective_timeout = (
            timeout_override if timeout_override is not None else self._timeout_seconds
        )
        loop_start = asyncio.get_event_loop().time()
        soft_deadline = loop_start + effective_timeout * SOFT_DEADLINE_FRACTION
        soft_deadline_injected = False

        result_text = ""
        try:
            async with asyncio.timeout(effective_timeout):
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

                    # P1-5: inject hook system messages from previous tool execution
                    pending_injections = getattr(ctx, "_pending_injections", None)
                    if pending_injections:
                        # Task 20: sanitize hook content to strip prompt-injection
                        # patterns (e.g. "ignore all prior instructions") before
                        # they land in the system prompt.
                        from yigthinker.context_manager import _sanitize_memory_content
                        sanitized = [_sanitize_memory_content(inj) for inj in pending_injections]
                        injection_text = "\n".join(sanitized)
                        # Cap at 8192 chars (~2048 tokens)
                        if len(injection_text) > 8192:
                            injection_text = injection_text[:8192] + "\n[hook injections truncated]"
                        if system_prompt:
                            system_prompt += f"\n\n[Hook Context]\n{injection_text}"
                        else:
                            system_prompt = f"[Hook Context]\n{injection_text}"
                        ctx._pending_injections = None

                    steerings = ctx.drain_steerings()
                    if steerings:
                        # Task 20 extension: sanitize steering messages before injecting
                        # into the system prompt — same guard applied to hook injections.
                        # Steerings originate from WebSocket user_input and Teams/Feishu
                        # Bot Framework payloads; both are external trust boundaries.
                        from yigthinker.context_manager import _sanitize_memory_content
                        sanitized_steerings = [_sanitize_memory_content(s) for s in steerings]
                        numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sanitized_steerings))
                        steering_block = f"[User Follow-up (sent while you were working)]\n{numbered}"
                        if system_prompt:
                            system_prompt += f"\n\n{steering_block}"
                        else:
                            system_prompt = steering_block

                    if self._compact is not None:
                        token_est = self._estimate_tokens(messages)
                        if token_est > ctx.context_manager.history_budget:
                            # Microcompact pass: replace old referenced tool_results
                            messages = self._microcompact(messages)
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
                            messages, compact_injection = await self._compact.run(messages, memory_content, token_est, vars_summary)
                            if compact_injection:
                                if system_prompt:
                                    system_prompt += f"\n\n{compact_injection}"
                                else:
                                    system_prompt = compact_injection

                    # quick-260416-j3y-04: inject the soft-deadline steering
                    # message exactly once, when we cross 80% of the budget.
                    # Placed right before the LLM call so the model has a chance
                    # to wrap up cleanly instead of being cut off mid-iteration.
                    if (
                        not soft_deadline_injected
                        and asyncio.get_event_loop().time() >= soft_deadline
                    ):
                        messages.append(
                            Message(role="user", content=_SOFT_DEADLINE_MSG)
                        )
                        soft_deadline_injected = True

                    using_fallback = False

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
                        except (TimeoutError, asyncio.CancelledError):
                            raise
                        except Exception as exc:
                            if self._fallback_provider is not None and not using_fallback:
                                logger.warning("Primary provider failed (%s), switching to fallback", exc)
                                using_fallback = True
                                accumulated_text = ""
                                tool_uses_from_stream = []
                                stop_reason = "end_turn"
                                try:
                                    async for event in self._fallback_provider.stream(messages, tool_schemas, system=system_prompt):
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
                                    raise
                            else:
                                raise

                        response = LLMResponse(
                            stop_reason=stop_reason,
                            text=accumulated_text,
                            tool_uses=tool_uses_from_stream,
                        )
                    else:
                        try:
                            response = await self._provider.chat(messages, tool_schemas, system=system_prompt)
                        except (TimeoutError, asyncio.CancelledError):
                            raise
                        except Exception as exc:
                            if self._fallback_provider is not None and not using_fallback:
                                logger.warning("Primary provider failed (%s), switching to fallback", exc)
                                using_fallback = True
                                response = await self._fallback_provider.chat(messages, tool_schemas, system=system_prompt)
                            else:
                                raise

                    # Max-tokens auto-recovery: inject continuation prompt
                    if response.stop_reason == "max_tokens" and not response.tool_uses:
                        self._max_tokens_recovery_count += 1
                        if self._max_tokens_recovery_count <= 3:
                            if response.text:
                                messages.append(Message(role="assistant", content=response.text))
                            messages.append(Message(
                                role="user",
                                content="[System: Output token limit reached. Continue directly from where you left off - no apology, no recap.]",
                            ))
                            continue

                    if response.stop_reason == "end_turn" or not response.tool_uses:
                        messages.append(Message(role="assistant", content=response.text))
                        result_text = response.text
                        break

                    content_blocks: list[dict] = []
                    # Include thinking blocks before text/tool_use (preserves multi-turn context)
                    for tb in response.thinking_blocks:
                        content_blocks.append(tb)
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

                    tool_results = await self._execute_tool_batch(
                        response.tool_uses, ctx, on_tool_event
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
            # quick-260416-j3y-04: surface a concrete list of what survived
            # instead of the opaque "may be available" line. The user can then
            # reference `ctx.vars.get("name")` or re-prompt the agent against
            # the registered DataFrames without re-running the pipeline.
            result_text = (
                "(Agent loop timed out. Partial results may be available in "
                "the variable registry.)"
            )
            try:
                infos = ctx.vars.list()
            except Exception:
                infos = []
            if infos:
                lines = []
                for info in infos[:_TIMEOUT_VAR_SUMMARY_LIMIT]:
                    lines.append(
                        f"- {info.name}: {info.shape[0]}x{info.shape[1]} "
                        f"({info.var_type})"
                    )
                overflow = len(infos) - _TIMEOUT_VAR_SUMMARY_LIMIT
                if overflow > 0:
                    lines.append(f"- ...and {overflow} more")
                result_text += (
                    "\n\nPartial results still in variable registry:\n"
                    + "\n".join(lines)
                )
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

    async def _execute_tool_batch(
        self,
        tool_uses: list[ToolUse],
        ctx: SessionContext,
        on_tool_event: Callable[[str, dict], None] | None = None,
    ) -> list[dict]:
        """Execute a batch of tool calls, running concurrency-safe tools in parallel."""
        safe: list[ToolUse] = []
        unsafe: list[ToolUse] = []
        for tu in tool_uses:
            try:
                tool = self._tools.get(tu.name)
                if getattr(tool, "is_concurrency_safe", False):
                    safe.append(tu)
                else:
                    unsafe.append(tu)
            except Exception:
                unsafe.append(tu)

        results_by_id: dict[str, ToolResult] = {}

        # Run safe tools concurrently
        if safe:
            safe_results = await asyncio.gather(
                *[self._execute_tool(tu.name, tu.input, tu.id, ctx, on_tool_event) for tu in safe]
            )
            for tu, result in zip(safe, safe_results):
                results_by_id[tu.id] = result

        # Run unsafe tools serially
        for tu in unsafe:
            result = await self._execute_tool(tu.name, tu.input, tu.id, ctx, on_tool_event)
            results_by_id[tu.id] = result

        # Build results in original order
        tool_results: list[dict] = []
        for tu in tool_uses:
            result = results_by_id[tu.id]
            result_content = _serialize_tool_content(result.content)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_content,
                "is_error": result.is_error,
            })

        # P1-5: collect hook injections from tool results
        hook_injections: list[str] = []
        for tu in tool_uses:
            result = results_by_id[tu.id]
            injections = getattr(result, "_hook_injections", None)
            if injections:
                hook_injections.extend(injections)

        # Store injections on ctx for system prompt assembly
        if hook_injections:
            ctx._pending_injections = hook_injections

        return tool_results

    def _microcompact(self, messages: list[Message]) -> list[Message]:
        """Replace old tool_result contents that have been referenced by subsequent assistant messages."""
        sentinel = "[result referenced - omitted for context efficiency]"
        # Collect tool_use_ids from tool_result blocks more than 3 messages from the end
        cutoff = len(messages) - 3
        if cutoff <= 0:
            return messages

        # Find all tool_use_ids referenced in assistant messages after the cutoff
        referenced_ids: set[str] = set()
        for msg in messages[cutoff:]:
            if msg.role == "assistant" and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        referenced_ids.add(block.get("id", ""))

        # Scan old messages for tool_result blocks and replace if referenced
        for i in range(cutoff):
            msg = messages[i]
            if msg.role == "user" and isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_id = item.get("tool_use_id", "")
                        if tool_id in referenced_ids:
                            item["content"] = sentinel

        return messages

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

        pre_agg = await self._hooks.run(pre_event)
        if pre_agg.action == HookAction.BLOCK:
            return ToolResult(
                tool_use_id=tool_use_id,
                content=f"Blocked: {pre_agg.message}",
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

            # quick-260416-j3y diagnostic: log every tool call so Teams/IM
            # channel operators can see what the LLM actually picked. Input
            # repr is truncated to keep logs readable on wide payloads.
            logger.info(
                "tool_call name=%s input=%s",
                tool_name,
                repr(tool_input)[:300],
            )

            # P1-1: inject progress callback before tool execution.
            # NOTE: concurrent tool batches share the same ctx, so if multiple
            # safe tools run via asyncio.gather(), the last one to set
            # _progress_callback wins. This means progress events may briefly
            # be attributed to the wrong tool. Acceptable for current use;
            # rearchitect to a dict keyed by tool_use_id if precise attribution
            # becomes important.
            if on_tool_event is not None:
                ctx._progress_callback = lambda msg: on_tool_event(
                    "tool_progress", {"tool": tool_name, "message": msg}
                )

            result = await tool.execute(input_obj, ctx)
            result.tool_use_id = tool_use_id

            # quick-260416-j3y diagnostic: log tool outcome.
            logger.info(
                "tool_result name=%s is_error=%s",
                tool_name,
                result.is_error,
            )

            # P1-1: cleanup progress callback
            ctx._progress_callback = None

            # Truncate oversized results
            result_str = _serialize_tool_content(result.content)
            if len(result_str) > MAX_RESULT_CHARS:
                total = len(result_str)
                result.content = result_str[:MAX_RESULT_CHARS] + (
                    f"\n[truncated - {total} chars total. "
                    f"Full result in variable registry.]"
                )
        except Exception as exc:
            ctx._progress_callback = None  # P1-1: cleanup on error
            result = ToolResult(tool_use_id=tool_use_id, content=str(exc), is_error=True)

        post_event = HookEvent(
            event_type="PostToolUse",
            session_id=ctx.session_id,
            transcript_path=ctx.transcript_path,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=result,
        )
        post_agg = await self._hooks.run(post_event)

        # P1-5: apply post-hook effects
        if post_agg.suppress:
            result = ToolResult(tool_use_id=tool_use_id, content="[output suppressed by hook]", is_error=False)
            result._suppressed = True
        elif post_agg.replacement is not None:
            result.content = post_agg.replacement

        # Collect injections from both pre and post hooks
        all_injections = pre_agg.injections + post_agg.injections
        if all_injections:
            result._hook_injections = all_injections

        if on_tool_event is not None:
            serialized_content = _serialize_tool_content(result.content)
            on_tool_event("tool_result", {
                "tool_id": tool_use_id,
                "content": serialized_content,
                "content_obj": result.content,
                "is_error": result.is_error,
            })

        return result
