"""Translate Plotly JSON to VChart spec for Feishu native rendering."""
from __future__ import annotations

import base64
import json
from typing import Any

# Plotly trace type -> VChart series type
_TYPE_MAP: dict[str, str] = {
    "bar": "bar",
    "scatter": "line",  # Plotly scatter with mode=lines is a line chart
    "scattergl": "line",
    "pie": "pie",
    "histogram": "bar",
    "waterfall": "waterfall",
    "funnel": "funnel",
}

# Recent Plotly versions serialize numeric arrays as binary objects of the
# form {"dtype": "i1", "bdata": "<base64>"} instead of plain JSON lists.
# Map dtype codes to struct format chars + element size.
_DTYPE_MAP: dict[str, tuple[str, int]] = {
    "i1": ("b", 1), "u1": ("B", 1),
    "i2": ("h", 2), "u2": ("H", 2),
    "i4": ("i", 4), "u4": ("I", 4),
    "i8": ("q", 8), "u8": ("Q", 8),
    "f4": ("f", 4), "f8": ("d", 8),
}


def _coerce_array(value: Any) -> list:
    """Normalize a Plotly array field to a plain Python list.

    Handles both plain lists and the base64-encoded
    {"dtype": ..., "bdata": ...} form introduced in recent Plotly versions.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "bdata" in value and "dtype" in value:
        import struct
        dtype = value["dtype"]
        raw = base64.b64decode(value["bdata"])
        fmt_info = _DTYPE_MAP.get(dtype)
        if fmt_info is None:
            return []
        fmt_char, size = fmt_info
        count = len(raw) // size
        return list(struct.unpack(f"<{count}{fmt_char}", raw))
    return list(value) if hasattr(value, "__iter__") else []


def plotly_to_vchart(fig_json: str) -> dict[str, Any]:
    """Convert a Plotly figure JSON string to a VChart spec dict.

    Supports: bar, line/scatter, pie, histogram, waterfall.
    Unsupported trace types fall back to bar.
    """
    fig = json.loads(fig_json)
    traces = fig.get("data", [])
    layout = fig.get("layout", {})

    if not traces:
        return {"type": "common", "series": [], "data": [{"values": []}]}

    first_trace = traces[0]
    plotly_type = first_trace.get("type", "bar")
    vchart_type = _TYPE_MAP.get(plotly_type, "bar")

    if vchart_type == "pie":
        return _translate_pie(traces, layout)

    return _translate_cartesian(traces, layout, vchart_type)


def _translate_cartesian(traces: list[dict], layout: dict, default_type: str) -> dict[str, Any]:
    """Translate Cartesian (x/y) chart types."""
    all_values: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []

    for i, trace in enumerate(traces):
        vchart_type = _TYPE_MAP.get(trace.get("type", ""), default_type)
        x_vals = _coerce_array(trace.get("x"))
        y_vals = _coerce_array(trace.get("y"))
        trace_name = trace.get("name", f"series_{i}")

        for x, y in zip(x_vals, y_vals):
            all_values.append({"x": str(x), "y": y, "series": trace_name})

        series.append({
            "type": vchart_type,
            "xField": "x",
            "yField": "y",
            "seriesField": "series" if len(traces) > 1 else None,
        })

    spec: dict[str, Any] = {
        "type": "common",
        "data": [{"id": "data", "values": all_values}],
        "series": series,
    }

    title = layout.get("title", {})
    if isinstance(title, dict) and title.get("text"):
        spec["title"] = {"text": title["text"]}
    elif isinstance(title, str) and title:
        spec["title"] = {"text": title}

    return spec


def _translate_pie(traces: list[dict], layout: dict) -> dict[str, Any]:
    """Translate pie chart."""
    trace = traces[0]
    labels = _coerce_array(trace.get("labels"))
    values = _coerce_array(trace.get("values"))

    data_values = [{"category": str(l), "value": v} for l, v in zip(labels, values)]

    spec: dict[str, Any] = {
        "type": "common",
        "data": [{"id": "data", "values": data_values}],
        "series": [{"type": "pie", "categoryField": "category", "valueField": "value"}],
    }

    title = layout.get("title", {})
    if isinstance(title, dict) and title.get("text"):
        spec["title"] = {"text": title["text"]}
    elif isinstance(title, str) and title:
        spec["title"] = {"text": title}

    return spec
