"""Unit tests for TUI widgets."""
from __future__ import annotations


import pytest


# -- TUI-02: VarsPanel shows variables -----------------------------------------
class TestVarsPanel:
    def test_vars_panel_display_with_data(self):
        """VarsPanel.update_vars renders name, shape, and column names."""
        from yigthinker.presence.tui.widgets.vars_panel import VarsPanel

        panel = VarsPanel(id="test-panel")
        vars_data = [
            {
                "name": "df1",
                "shape": [100, 5],
                "dtypes": {"col_a": "int64", "col_b": "float64", "col_c": "object"},
                "var_type": "dataframe",
            },
            {
                "name": "chart1",
                "shape": [0, 0],
                "dtypes": {},
                "var_type": "chart",
            },
        ]
        panel.update_vars(vars_data)
        rendered = str(panel.render())
        assert "df1" in rendered
        assert "100x5" in rendered
        assert "col_a" in rendered
        assert "chart1" in rendered

    def test_vars_panel_empty(self):
        """VarsPanel shows 'No variables' when list is empty."""
        from yigthinker.presence.tui.widgets.vars_panel import VarsPanel

        panel = VarsPanel(id="test-panel")
        panel.update_vars([])
        rendered = str(panel.render())
        assert "No variables" in rendered


# -- TUI-05: StatusBar connection state colors ---------------------------------
class TestStatusBar:
    def test_status_bar_connected(self):
        """StatusBar shows green for connected state."""
        from yigthinker.presence.tui.widgets.status_bar import StatusBar

        bar = StatusBar(id="test-bar")
        bar.set_status(session="test", state="connected")
        content = bar.render()
        assert "connected" in str(content)
        assert any("green" in str(s.style) for s in content.spans)

    def test_status_bar_disconnected(self):
        """StatusBar shows red for disconnected state."""
        from yigthinker.presence.tui.widgets.status_bar import StatusBar

        bar = StatusBar(id="test-bar")
        bar.set_status(session="test", state="disconnected")
        content = bar.render()
        assert "disconnected" in str(content)
        assert any("red" in str(s.style) for s in content.spans)

    def test_status_bar_reconnecting(self):
        """StatusBar shows yellow for reconnecting state."""
        from yigthinker.presence.tui.widgets.status_bar import StatusBar

        bar = StatusBar(id="test-bar")
        bar.set_status(session="test", state="reconnecting")
        content = bar.render()
        assert "reconnecting" in str(content)
        assert any("yellow" in str(s.style) for s in content.spans)


# -- TUI-06: ToolCard collapse/expand ------------------------------------------
class TestToolCard:
    def test_tool_card_starts_collapsed(self):
        """ToolCard defaults to collapsed state."""
        from yigthinker.presence.tui.widgets.tool_card import ToolCard

        card = ToolCard(tool_name="sql_query")
        assert card.collapsed is True

    def test_tool_card_toggle(self):
        """ToolCard.toggle_collapsed() flips state."""
        from yigthinker.presence.tui.widgets.tool_card import ToolCard

        card = ToolCard(tool_name="sql_query")
        card.toggle_collapsed()
        assert card.collapsed is False
        card.toggle_collapsed()
        assert card.collapsed is True

    def test_tool_card_set_result(self):
        """ToolCard.set_result() stores content and error state."""
        from yigthinker.presence.tui.widgets.tool_card import ToolCard

        card = ToolCard(tool_name="sql_query")
        card.set_result("5 rows returned", is_error=False)
        assert card._has_result is True
        assert card._result_content == "5 rows returned"
        assert card._is_error is False


# -- TUI-07: InputBar slash command autocomplete --------------------------------
class TestSlashCommandSuggester:
    @pytest.mark.asyncio
    async def test_suggest_on_slash_prefix(self):
        """Suggester returns matching command when input starts with /."""
        from yigthinker.presence.tui.widgets.input_bar import SlashCommandSuggester

        s = SlashCommandSuggester(commands=["/help", "/clear", "/model"])
        result = await s.get_suggestion("/he")
        assert result == "/help"

    @pytest.mark.asyncio
    async def test_no_suggest_without_slash(self):
        """Suggester returns None when input does not start with /."""
        from yigthinker.presence.tui.widgets.input_bar import SlashCommandSuggester

        s = SlashCommandSuggester(commands=["/help", "/clear"])
        result = await s.get_suggestion("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_suggest_exact_match(self):
        """Suggester returns None when input exactly matches a command."""
        from yigthinker.presence.tui.widgets.input_bar import SlashCommandSuggester

        s = SlashCommandSuggester(commands=["/help"])
        result = await s.get_suggestion("/help")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggest_case_insensitive(self):
        """Suggester matches case-insensitively."""
        from yigthinker.presence.tui.widgets.input_bar import SlashCommandSuggester

        s = SlashCommandSuggester(commands=["/Help", "/Clear"])
        result = await s.get_suggestion("/he")
        assert result == "/Help"
