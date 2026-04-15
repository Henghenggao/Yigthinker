# tests/test_channels/test_feishu_cards.py
"""Tests for FeishuCardRenderer including chart image, VChart native, and native table."""

from yigthinker.channels.feishu.cards import FeishuCardRenderer


def test_render_chart_image_without_interactive_url():
    renderer = FeishuCardRenderer()
    card = renderer.render_chart_image("Sales Q1", "img_v2_abc123")

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "Sales Q1"
    assert card["header"]["template"] == "blue"

    elements = card["elements"]
    assert len(elements) == 1

    img = elements[0]
    assert img["tag"] == "img"
    assert img["img_key"] == "img_v2_abc123"
    assert img["alt"] == {"tag": "plain_text", "content": "Sales Q1"}


def test_render_chart_image_with_interactive_url():
    renderer = FeishuCardRenderer()
    card = renderer.render_chart_image(
        "Sales Q1",
        "img_v2_abc123",
        interactive_url="https://gw.local/api/charts/abc",
    )

    elements = card["elements"]
    assert len(elements) == 2

    img = elements[0]
    assert img["tag"] == "img"
    assert img["img_key"] == "img_v2_abc123"

    action = elements[1]
    assert action["tag"] == "action"
    assert len(action["actions"]) == 1
    button = action["actions"][0]
    assert button["tag"] == "button"
    assert button["text"]["content"] == "Open Interactive"
    assert button["type"] == "primary"
    assert button["url"] == "https://gw.local/api/charts/abc"


def test_render_vchart_native():
    renderer = FeishuCardRenderer()
    vchart_spec = {"type": "bar", "data": {"values": [{"x": "A", "y": 1}]}}
    card = renderer.render_vchart_native("Revenue", vchart_spec)

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "Revenue"
    assert card["header"]["template"] == "blue"

    elements = card["elements"]
    assert len(elements) == 1

    chart = elements[0]
    assert chart["tag"] == "chart"
    assert chart["chart_spec"]["type"] == "vchart"
    assert chart["chart_spec"]["data"] == vchart_spec
    assert chart["height"] == "380px"


def test_render_native_table_without_truncation():
    renderer = FeishuCardRenderer()
    columns = ["region", "revenue"]
    rows = [["EU", "100"], ["US", "200"]]
    card = renderer.render_native_table("Revenue by region", columns, rows, total_rows=2)

    assert card["config"]["wide_screen_mode"] is True
    assert card["header"]["title"]["content"] == "Revenue by region"
    assert card["header"]["template"] == "blue"

    elements = card["elements"]
    # Only the table element; no note element
    assert len(elements) == 1
    table = elements[0]
    assert table["tag"] == "table"
    assert table["page_size"] == 2  # min(len(rows)=2, 10)

    # Columns built as dicts with name/display_name
    assert table["columns"] == [
        {"name": "region", "display_name": "region"},
        {"name": "revenue", "display_name": "revenue"},
    ]

    # Rows built as dicts keyed by column names
    assert table["rows"] == [
        {"region": "EU", "revenue": "100"},
        {"region": "US", "revenue": "200"},
    ]


def test_render_native_table_with_truncation():
    renderer = FeishuCardRenderer()
    columns = ["id", "name"]
    rows = [["1", "a"], ["2", "b"]]
    card = renderer.render_native_table("Users", columns, rows, total_rows=10)

    elements = card["elements"]
    assert len(elements) == 2

    note = elements[-1]
    assert note["tag"] == "note"
    inner = note["elements"][0]
    assert inner["tag"] == "plain_text"
    assert inner["content"] == "Showing 2 of 10 rows"


def test_render_native_table_rows_are_dicts_keyed_by_columns():
    renderer = FeishuCardRenderer()
    columns = ["a", "b", "c"]
    rows = [["1", "2", "3"], ["4", "5", "6"]]
    card = renderer.render_native_table("T", columns, rows, total_rows=2)

    table = card["elements"][0]
    assert table["rows"][0] == {"a": "1", "b": "2", "c": "3"}
    assert table["rows"][1] == {"a": "4", "b": "5", "c": "6"}


def test_render_native_table_page_size_caps_at_10():
    renderer = FeishuCardRenderer()
    columns = ["n"]
    rows = [[str(i)] for i in range(15)]
    card = renderer.render_native_table("Many", columns, rows, total_rows=100)

    table = card["elements"][0]
    assert table["page_size"] == 10


def test_render_native_table_page_size_small_row_count():
    renderer = FeishuCardRenderer()
    columns = ["n"]
    rows = [["1"], ["2"], ["3"]]
    card = renderer.render_native_table("Few", columns, rows, total_rows=3)

    table = card["elements"][0]
    assert table["page_size"] == 3
