from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext

_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


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

    async def execute(self, input: ReportTemplateInput, ctx: SessionContext) -> ToolResult:
        if input.action == "list":
            templates = []
            if self._templates_dir.exists():
                for f in self._templates_dir.iterdir():
                    if f.suffix in (".j2", ".jinja2"):
                        name = f.name.replace(".xlsx.j2", "").replace(".j2", "")
                        templates.append({"name": name, "file": f.name})
            return ToolResult(tool_use_id="", content={"templates": templates})

        if input.action == "preview":
            if not input.name:
                return ToolResult(
                    tool_use_id="", content="'name' required for action='preview'", is_error=True
                )
            matches = list(self._templates_dir.glob(f"{input.name}*"))
            if not matches:
                return ToolResult(
                    tool_use_id="", content=f"Template '{input.name}' not found", is_error=True
                )
            return ToolResult(tool_use_id="", content={"name": input.name, "content": matches[0].read_text()})

        return ToolResult(tool_use_id="", content=f"Unknown action '{input.action}'", is_error=True)
