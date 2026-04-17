"""artifact_write — persist free-form text (scripts, configs, markdown) as a
named file in the workspace.

This tool exists to close a gap observed in quick-260416-j3y: when the user
asks for a custom Python script (e.g. openpyxl-styled P&L sheet), the LLM has
no first-class "save this text" path and ends up stuffing source code into a
DataFrame via df_transform — slow, opaque, and prone to wall-clock timeouts.
See .planning/quick/260416-j3y-*/260416-j3y-PLAN.md.

Keep in mind:
- Content is a ``str`` field, so this writes UTF-8 text only. No binaries.
- Path safety reuses ``_safe_output_path`` from report_generate (workspace +
  attachments allowlist).
- Extension is pre-validated so the LLM cannot scatter arbitrary file types.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from yigthinker.session import SessionContext
from yigthinker.tools.reports.report_generate import _safe_output_path
from yigthinker.types import ToolResult

ALLOWED_EXTENSIONS: set[str] = {
    ".py", ".sql", ".md", ".txt",
    ".yaml", ".yml", ".json", ".csv",
    ".sh", ".ini", ".toml",
    ".html", ".xml",
}

# Cap on content size. 1 MiB is comfortably above any reasonable single-file
# script or config but small enough to prevent the LLM from dumping large data.
MAX_CONTENT_BYTES: int = 1 * 1024 * 1024


class ArtifactWriteInput(BaseModel):
    filename: str = Field(
        description=(
            "Relative path within the workspace (e.g. 'scripts/build_pl.py'). "
            f"Extension must be one of: {sorted(ALLOWED_EXTENSIONS)}."
        ),
    )
    content: str = Field(
        description="Full UTF-8 text content to write. Capped at 1 MiB.",
    )
    summary: str | None = Field(
        default=None,
        description="Optional one-line description shown to the user in IM cards.",
    )
    overwrite: bool = Field(
        default=False,
        description=(
            "If False (default), writing over an existing file fails. "
            "Set True only when the user explicitly asked to replace."
        ),
    )

    @field_validator("filename")
    @classmethod
    def _check_filename(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename must not be empty")
        suffix = Path(v).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"filename suffix {suffix!r} is not allowed. "
                f"Allowed: {sorted(ALLOWED_EXTENSIONS)}. "
                "Pick a supported text extension or reply inline."
            )
        return v


class ArtifactWriteTool:
    name = "artifact_write"
    description = (
        "Use this to save a free-form text artifact (Python/SQL/VBA scripts, "
        "YAML/JSON configs, Markdown docs, one-off CSVs from string content) "
        "as a named file in the workspace. Call this when the user asks for "
        "a script, a config, a snippet, or any text file — do NOT paste code "
        "inline and do NOT stuff text into a DataFrame via df_transform. "
        "The returned path is delivered to the user as a file card."
    )
    input_schema = ArtifactWriteInput

    async def execute(
        self, input: ArtifactWriteInput, ctx: SessionContext,
    ) -> ToolResult:
        # Size guard (fast, before path resolution)
        encoded = input.content.encode("utf-8")
        if len(encoded) > MAX_CONTENT_BYTES:
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Content too large: {len(encoded):,} bytes exceeds the "
                    f"{MAX_CONTENT_BYTES:,}-byte limit. Split the artifact or "
                    "use report_generate for tabular data."
                ),
                is_error=True,
            )

        # Path safety — share the existing workspace+attachments allowlist
        path, err = _safe_output_path(
            input.filename, ctx.settings, attachments=ctx.attachments,
        )
        if err:
            return ToolResult(tool_use_id="", content=err, is_error=True)

        if path.exists() and not input.overwrite:
            return ToolResult(
                tool_use_id="",
                content=(
                    f"File already exists: {path}. Set overwrite=True only if "
                    "the user explicitly asked to replace it."
                ),
                is_error=True,
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input.content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                tool_use_id="",
                content=f"Failed to write {path}: {exc}",
                is_error=True,
            )

        # Register in attachments so IM adapters can serve the file back later
        # (same pattern as report_generate's downstream consumers).
        ctx.attachments.add(path.resolve())

        return ToolResult(
            tool_use_id="",
            content={
                "kind": "file",
                "path": str(path),
                "filename": Path(input.filename).name,
                "bytes": len(encoded),
                "summary": input.summary,
            },
        )
