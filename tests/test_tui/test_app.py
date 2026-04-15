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


# STRM-04: TUI streaming creates Markdown widget on first token message
@pytest.mark.asyncio
async def test_token_streaming_creates_markdown_widget():
    """TUI creates a Markdown widget on first token message (STRM-04)."""
    from yigthinker.tui.app import YigthinkerTUI

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()

            # Simulate token messages
            app._on_ws_message({"type": "token", "text": "Hello "})
            await pilot.pause()

            # Verify streaming state is active
            assert app._stream is not None
            assert app._stream_widget is not None

            # D-12: Verify blinking cursor is mounted
            assert app._stream_cursor is not None

            # Simulate response_done to finalize
            app._on_ws_message({"type": "response_done", "full_text": "Hello world"})
            await pilot.pause()
            await pilot.pause()  # Extra pause for async finalization
            await pilot.pause()

            # Stream should be cleaned up
            assert app._stream is None
            assert app._stream_widget is None
            # D-12: Cursor should be removed
            assert app._stream_cursor is None


# D-11: TUI stops stream and shows ToolCard when tool_call arrives mid-stream
@pytest.mark.asyncio
async def test_token_streaming_handles_tool_call_midstream():
    """TUI stops stream, removes cursor, and shows ToolCard when tool_call arrives mid-stream (D-11, D-12)."""
    from yigthinker.tui.app import YigthinkerTUI

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()

            # Start streaming
            app._on_ws_message({"type": "token", "text": "Let me check"})
            await pilot.pause()
            assert app._stream is not None
            assert app._stream_cursor is not None  # D-12: cursor present

            # Tool call mid-stream -- should stop the stream and remove cursor
            app._on_ws_message({
                "type": "tool_call",
                "tool_name": "sql_query",
                "tool_input": {"query": "SELECT 1"},
                "tool_id": "tc1",
            })
            await pilot.pause()
            await pilot.pause()

            # Stream should be stopped
            assert app._stream is None
            # D-12: Cursor should be removed
            assert app._stream_cursor is None
            # ToolCard should be mounted
            assert len(app._tool_cards) == 1


# D-12: Blinking cursor lifecycle
@pytest.mark.asyncio
async def test_blinking_cursor_lifecycle():
    """D-12: Blinking cursor appears on stream start, blinks, and disappears on done."""
    from yigthinker.tui.app import YigthinkerTUI

    with patch(
        "yigthinker.tui.ws_client.GatewayWSClient.connect_loop",
        new_callable=AsyncMock,
    ):
        app = YigthinkerTUI(gateway_url="ws://localhost:1/ws", token="test")
        async with app.run_test(size=_TEST_SIZE) as pilot:
            await pilot.pause()

            # No cursor before streaming starts
            assert app._stream_cursor is None

            # Start streaming -- cursor should appear
            app._on_ws_message({"type": "token", "text": "Start"})
            await pilot.pause()
            assert app._stream_cursor is not None

            # Verify cursor timer is running (blink mechanism)
            assert app._cursor_timer is not None

            # Finalize -- cursor should be removed and timer stopped
            app._on_ws_message({"type": "response_done", "full_text": "Start complete"})
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            assert app._stream_cursor is None
            # Timer should be stopped
            assert app._cursor_timer is None
