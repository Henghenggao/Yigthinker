"""Integration tests for YigthinkerTUI using Textual Pilot."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

_TEST_SIZE = (80, 24)


# TUI-01: Connect to Gateway and display chat log with markdown
@pytest.mark.asyncio
async def test_tui_app_mounts_chat_screen():
    """TUI app mounts ChatScreen with ChatLog, VarsPanel, StatusBar, InputBar."""
    from yigthinker.tui.app import YigthinkerTUI

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            chat_log = app.screen.query_one("#chat-log")
            assert chat_log is not None
            vars_panel = app.screen.query_one("#vars-panel")
            assert vars_panel is not None
            status_bar = app.screen.query_one("#status-bar")
            assert status_bar is not None
            input_bar = app.screen.query_one("#input-bar")
            assert input_bar is not None


# TUI-01: ChatLog renders markdown
@pytest.mark.asyncio
async def test_chat_log_append_response():
    """ChatLog.append_response renders Rich Markdown."""
    from yigthinker.tui.app import YigthinkerTUI
    from yigthinker.tui.widgets.chat_log import ChatLog

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            chat_log = app.screen.query_one("#chat-log")
            assert isinstance(chat_log, ChatLog)
            # This should not raise -- Markdown is a valid ConsoleRenderable
            chat_log.append_response("# Hello\n\nThis is **bold** text")
            chat_log.append_user("test message")
            chat_log.append_error("test error")


# TUI-03: Keyboard shortcuts open correct screens
@pytest.mark.asyncio
async def test_keyboard_shortcut_session_picker():
    """Ctrl+G opens SessionPickerScreen."""
    from yigthinker.tui.app import YigthinkerTUI
    from yigthinker.tui.screens.session_picker import SessionPickerScreen

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+g")
            assert any(isinstance(s, SessionPickerScreen) for s in app.screen_stack)


@pytest.mark.asyncio
async def test_keyboard_shortcut_model_picker():
    """Ctrl+L opens ModelPickerScreen."""
    from yigthinker.tui.app import YigthinkerTUI
    from yigthinker.tui.screens.model_picker import ModelPickerScreen

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+l")
            assert any(isinstance(s, ModelPickerScreen) for s in app.screen_stack)


# TUI-03: Ctrl+D opens DataFrame preview
@pytest.mark.asyncio
async def test_keyboard_shortcut_dataframe_preview():
    """Ctrl+D opens DataFramePreviewScreen when vars data is available."""
    from yigthinker.tui.app import YigthinkerTUI
    from yigthinker.tui.screens.dataframe_preview import DataFramePreviewScreen

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            # Inject vars data so the preview has something to show
            app._vars_data = [
                {
                    "name": "df1",
                    "shape": [10, 3],
                    "dtypes": {"a": "int64", "b": "float64", "c": "object"},
                },
            ]
            await pilot.press("ctrl+d")
            assert any(
                isinstance(s, DataFramePreviewScreen) for s in app.screen_stack
            )


@pytest.mark.asyncio
async def test_keyboard_shortcut_dataframe_preview_empty():
    """Ctrl+D shows error when no vars data available."""
    from yigthinker.tui.app import YigthinkerTUI
    from yigthinker.tui.screens.dataframe_preview import DataFramePreviewScreen

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            # No vars data set -- should show error, not crash
            await pilot.press("ctrl+d")
            # Should NOT push a DataFramePreviewScreen
            assert not any(
                isinstance(s, DataFramePreviewScreen) for s in app.screen_stack
            )


# TUI-05: StatusBar shows connection state
@pytest.mark.asyncio
async def test_status_bar_reflects_state():
    """StatusBar updates when connection state changes."""
    from yigthinker.tui.app import YigthinkerTUI

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()
            status_bar = app.screen.query_one("#status-bar")
            # Simulate state change
            app._on_state_change("connected")
            await pilot.pause()
            rendered = str(status_bar.render())
            assert "connected" in rendered
