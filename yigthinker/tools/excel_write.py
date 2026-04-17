"""excel_write — produce a formatted ``.xlsx`` file from a registered DataFrame,
with optional base-file modify mode and minimal named styles.

This closes a gap observed in quick-260416-kyn: when the user asks for a
formatted P&L / report spreadsheet with section headers, subtotals, frozen
panes, and accounting number formats, the LLM has no first-class "write me a
styled xlsx" path and either (a) stuffs openpyxl source into df_transform or
(b) falls back to report_generate which only does bare header formatting.

Design choices (see ``.planning/quick/260416-kyn-.../260416-kyn-CONTEXT.md``):

- Output lands under ``~/.yigthinker/artifacts/<session_id>/`` (not the
  workspace), so every session has an isolated artifact bucket that the
  gateway's 7-day sweeper owns. Callers can override the filename, not the
  directory.
- ``base_file`` support: if set, the tool opens the base xlsx, adds/replaces
  ONE sheet, preserves every other sheet's formatting via openpyxl's native
  in-memory object graph, and writes the mutated workbook out under a
  deterministic new name. We never mutate the source file.
- Named styles are prefixed ``yt_`` to avoid collisions with user styles
  already present in the base workbook. Registering a named style that
  already exists raises ``ValueError`` in openpyxl ≥3.1, so we guard.
- ``row_style_map`` uses 0-based DataFrame row indices; row 0 in the map is
  the first data row (Excel row 2, since row 1 is the header).

Path safety reuses ``_safe_output_path`` from report_generate — the output
dir is under ``Path.home()`` but the attachments allowlist accepts explicit
registration so downstream adapters (e.g. Teams signed-URL delivery) can
both read from and serve the produced file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from yigthinker.session import SessionContext
from yigthinker.types import DryRunReceipt, ToolResult

# ── Named-style registry ─────────────────────────────────────────────────
#
# Friendly names the LLM may use in ``row_style_map``. The rendered style
# name in the workbook is prefixed ``yt_`` to avoid colliding with user
# styles that might already exist in a base file.

_KNOWN_STYLE_NAMES: frozenset[str] = frozenset(
    {"section_header", "subtotal", "italic", "percent", "alt_row_fill"}
)

# Excel sheet-name rules (openpyxl enforces these but raises late — we
# reject eagerly so the LLM gets a clear schema-level error).
_FORBIDDEN_SHEET_CHARS: frozenset[str] = frozenset("[]:*?/\\")
_MAX_SHEET_NAME_LEN = 31

# Target file-size ceiling. openpyxl will happily build multi-GB workbooks
# and we do not want a runaway tool call to fill the disk.
_MAX_OUTPUT_BYTES = 50 * 1024 * 1024  # 50 MiB


class ExcelWriteInput(BaseModel):
    input_var: str = Field(
        description=(
            "Name of a registered DataFrame variable (see ``ctx.vars``). "
            "The DataFrame is written starting at cell A1 with headers on row 1."
        ),
    )
    sheet_name: str = Field(
        description=(
            "Target sheet name. Max 31 characters; must not contain any of "
            "``[ ] : * ? / \\``."
        ),
    )
    base_file: str | None = Field(
        default=None,
        description=(
            "Optional path to an existing ``.xlsx`` workbook to start from. "
            "Other sheets are preserved verbatim (formatting, formulas, "
            "merged cells). Must be registered in ``ctx.attachments`` or "
            "live inside the workspace."
        ),
    )
    overwrite_sheet: bool = Field(
        default=False,
        description=(
            "When ``base_file`` is set and ``sheet_name`` already exists in "
            "the base workbook: if False (default) the tool errors out; if "
            "True the existing sheet is dropped and replaced."
        ),
    )
    output_filename: str | None = Field(
        default=None,
        description=(
            "Basename (no directory) for the produced file. Defaults to "
            "``<base_stem>_<sheet_name>.xlsx`` in modify mode or "
            "``<sheet_name>.xlsx`` in new-file mode."
        ),
    )
    freeze_pane: str | None = Field(
        default=None,
        description=(
            "Cell reference (e.g. ``'B2'``) marking the top-left cell of "
            "the scrollable region. Use ``'A2'`` to freeze the header row."
        ),
    )
    number_format: dict[str, str] | None = Field(
        default=None,
        description=(
            "Map column-name → openpyxl number-format code, e.g. "
            "``{'Revenue': '#,##0;[Red]-#,##0', 'Margin': '0.0%'}``."
        ),
    )
    row_style_map: dict[int, str] | None = Field(
        default=None,
        description=(
            "Map 0-based DataFrame row index → named style. Valid names: "
            f"{sorted(_KNOWN_STYLE_NAMES)}."
        ),
    )
    summary: str | None = Field(
        default=None,
        description="Optional one-liner shown on the IM card.",
    )

    @field_validator("sheet_name")
    @classmethod
    def _check_sheet_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("sheet_name must not be empty")
        if len(v) > _MAX_SHEET_NAME_LEN:
            raise ValueError(
                f"sheet_name too long ({len(v)} chars). Excel caps at "
                f"{_MAX_SHEET_NAME_LEN}."
            )
        bad = sorted(ch for ch in v if ch in _FORBIDDEN_SHEET_CHARS)
        if bad:
            raise ValueError(
                f"sheet_name contains forbidden character(s) {bad!r}. "
                "Excel disallows any of [ ] : * ? / \\."
            )
        return v


class ExcelWriteTool:
    name = "excel_write"
    description = (
        "Write a formatted ``.xlsx`` file from a registered DataFrame with "
        "named styles (section_header / subtotal / italic / percent / "
        "alt_row_fill), per-column number formats, and optional frozen "
        "panes. Supports ``base_file`` modify mode: open an existing "
        "workbook, add or replace ONE sheet, and preserve every other "
        "sheet's formatting. Use THIS instead of df_transform when the "
        "user asks for a formatted xlsx — df_transform cannot style "
        "cells and report_generate only applies bare header formatting. "
        "Output lands under the session artifacts dir and is auto-"
        "registered in ``ctx.attachments`` for IM delivery."
    )
    input_schema = ExcelWriteInput

    async def execute(
        self, input: ExcelWriteInput, ctx: SessionContext,
    ) -> ToolResult:
        if ctx.dry_run:
            return ToolResult(
                tool_use_id="",
                content=DryRunReceipt(
                    tool_name=self.name,
                    summary=(
                        f"Would write Excel sheet '{input.sheet_name}' "
                        f"from {input.input_var}"
                        + (f" into base_file {input.base_file}"
                           if input.base_file else "")
                    ),
                    details={"input": input.model_dump()},
                ),
            )

        # ── 1. Resolve the DataFrame ─────────────────────────────────
        try:
            df = ctx.vars.get(input.input_var)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        try:
            import pandas as pd  # local — pandas is a core dep
        except ImportError as exc:  # pragma: no cover — core dep
            return ToolResult(
                tool_use_id="", content=f"pandas not available: {exc}",
                is_error=True,
            )
        if not isinstance(df, pd.DataFrame):
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Variable '{input.input_var}' is a {type(df).__name__}, "
                    "not a DataFrame. excel_write expects a tabular input."
                ),
                is_error=True,
            )

        # ── 2. Validate row_style_map friendly names early ───────────
        if input.row_style_map:
            unknown = sorted(
                set(input.row_style_map.values()) - _KNOWN_STYLE_NAMES
            )
            if unknown:
                return ToolResult(
                    tool_use_id="",
                    content=(
                        f"Unknown style name(s) {unknown!r}. "
                        f"Valid: {sorted(_KNOWN_STYLE_NAMES)}."
                    ),
                    is_error=True,
                )

        # ── 3. Validate & open base_file (if any) ────────────────────
        base_wb = None
        base_stem: str | None = None
        if input.base_file is not None:
            # Import locally so test_rejects_invalid_sheet_name_* don't pay
            # the openpyxl import cost.
            from yigthinker.tools.reports.report_generate import (
                _safe_output_path,
            )
            base_resolved, err = _safe_output_path(
                input.base_file, ctx.settings, attachments=ctx.attachments,
            )
            if err:
                return ToolResult(tool_use_id="", content=err, is_error=True)
            if not base_resolved.exists():
                return ToolResult(
                    tool_use_id="",
                    content=f"base_file does not exist: {base_resolved}",
                    is_error=True,
                )
            if base_resolved.suffix.lower() == ".xlsm":
                return ToolResult(
                    tool_use_id="",
                    content=(
                        "base_file is an .xlsm (macro-enabled) workbook. "
                        "excel_write refuses to open macro files — re-save "
                        "as plain .xlsx first."
                    ),
                    is_error=True,
                )
            if base_resolved.suffix.lower() != ".xlsx":
                return ToolResult(
                    tool_use_id="",
                    content=(
                        f"base_file must be .xlsx, got "
                        f"{base_resolved.suffix!r}."
                    ),
                    is_error=True,
                )

            import openpyxl
            try:
                base_wb = openpyxl.load_workbook(filename=str(base_resolved))
            except Exception as exc:  # pragma: no cover — openpyxl raises many
                return ToolResult(
                    tool_use_id="",
                    content=f"Failed to open base_file: {exc}",
                    is_error=True,
                )

            # Conflict check against existing sheet
            if input.sheet_name in base_wb.sheetnames and not input.overwrite_sheet:
                return ToolResult(
                    tool_use_id="",
                    content=(
                        f"Sheet '{input.sheet_name}' already exists in "
                        f"{base_resolved.name}. Pass overwrite_sheet=True "
                        "to replace it, or pick a different sheet_name."
                    ),
                    is_error=True,
                )
            base_stem = base_resolved.stem

        # ── 4. Resolve output path ───────────────────────────────────
        out_dir = _artifacts_dir(ctx)
        out_dir.mkdir(parents=True, exist_ok=True)

        if input.output_filename:
            # Basename only — no slashes, no parent escapes.
            safe_name = Path(input.output_filename).name
            if not safe_name.lower().endswith(".xlsx"):
                safe_name = f"{safe_name}.xlsx"
        elif base_stem is not None:
            safe_name = f"{base_stem}_{input.sheet_name}.xlsx"
        else:
            safe_name = f"{input.sheet_name}.xlsx"

        out_path = (out_dir / safe_name).resolve()

        # ── 5. Build / mutate the workbook ───────────────────────────
        import openpyxl

        if base_wb is not None:
            wb = base_wb
            if input.sheet_name in wb.sheetnames:
                # overwrite_sheet is True (we short-circuited earlier if not).
                del wb[input.sheet_name]
            ws = wb.create_sheet(title=input.sheet_name)
        else:
            wb = openpyxl.Workbook()
            default_ws = wb.active
            default_ws.title = input.sheet_name
            ws = default_ws

        # Register named styles (idempotent — re-registering raises ValueError
        # in openpyxl ≥3.1 so we guard by checking wb.named_styles).
        _register_named_styles(wb)

        # ── 6. Write the DataFrame (headers row 1, data row 2+) ──────
        headers = [str(c) for c in df.columns]
        for col_idx, header in enumerate(headers, start=1):
            ws.cell(row=1, column=col_idx, value=header)

        for row_idx, (_, row) in enumerate(df.iterrows()):
            excel_row = row_idx + 2  # +1 for 1-based, +1 for header row
            for col_idx, value in enumerate(row.tolist(), start=1):
                cell = ws.cell(row=excel_row, column=col_idx)
                cell.value = _coerce_value(value)

        # ── 7. Apply per-column number formats ───────────────────────
        if input.number_format:
            header_to_col = {h: i + 1 for i, h in enumerate(headers)}
            data_row_count = len(df.index)
            for col_name, fmt in input.number_format.items():
                col_idx = header_to_col.get(col_name)
                if col_idx is None:
                    continue  # silent — the LLM sometimes names optional cols
                for r in range(2, data_row_count + 2):
                    ws.cell(row=r, column=col_idx).number_format = fmt

        # ── 8. Apply row styles ──────────────────────────────────────
        if input.row_style_map:
            col_count = max(1, len(headers))
            for df_row, friendly in input.row_style_map.items():
                excel_row = df_row + 2  # 0-based DF → Excel data row
                style_name = f"yt_{friendly}"
                if style_name not in wb.named_styles:
                    continue  # defensive — validated above
                for col_idx in range(1, col_count + 1):
                    ws.cell(row=excel_row, column=col_idx).style = style_name

        # ── 9. Freeze panes ──────────────────────────────────────────
        if input.freeze_pane:
            ws.freeze_panes = input.freeze_pane

        # ── 10. Save ─────────────────────────────────────────────────
        try:
            wb.save(str(out_path))
        except Exception as exc:  # pragma: no cover — disk / perm errors
            return ToolResult(
                tool_use_id="",
                content=f"Failed to save {out_path}: {exc}",
                is_error=True,
            )

        try:
            size_bytes = out_path.stat().st_size
        except OSError:
            size_bytes = 0
        if size_bytes > _MAX_OUTPUT_BYTES:
            # Unlink the oversized file to avoid leaking disk — the LLM
            # should either slim the DF or use report_generate/csv.
            out_path.unlink(missing_ok=True)
            return ToolResult(
                tool_use_id="",
                content=(
                    f"Output exceeded {_MAX_OUTPUT_BYTES:,}-byte cap "
                    f"({size_bytes:,} bytes). Trim the DataFrame or split."
                ),
                is_error=True,
            )

        # Register so IM adapters can surface / serve the file.
        ctx.attachments.add(out_path)

        return ToolResult(
            tool_use_id="",
            content={
                "kind": "file",
                "path": str(out_path),
                "filename": out_path.name,
                "bytes": size_bytes,
                "summary": input.summary,
                "mime_type": (
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
            },
        )


# ── Module-private helpers ───────────────────────────────────────────────


def _artifacts_dir(ctx: SessionContext) -> Path:
    """Return ``~/.yigthinker/artifacts/<session_id>/`` for this session."""
    return Path.home() / ".yigthinker" / "artifacts" / ctx.session_id


def _coerce_value(value: Any) -> Any:
    """Convert pandas sentinel values to something openpyxl accepts.

    openpyxl rejects ``pd.NaT`` and silently mis-writes numpy scalars that
    pandas returns from ``DataFrame.iterrows()``. Round-trip via Python
    scalars for safety.
    """
    try:
        import pandas as pd  # noqa: WPS433
        if pd.isna(value):
            return None
    except Exception:
        pass
    # numpy scalar → Python scalar
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            return value
    return value


def _register_named_styles(wb: Any) -> None:
    """Register the minimal ``yt_*`` named style set on the workbook.

    openpyxl raises ``ValueError("Style ... exists already")`` if you add
    the same NamedStyle twice — which happens when the base workbook was
    itself produced by a prior excel_write call. We guard by checking
    ``wb.named_styles`` (the list-of-names view).
    """
    from openpyxl.styles import Alignment, Font, NamedStyle, PatternFill

    existing = set(wb.named_styles)

    styles: dict[str, NamedStyle] = {}

    # section_header — bold, light-grey fill, left aligned
    styles["yt_section_header"] = NamedStyle(
        name="yt_section_header",
        font=Font(bold=True),
        fill=PatternFill("solid", fgColor="E7E6E6"),
        alignment=Alignment(horizontal="left", vertical="center"),
    )

    # subtotal — bold, top-border feel via font + italic off
    styles["yt_subtotal"] = NamedStyle(
        name="yt_subtotal",
        font=Font(bold=True),
    )

    # italic — for footnote / commentary rows
    styles["yt_italic"] = NamedStyle(
        name="yt_italic",
        font=Font(italic=True),
    )

    # percent — number_format for percentage cells
    styles["yt_percent"] = NamedStyle(
        name="yt_percent",
        number_format="0.0%",
    )

    # alt_row_fill — subtle zebra striping
    styles["yt_alt_row_fill"] = NamedStyle(
        name="yt_alt_row_fill",
        fill=PatternFill("solid", fgColor="F2F2F2"),
    )

    for name, ns in styles.items():
        if name in existing:
            continue
        try:
            wb.add_named_style(ns)
        except ValueError:
            # Race: another code path added the style between our check
            # and the add. Safe to ignore.
            continue
