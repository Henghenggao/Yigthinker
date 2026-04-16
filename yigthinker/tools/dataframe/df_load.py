from __future__ import annotations
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext


def _safe_path(
    source: str,
    ctx_settings: dict,
    attachments: set[Path] | None = None,
) -> tuple[Path, str | None]:
    """Return (resolved_path, error_msg). error_msg is None if safe.

    A path outside workspace_dir is accepted if it is present in the
    ``attachments`` allowlist (caller's contract: set entries are expected to
    be pre-resolved absolute paths). Used to let Teams/Feishu-downloaded temp
    files flow into df_load without widening workspace_dir globally.
    """
    workspace = Path(ctx_settings.get("workspace_dir", Path.cwd())).expanduser().resolve()
    raw_path = Path(source).expanduser()
    try:
        candidate = raw_path if raw_path.is_absolute() else workspace / raw_path
        resolved = candidate.resolve(strict=False)
    except Exception:
        return raw_path, f"Cannot resolve path: {source}"
    try:
        resolved.relative_to(workspace)
        return resolved, None
    except ValueError:
        if attachments and resolved in attachments:
            return resolved, None
        return resolved, (
            f"Access denied: '{source}' is outside the workspace directory "
            f"'{workspace}'. Use a relative path or configure workspace_dir in settings."
        )


_LOADERS = {
    ".csv": pd.read_csv,
    ".parquet": pd.read_parquet,
    ".json": pd.read_json,
    ".xlsx": pd.read_excel,
    ".xls": pd.read_excel,
}


class DfLoadInput(BaseModel):
    source: str
    var_name: str = "df1"
    sheet_name: str | None = None
    header: int | None = 0
    skiprows: int | None = None
    usecols: str | None = None


class DfLoadTool:
    name = "df_load"
    description = (
        "Load data from a file (CSV, Excel, Parquet, JSON) into a named DataFrame "
        "in the variable registry. Reference it in later tool calls by var_name. "
        "Set header=null for files without a header row. Use skiprows to skip "
        "metadata rows at the top. Use usecols to select specific columns (e.g. 'A:L'). "
        "For data files only. Do NOT use to load source code, configs, or free-form "
        "text — return those inline or use `artifact_write` instead."
    )
    input_schema = DfLoadInput

    async def execute(self, input: DfLoadInput, ctx: SessionContext) -> ToolResult:
        try:
            safe_path, err = _safe_path(
                input.source, ctx.settings, attachments=ctx.attachments
            )
            if err:
                return ToolResult(tool_use_id="", content=err, is_error=True)
            path = safe_path
            suffix = path.suffix.lower()
            loader = _LOADERS.get(suffix)
            if loader is None:
                return ToolResult(
                    tool_use_id="",
                    content=f"Unsupported file format '{suffix}'. Supported: {list(_LOADERS)}",
                    is_error=True,
                )

            kwargs = {}

            # Excel sheet enumeration: discover sheets before loading
            if suffix in (".xlsx", ".xls"):
                xls = pd.ExcelFile(path)
                sheets = xls.sheet_names

                if input.sheet_name and input.sheet_name not in sheets:
                    return ToolResult(
                        tool_use_id="",
                        content=f"Sheet '{input.sheet_name}' not found. Available sheets: {sheets}",
                        is_error=True,
                    )

                if not input.sheet_name and len(sheets) > 1:
                    return ToolResult(
                        tool_use_id="",
                        content={
                            "message": f"This Excel file has {len(sheets)} sheets. Specify sheet_name to load one.",
                            "available_sheets": sheets,
                        },
                    )

                # Single sheet or explicit sheet_name — proceed with loading
                if input.sheet_name:
                    kwargs["sheet_name"] = input.sheet_name
                else:
                    kwargs["sheet_name"] = sheets[0]

            # header, skiprows, usecols only supported by CSV and Excel loaders;
            # JSON and Parquet do not accept these parameters.
            if suffix in (".csv", ".xlsx", ".xls"):
                kwargs["header"] = input.header  # int or None
                if input.skiprows is not None:
                    kwargs["skiprows"] = input.skiprows
                if input.usecols is not None:
                    kwargs["usecols"] = input.usecols

            df = loader(path, **kwargs)
            ctx.vars.set(input.var_name, df)

            cm = ctx.context_manager
            return ToolResult(
                tool_use_id="",
                content={
                    "loaded": input.var_name,
                    "preview": cm.summarize_dataframe_result(df),
                },
            )
        except FileNotFoundError:
            return ToolResult(
                tool_use_id="",
                content=f"File not found: {input.source}",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
