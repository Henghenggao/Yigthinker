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
