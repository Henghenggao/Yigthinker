"""Workflow generation tool for creating self-contained Python script packages.

Connects WorkflowRegistry (storage) and TemplateEngine (rendering) into a tool
the LLM can call. Supports explicit step definitions and from_history extraction
from conversation tool_use messages.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from yigthinker.session import SessionContext
from yigthinker.tools.workflow.registry import WorkflowRegistry
from yigthinker.tools.workflow.template_engine import TemplateEngine
from yigthinker.types import Message, ToolResult

# Tools that can be automated into workflow scripts
_AUTOMATABLE_TOOLS = {
    "sql_query", "df_load", "df_transform", "df_merge",
    "chart_create", "report_generate", "finance_calculate",
    "finance_analyze", "finance_validate", "finance_budget",
}

# Connection-related param keys
_CONNECTION_KEYS = {"connection", "connection_string", "db", "database", "dsn"}


class WorkflowStep(BaseModel):
    id: str
    action: str
    params: dict[str, Any] = {}
    inputs: list[str] = []
    rpa_action: str | None = None


class WorkflowGenerateInput(BaseModel):
    name: str
    description: str
    steps: list[WorkflowStep] = []
    from_history: bool = False
    target: Literal["python", "power_automate", "uipath"] = "python"
    schedule: str | None = None
    update_of: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_\-]{1,64}", v):
            raise ValueError(
                "workflow name must be alphanumeric, underscore or hyphen, max 64 chars"
            )
        return v


def _extract_steps_from_history(messages: list[Message]) -> list[WorkflowStep]:
    """Extract automatable steps from conversation tool_use messages.

    Scans assistant messages for tool_use blocks, checks corresponding
    tool_result in the next user message for errors, and builds a step list.
    """
    steps: list[WorkflowStep] = []
    step_idx = 0

    for i, msg in enumerate(messages):
        if msg.role != "assistant" or not isinstance(msg.content, list):
            continue

        for block in msg.content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            tool_name = block.get("name", "")
            if tool_name not in _AUTOMATABLE_TOOLS:
                continue

            tool_use_id = block.get("id", "")

            # Check corresponding tool_result in the next user message
            is_error = False
            if i + 1 < len(messages):
                next_msg = messages[i + 1]
                if next_msg.role == "user" and isinstance(next_msg.content, list):
                    for result_block in next_msg.content:
                        if (
                            isinstance(result_block, dict)
                            and result_block.get("type") == "tool_result"
                            and result_block.get("tool_use_id") == tool_use_id
                        ):
                            if result_block.get("is_error"):
                                is_error = True
                            break

            if is_error:
                continue

            step_id = f"step_{step_idx + 1}"
            inputs = [f"step_{step_idx}"] if step_idx > 0 else []
            steps.append(WorkflowStep(
                id=step_id,
                action=tool_name,
                params=block.get("input", {}),
                inputs=inputs,
            ))
            step_idx += 1

    return steps


def _normalize_step_params(params: dict[str, Any]) -> dict[str, Any]:
    """Coerce common LLM mistakes in step parameters."""
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if not isinstance(value, str):
            normalized[key] = value
            continue

        if value == "None":
            normalized[key] = None
        elif value == "True":
            normalized[key] = True
        elif value == "False":
            normalized[key] = False
        else:
            # Try int first, then float
            try:
                normalized[key] = int(value)
                continue
            except ValueError:
                pass
            try:
                normalized[key] = float(value)
                continue
            except ValueError:
                pass
            normalized[key] = value
    return normalized


def _validate_schedule(schedule: str) -> None:
    """Validate cron expression at generate time (D-16)."""
    try:
        from croniter import croniter
        croniter(schedule)
    except (ValueError, KeyError) as e:
        raise ValueError(f"Invalid cron expression '{schedule}': {e}")


def _extract_connections(steps: list[WorkflowStep]) -> list[str]:
    """Extract connection names from step parameters."""
    connections: list[str] = []
    seen: set[str] = set()
    for step in steps:
        for key in _CONNECTION_KEYS:
            val = step.params.get(key)
            if val and isinstance(val, str) and val not in seen:
                connections.append(val)
                seen.add(val)
    return connections


class WorkflowGenerateTool:
    name = "workflow_generate"
    description = (
        "Generate a self-contained Python script from analysis step definitions. "
        "Supports python, power_automate, and uipath targets. "
        "Set from_history=True to auto-extract steps from recent tool calls. "
        "Set update_of to create a new version of an existing workflow."
    )
    input_schema = WorkflowGenerateInput

    def __init__(self, registry: WorkflowRegistry) -> None:
        self._registry = registry
        self._engine = TemplateEngine()

    async def execute(
        self, input: WorkflowGenerateInput, ctx: SessionContext,
    ) -> ToolResult:
        try:
            return await self._do_execute(input, ctx)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

    async def _do_execute(
        self, input: WorkflowGenerateInput, ctx: SessionContext,
    ) -> ToolResult:
        # Step resolution
        if input.from_history and not input.steps:
            steps = _extract_steps_from_history(ctx.messages)
            if not steps:
                return ToolResult(
                    tool_use_id="",
                    content="No automatable tool calls found in conversation history",
                    is_error=True,
                )
        else:
            steps = list(input.steps)

        if not steps:
            return ToolResult(
                tool_use_id="",
                content="No steps provided",
                is_error=True,
            )

        # Normalize params
        for step in steps:
            step.params = _normalize_step_params(step.params)

        # Schedule validation
        if input.schedule:
            try:
                _validate_schedule(input.schedule)
            except ValueError as e:
                return ToolResult(
                    tool_use_id="", content=str(e), is_error=True,
                )

        # Compute dependencies and connections
        step_dicts = [s.model_dump() for s in steps]
        deps = TemplateEngine.compute_dependencies(step_dicts)
        connections = _extract_connections(steps)

        # Determine version
        if input.update_of:
            version = self._registry.next_version(input.update_of)
        else:
            version = self._registry.next_version(input.name)

        # Build template context
        context = {
            "workflow_name": input.name,
            "description": input.description,
            "steps": step_dicts,
            "version": version,
            "workflow_version": version,  # CORR-01: checkpoint_utils template reads this
            "schedule": input.schedule,
            "connections": connections,
            "dependencies": deps,
            "checkpoint_ids": [s.id for s in steps],
            "max_retries": 3,
            "gateway_url": None,
        }

        # Render all files
        version_data = {
            "main.py": self._engine.render(input.target, context),
            "checkpoint_utils.py": self._engine.render_checkpoint_utils(context),
            "config.yaml": self._engine.render_config(context),
            "requirements.txt": self._engine.render_requirements(context),
        }

        # Create or update in registry
        if input.update_of:
            version_dir = self._registry.update(
                input.update_of,
                input.description,
                version_data,
                changelog=f"Updated: {input.description}",
            )
        else:
            version_dir = self._registry.create(
                input.name, input.description, version_data,
            )

        # Write .gitignore in workflow dir (parent of version dir)
        workflow_dir = version_dir.parent
        gitignore_path = workflow_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(
                "config.yaml\n*.tmp\n.lock\n",
                encoding="utf-8",
            )

        return ToolResult(
            tool_use_id="",
            content={
                "output_dir": str(version_dir),
                "version": version,
                "files": list(version_data.keys()),
                "workflow_name": input.name,
                "target": input.target,
            },
        )
