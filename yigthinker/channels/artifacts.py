from __future__ import annotations

from typing import Any


def structured_artifact_from_tool_result(raw_content: Any) -> dict[str, Any] | None:
    """Extract a renderable IM artifact from a raw tool result payload."""
    if not isinstance(raw_content, dict):
        return None

    chart_name = raw_content.get("chart_name")
    chart_json = raw_content.get("chart_json")
    if isinstance(chart_name, str) and isinstance(chart_json, str):
        return {
            "kind": "chart",
            "chart_name": chart_name,
            "chart_json": chart_json,
        }

    # artifact_write returns {"kind": "file", ...} — see
    # .planning/quick/260416-j3y-artifact-write-timeout-fix/260416-j3y-PLAN.md.
    if raw_content.get("kind") == "file":
        filename = raw_content.get("filename")
        path = raw_content.get("path")
        if isinstance(filename, str) and isinstance(path, str):
            return {
                "kind": "file",
                "filename": filename,
                "path": path,
                "bytes": int(raw_content.get("bytes") or 0),
                "summary": raw_content.get("summary"),
            }

    preview = raw_content.get("preview", raw_content)
    if not isinstance(preview, dict):
        return None

    preview_type = preview.get("type")
    if preview_type == "dataframe":
        records = preview.get("data", [])
        if not isinstance(records, list):
            return None
        columns = list(records[0].keys()) if records else []
        rows = [[record.get(col, "") for col in columns] for record in records[:10]]
        total_rows = len(records)
    elif preview_type == "dataframe_summary":
        columns = list(preview.get("columns") or [])
        sample = preview.get("sample", [])
        if not isinstance(sample, list):
            return None
        rows = [[record.get(col, "") for col in columns] for record in sample[:10]]
        total_rows = int(preview.get("total_rows") or len(sample))
    else:
        return None

    return {
        "kind": "table",
        "title": raw_content.get("stored_as") or raw_content.get("loaded") or "Data Preview",
        "columns": columns,
        "rows": rows,
        "total_rows": total_rows,
    }


def choose_best_artifact(artifacts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Ranking: most recent chart > most recent file > most recent anything.

    File artifacts (artifact_write) outrank table previews because a saved script
    or report is almost always the concrete thing the user asked for, whereas a
    DataFrame preview is usually an intermediate step.
    """
    if not artifacts:
        return None

    charts = [artifact for artifact in artifacts if artifact.get("kind") == "chart"]
    if charts:
        return charts[-1]
    files = [artifact for artifact in artifacts if artifact.get("kind") == "file"]
    if files:
        return files[-1]
    return artifacts[-1]
