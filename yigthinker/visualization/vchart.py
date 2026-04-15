"""Translate Plotly JSON to VChart spec for Feishu native rendering."""
from __future__ import annotations

import base64
import json
from typing import Any

# Plotly trace type -> VChart series type
_TYPE_MAP: dict[str, str] = {
    "bar": "bar",
    "scatter": "scatter",  # mode-aware: lines→line, markers→scatter (handled below)
    "scattergl": "scatter",
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


def _vchart_type_for_scatter(trace: dict) -> str:
    """Resolve VChart series type from a Plotly scatter trace.

    Plotly scatter with mode containing 'lines' is a line chart; one with
    mode='markers' (the default) is a scatter plot. Mixed modes (lines+markers)
    map to line since the connecting line is the distinguishing element.
    """
    mode = trace.get("mode", "lines")
    if "lines" in mode:
        return "line"
    return "scatter"


def plotly_to_vchart(fig_json: str) -> dict[str, Any]:
    """Convert a Plotly figure JSON string to a VChart spec dict.

    Supports: bar, line/scatter, pie, histogram, waterfall, funnel.
    Raises ValueError for trace types with no supported VChart equivalent.
    """
    fig = json.loads(fig_json)
    traces = fig.get("data", [])
    layout = fig.get("layout", {})

    if not traces:
        return {"type": "common", "series": [], "data": [{"values": []}]}

    first_trace = traces[0]
    plotly_type = first_trace.get("type", "bar")

    if plotly_type in ("scatter", "scattergl"):
        vchart_type = _vchart_type_for_scatter(first_trace)
    else:
        vchart_type = _TYPE_MAP.get(plotly_type)
        if vchart_type is None:
            raise ValueError(
                f"Unsupported Plotly trace type '{plotly_type}' for VChart translation. "
                f"Supported: {list(_TYPE_MAP)}"
            )

    if vchart_type == "pie":
        return _translate_pie(traces, layout)

    if vchart_type == "funnel":
        return _translate_funnel(traces, layout)

    if vchart_type == "waterfall":
        return _translate_waterfall(traces, layout)

    return _translate_cartesian(traces, layout, vchart_type)


def _translate_cartesian(traces: list[dict], layout: dict, default_type: str) -> dict[str, Any]:
    """Translate Cartesian (x/y) chart types."""
    all_values: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []

    for i, trace in enumerate(traces):
        plotly_type = trace.get("type", "")
        if plotly_type in ("scatter", "scattergl"):
            vchart_type = _vchart_type_for_scatter(trace)
        else:
            vchart_type = _TYPE_MAP.get(plotly_type, default_type)

        x_vals = _coerce_array(trace.get("x"))
        y_vals = _coerce_array(trace.get("y"))
        trace_name = trace.get("name", f"series_{i}")

        if len(x_vals) != len(y_vals):
            import logging
            logging.getLogger(__name__).warning(
                "VChart translation: trace '%s' has mismatched x/y lengths (%d vs %d); "
                "extra values will be dropped.",
                trace_name, len(x_vals), len(y_vals),
            )

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


def _translate_funnel(traces: list[dict], layout: dict) -> dict[str, Any]:
    """Translate funnel chart. Plotly funnel traces use 'values' and 'labels'."""
    trace = traces[0]
    labels = _coerce_array(trace.get("labels") or trace.get("y"))
    values = _coerce_array(trace.get("values") or trace.get("x"))

    data_values = [{"category": str(l), "value": v} for l, v in zip(labels, values)]

    spec: dict[str, Any] = {
        "type": "common",
        "data": [{"id": "data", "values": data_values}],
        "series": [{"type": "funnel", "categoryField": "category", "valueField": "value"}],
    }

    title = layout.get("title", {})
    if isinstance(title, dict) and title.get("text"):
        spec["title"] = {"text": title["text"]}
    elif isinstance(title, str) and title:
        spec["title"] = {"text": title}

    return spec


def _translate_waterfall(traces: list[dict], layout: dict) -> dict[str, Any]:
    """Translate waterfall chart. Plotly waterfall uses x/y plus measure array."""
    trace = traces[0]
    x_vals = _coerce_array(trace.get("x"))
    y_vals = _coerce_array(trace.get("y"))
    measures = _coerce_array(trace.get("measure")) or ["relative"] * len(x_vals)

    data_values = [
        {"x": str(x), "y": y, "measure": m}
        for x, y, m in zip(x_vals, y_vals, measures)
    ]

    spec: dict[str, Any] = {
        "type": "common",
        "data": [{"id": "data", "values": data_values}],
        "series": [{
            "type": "waterfall",
            "xField": "x",
            "yField": "y",
        }],
    }

    title = layout.get("title", {})
    if isinstance(title, dict) and title.get("text"):
        spec["title"] = {"text": title["text"]}
    elif isinstance(title, str) and title:
        spec["title"] = {"text": title}

    return spec
