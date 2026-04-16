# tests/test_channels/test_teams_cards.py
"""Tests for TeamsCardRenderer including progress cards."""

from yigthinker.channels.teams.cards import TeamsCardRenderer


def test_render_text_card():
    renderer = TeamsCardRenderer()
    card = renderer.render_text("Hello world")
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert card["body"][0]["text"] == "Hello world"


def test_render_tool_progress():
    renderer = TeamsCardRenderer()
    card = renderer.render_tool_progress("sql_query", "Returned 42 rows")

    assert card["type"] == "AdaptiveCard"
    assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"
    assert card["version"] == "1.5"

    body = card["body"]
    assert len(body) == 1
    column_set = body[0]
    assert column_set["type"] == "ColumnSet"

    columns = column_set["columns"]
    assert len(columns) == 2

    # First column: tool name (bold, small)
    tool_col = columns[0]
    assert tool_col["width"] == "auto"
    assert tool_col["items"][0]["text"] == "sql_query"
    assert tool_col["items"][0]["weight"] == "Bolder"
    assert tool_col["items"][0]["size"] == "Small"

    # Second column: summary (wrapping, small)
    summary_col = columns[1]
    assert summary_col["width"] == "stretch"
    assert summary_col["items"][0]["text"] == "Returned 42 rows"
    assert summary_col["items"][0]["wrap"] is True
    assert summary_col["items"][0]["size"] == "Small"


def test_render_error_card():
    renderer = TeamsCardRenderer()
    card = renderer.render_error("Something broke")
    assert card["type"] == "AdaptiveCard"
    assert card["body"][0]["text"] == "Error"
    assert card["body"][1]["text"] == "Something broke"


def test_render_chart_image_without_interactive_url():
    renderer = TeamsCardRenderer()
    card = renderer.render_chart_image("Sales Q1", "https://gw.local/api/charts/abc.png")

    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"

    body = card["body"]
    assert body[0]["type"] == "TextBlock"
    assert body[0]["text"] == "Sales Q1"
    assert body[0]["weight"] == "Bolder"
    assert body[0]["size"] == "Medium"

    assert body[1]["type"] == "Image"
    assert body[1]["url"] == "https://gw.local/api/charts/abc.png"
    assert body[1]["size"] == "Stretch"

    # No interactive url => no actions key
    assert "actions" not in card


def test_render_chart_image_with_interactive_url():
    renderer = TeamsCardRenderer()
    card = renderer.render_chart_image(
        "Sales Q1",
        "https://gw.local/api/charts/abc.png",
        interactive_url="https://gw.local/api/charts/abc",
    )

    assert "actions" in card
    assert len(card["actions"]) == 1
    action = card["actions"][0]
    assert action["type"] == "Action.OpenUrl"
    assert action["title"] == "Open Interactive"
    assert action["url"] == "https://gw.local/api/charts/abc"


def test_render_native_table_without_truncation():
    renderer = TeamsCardRenderer()
    columns = ["region", "revenue"]
    rows = [["EU", "100"], ["US", "200"]]
    card = renderer.render_native_table("Revenue by region", columns, rows, total_rows=2)

    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"

    body = card["body"]
    # [title, Table] — no subtitle when total_rows == len(rows)
    assert len(body) == 2
    assert body[0]["type"] == "TextBlock"
    assert body[0]["text"] == "Revenue by region"
    assert body[0]["weight"] == "Bolder"
    assert body[0]["size"] == "Medium"

    table = body[1]
    assert table["type"] == "Table"
    assert len(table["columns"]) == 2
    assert all(c == {"width": 1} for c in table["columns"])

    table_rows = table["rows"]
    # Header + 2 data rows
    assert len(table_rows) == 3

    header = table_rows[0]
    assert header["type"] == "TableRow"
    assert header["style"] == "accent"
    for cell, expected_text in zip(header["cells"], columns):
        assert cell["type"] == "TableCell"
        block = cell["items"][0]
        assert block["type"] == "TextBlock"
        assert block["text"] == expected_text
        assert block["weight"] == "Bolder"

    # Data rows — no accent style, cells contain wrapping TextBlocks
    for data_row, expected in zip(table_rows[1:], rows):
        assert data_row["type"] == "TableRow"
        assert data_row.get("style") != "accent"
        for cell, expected_val in zip(data_row["cells"], expected):
            assert cell["type"] == "TableCell"
            block = cell["items"][0]
            assert block["type"] == "TextBlock"
            assert block["text"] == expected_val
            assert block["wrap"] is True


def test_render_native_table_with_truncation():
    renderer = TeamsCardRenderer()
    columns = ["id", "name"]
    rows = [["1", "a"], ["2", "b"]]
    card = renderer.render_native_table("Users", columns, rows, total_rows=10)

    body = card["body"]
    # title, Table, subtitle
    assert len(body) == 3
    subtitle = body[2]
    assert subtitle["type"] == "TextBlock"
    assert subtitle["text"] == "Showing 2 of 10 rows"
    assert subtitle["size"] == "Small"
    assert subtitle["isSubtle"] is True


def test_render_native_table_stringifies_non_string_values():
    renderer = TeamsCardRenderer()
    card = renderer.render_native_table(
        "Mixed", ["n"], [[42], [None]], total_rows=2
    )
    table_rows = card["body"][1]["rows"]
    assert table_rows[1]["cells"][0]["items"][0]["text"] == "42"
    assert table_rows[2]["cells"][0]["items"][0]["text"] == "None"


def test_render_file_saved_with_summary():
    """kind="file" artifact card — see quick-260416-j3y."""
    renderer = TeamsCardRenderer()
    card = renderer.render_file_saved(
        "build_pl_sheet.py",
        size_bytes=4321,
        summary="Builds formatted P&L sheet",
    )
    assert card["type"] == "AdaptiveCard"
    body = card["body"]
    # title, subtitle (workspace + bytes), summary
    assert len(body) == 3
    assert body[0]["text"] == "Saved build_pl_sheet.py"
    assert body[0]["weight"] == "Bolder"
    assert "4,321 B" in body[1]["text"]
    assert body[1]["isSubtle"] is True
    assert body[2]["text"] == "Builds formatted P&L sheet"


def test_render_file_saved_without_summary():
    renderer = TeamsCardRenderer()
    card = renderer.render_file_saved("notes.md", size_bytes=12)
    body = card["body"]
    # title + subtitle only
    assert len(body) == 2
    assert body[0]["text"] == "Saved notes.md"
    assert "12 B" in body[1]["text"]
    # No OpenUrl action — workspace path is local
    assert "actions" not in card
