from __future__ import annotations
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext

_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEMPLATE_SUFFIXES = (".xlsx.j2", ".j2", ".jinja2")


def _template_name(path: Path) -> str:
    file_name = path.name
    for suffix in _TEMPLATE_SUFFIXES:
        if file_name.endswith(suffix):
            return file_name[: -len(suffix)]
    return path.stem


def _is_safe_template_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if any(ch in name for ch in ("*", "?", "[", "]")):
        return False
    return (
        PurePosixPath(name).name == name
        and PureWindowsPath(name).name == name
    )


class ReportTemplateInput(BaseModel):
    action: Literal["list", "preview"] = "list"
    name: str | None = None


class ReportTemplateTool:
    name = "report_template"
    description = (
        "List and preview available report templates. "
        "Templates are Jinja2 files in the project's templates/ directory."
    )
    input_schema = ReportTemplateInput

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._templates_dir = templates_dir or _DEFAULT_TEMPLATES_DIR

    def _iter_templates(self) -> list[Path]:
        if not self._templates_dir.exists():
            return []
        return sorted(
            [
                path for path in self._templates_dir.iterdir()
                if any(path.name.endswith(suffix) for suffix in _TEMPLATE_SUFFIXES)
            ],
            key=lambda path: path.name,
        )

    async def execute(self, input: ReportTemplateInput, ctx: SessionContext) -> ToolResult:
        if input.action == "list":
            templates = []
            for template_path in self._iter_templates():
                templates.append({"name": _template_name(template_path), "file": template_path.name})
            return ToolResult(tool_use_id="", content={"templates": templates})

        if input.action == "preview":
            if not input.name:
                return ToolResult(
                    tool_use_id="", content="'name' required for action='preview'", is_error=True
                )
            if not _is_safe_template_name(input.name):
                return ToolResult(
                    tool_use_id="",
                    content=f"Invalid template name '{input.name}'",
                    is_error=True,
                )
            matches = [
                path for path in self._iter_templates()
                if _template_name(path) == input.name
            ]
            if not matches:
                return ToolResult(
                    tool_use_id="", content=f"Template '{input.name}' not found", is_error=True
                )
            if len(matches) > 1:
                return ToolResult(
                    tool_use_id="",
                    content=f"Template name '{input.name}' is ambiguous",
                    is_error=True,
                )
            return ToolResult(
                tool_use_id="",
                content={"name": input.name, "content": matches[0].read_text(encoding="utf-8")},
            )

        return ToolResult(tool_use_id="", content=f"Unknown action '{input.action}'", is_error=True)
