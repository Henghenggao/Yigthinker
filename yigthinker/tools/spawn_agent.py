from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

from yigthinker.session import SessionContext
from yigthinker.subagent.dataframes import copy_dataframes_to_child, merge_back_dataframes
from yigthinker.subagent.engine import SubagentEngine
from yigthinker.subagent.manager import SubagentManager
from yigthinker.subagent.transcript import create_subagent_transcript_writer
from yigthinker.types import HookEvent, ToolResult

if TYPE_CHECKING:
    from yigthinker.hooks.executor import HookExecutor
    from yigthinker.permissions import PermissionSystem
    from yigthinker.providers.base import LLMProvider
    from yigthinker.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


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
        "Spawn a child agent to handle a subtask in isolation. The child runs "
        "with its own context and returns only its final result. Use foreground "
        "mode (default) to wait for the result, or background=True to continue "
        "working while the child runs. Specify allowed_tools to restrict the "
        "child's capabilities, or agent_type to load a predefined agent "
        "configuration from .yigthinker/agents/*.md files."
    )
    input_schema = SpawnAgentInput

    def __init__(self) -> None:
        self._tools: ToolRegistry | None = None
        self._hooks: HookExecutor | None = None
        self._permissions: PermissionSystem | None = None
        self._provider: LLMProvider | None = None

    def set_parent_components(
        self,
        tools: ToolRegistry,
        hooks: HookExecutor,
        permissions: PermissionSystem,
        provider: LLMProvider,
    ) -> None:
        """Inject parent components for SubagentEngine construction."""
        self._tools = tools
        self._hooks = hooks
        self._permissions = permissions
        self._provider = provider

    async def execute(self, input: SpawnAgentInput, ctx: SessionContext) -> ToolResult:
        # 1. Check all parent components are set
        if (
            self._tools is None
            or self._hooks is None
            or self._permissions is None
            or self._provider is None
        ):
            return ToolResult(
                tool_use_id="",
                content="spawn_agent not fully initialized. Missing parent components.",
                is_error=True,
            )

        # 2. Handle agent_type if specified (SPAWN-19, SPAWN-20)
        system_prompt_prefix = ""
        effective_allowed_tools = input.allowed_tools
        effective_model = input.model

        if input.agent_type:
            from yigthinker.subagent.agent_types import load_agent_type
            try:
                agent_def = load_agent_type(input.agent_type)
            except (FileNotFoundError, ValueError) as exc:
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

        # 3. Lazy-init SubagentManager on ctx
        if ctx.subagent_manager is None:
            max_concurrent = (
                ctx.settings.get("spawn_agent", {}).get("max_concurrent", 3)
            )
            ctx.subagent_manager = SubagentManager(max_concurrent)

        # 4. Check concurrency limit (SPAWN-12)
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

        # 5. Generate agent_name
        agent_name = input.name or input.agent_type or f"subagent_{len(ctx.subagent_manager.list_all()) + 1}"

        # 6. Broadcast spawned event if on_tool_event is available (SPAWN-18)
        _on_tool_event = getattr(ctx, "_on_tool_event", None)
        if _on_tool_event:
            _on_tool_event("subagent_event", {
                "subagent_id": "",
                "subagent_name": agent_name,
                "event": "spawned",
                "detail": f"Task: {input.prompt[:100]}",
            })

        # 7. Create SubagentEngine
        engine = SubagentEngine(
            self._tools,
            self._hooks,
            self._permissions,
            self._provider,
            ctx.settings,
        )

        # 8. Create child AgentLoop
        child_loop = engine.create_child_loop(
            allowed_tools=effective_allowed_tools,
            model=effective_model,
        )

        # 9. Create isolated SessionContext for child
        child_ctx = SessionContext(settings=ctx.settings)

        # 10. Copy DataFrames if specified
        original_names: set[str] = set()
        effective_dataframes = input.dataframes
        if effective_dataframes == ["*"]:
            effective_dataframes = [info.name for info in ctx.vars.list()]
        if effective_dataframes:
            try:
                copy_dataframes_to_child(ctx.vars, child_ctx.vars, effective_dataframes)
                original_names = set(child_ctx.vars._vars.keys())
            except KeyError as exc:
                return ToolResult(
                    tool_use_id="",
                    content=f"DataFrame copy failed: {exc}",
                    is_error=True,
                )

        if not input.background:
            # 11. Foreground mode (SPAWN-10)
            info = ctx.subagent_manager.register(agent_name, task=None)

            # Set transcript path for child
            writer = create_subagent_transcript_writer(ctx.session_id, info.subagent_id)
            child_ctx.transcript_path = str(writer._path)

            try:
                result_text = await child_loop.run(full_prompt, child_ctx)

                # Merge back DataFrames if any were specified
                merge_summary = ""
                if effective_dataframes:
                    merge_summary = merge_back_dataframes(
                        ctx.vars, child_ctx.vars, agent_name, original_names,
                    )

                ctx.subagent_manager.complete(info.subagent_id, result_text)

                # Fire SubagentStop hook event (notification-only per D-13, BLOCK is ignored)
                truncated_text = result_text[:500] if len(result_text) > 500 else result_text
                await self._hooks.run(HookEvent(
                    event_type="SubagentStop",
                    session_id=ctx.session_id,
                    transcript_path=ctx.transcript_path,
                    subagent_id=info.subagent_id,
                    subagent_name=agent_name,
                    subagent_status="completed",
                    subagent_final_text=truncated_text,  # per D-14
                ))
                # NOTE: Return value of hooks.run() intentionally ignored for SubagentStop
                # per D-13. Even if a hook returns BLOCK, the subagent has already completed.

                # Broadcast completed event (SPAWN-18)
                if _on_tool_event:
                    _on_tool_event("subagent_event", {
                        "subagent_id": info.subagent_id,
                        "subagent_name": agent_name,
                        "event": "completed",
                        "detail": truncated_text[:100],
                    })

                # Write child transcript
                for msg in child_ctx.messages:
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    writer.append(msg.role, content)

                return ToolResult(
                    tool_use_id="",
                    content=result_text + merge_summary,
                )

            except Exception as exc:
                ctx.subagent_manager.fail(info.subagent_id, str(exc))

                # Fire SubagentStop with status "failed" (D-14)
                error_text = str(exc)[:500]
                await self._hooks.run(HookEvent(
                    event_type="SubagentStop",
                    session_id=ctx.session_id,
                    transcript_path=ctx.transcript_path,
                    subagent_id=info.subagent_id,
                    subagent_name=agent_name,
                    subagent_status="failed",
                    subagent_final_text=error_text,  # per D-14
                ))
                # D-13: BLOCK result ignored for SubagentStop

                # Broadcast failed event (SPAWN-18)
                if _on_tool_event:
                    _on_tool_event("subagent_event", {
                        "subagent_id": info.subagent_id,
                        "subagent_name": agent_name,
                        "event": "failed",
                        "detail": str(exc)[:100],
                    })

                return ToolResult(
                    tool_use_id="",
                    content=f"Subagent '{agent_name}' failed: {exc}",
                    is_error=True,
                )
        else:
            # 12. Background mode (SPAWN-11)
            info = ctx.subagent_manager.register(agent_name, task=None)

            # Set transcript path for child
            writer = create_subagent_transcript_writer(ctx.session_id, info.subagent_id)
            child_ctx.transcript_path = str(writer._path)

            manager = ctx.subagent_manager
            hooks = self._hooks
            session_id = ctx.session_id
            transcript_path = ctx.transcript_path
            session_registry = getattr(ctx, "_session_registry", None)
            parent_vars = ctx.vars  # fallback if no registry
            dataframes_specified = effective_dataframes
            on_tool_event = _on_tool_event

            async def _run_background() -> None:
                result_text = ""
                status = "completed"
                try:
                    result_text = await child_loop.run(full_prompt, child_ctx)

                    # Merge back DataFrames — safe for evicted sessions
                    merge_summary = ""
                    if dataframes_specified:
                        target_vars = parent_vars  # default: direct reference
                        if session_registry is not None:
                            live_session = session_registry.get(session_id)
                            if live_session is None:
                                logger.warning(
                                    "Parent session %s evicted, skipping DataFrame merge-back for %s",
                                    session_id, agent_name,
                                )
                                target_vars = None
                            else:
                                target_vars = live_session.ctx.vars
                        if target_vars is not None:
                            merge_summary = merge_back_dataframes(
                                target_vars, child_ctx.vars, agent_name, original_names,
                            )

                    manager.complete(info.subagent_id, result_text)
                    # D-08: notification for parent LLM
                    manager.add_notification(
                        f"[Subagent '{agent_name}' completed] "
                        f"{result_text[:200]}{merge_summary}"
                    )

                except asyncio.CancelledError:
                    status = "cancelled"
                    info.status = "cancelled"
                    raise

                except Exception as exc:
                    status = "failed"
                    result_text = str(exc)
                    manager.fail(info.subagent_id, str(exc))
                    manager.add_notification(
                        f"[Subagent '{agent_name}' failed] {exc}"
                    )

                finally:
                    # Fire SubagentStop hook event (D-14, D-13: BLOCK ignored)
                    final_text = result_text[:500] if len(result_text) > 500 else result_text
                    await hooks.run(HookEvent(
                        event_type="SubagentStop",
                        session_id=session_id,
                        transcript_path=transcript_path,
                        subagent_id=info.subagent_id,
                        subagent_name=agent_name,
                        subagent_status=status,
                        subagent_final_text=final_text,  # per D-14
                    ))
                    # D-13: BLOCK result ignored for SubagentStop

                    # Broadcast lifecycle event (SPAWN-18)
                    if on_tool_event:
                        on_tool_event("subagent_event", {
                            "subagent_id": info.subagent_id,
                            "subagent_name": agent_name,
                            "event": status,
                            "detail": final_text[:100],
                        })

                    # Write child transcript
                    for msg in child_ctx.messages:
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        writer.append(msg.role, content)

            task = asyncio.create_task(_run_background())
            # Update the registered info with the actual task
            info.task = task

            return ToolResult(
                tool_use_id="",
                content=(
                    f"Subagent '{agent_name}' launched in background "
                    f"(id: {info.subagent_id}). "
                    "Use agent_status to check progress."
                ),
            )
