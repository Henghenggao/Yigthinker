"""Yigthinker TUI: Textual-based terminal client for the Gateway."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

try:
    from textual.app import App
except ImportError as exc:
    raise ImportError(
        "TUI requires the 'textual' package. Install with: pip install yigthinker[tui]"
    ) from exc

from yigthinker.tui.screens.chat import ChatScreen
from yigthinker.tui.screens.model_picker import ModelPickerScreen
from yigthinker.tui.screens.session_picker import SessionPickerScreen
from yigthinker.tui.widgets.chat_log import ChatLog
from yigthinker.tui.widgets.input_bar import InputBar
from yigthinker.tui.widgets.status_bar import StatusBar
from yigthinker.tui.widgets.tool_card import ToolCard
from yigthinker.tui.widgets.vars_panel import VarsPanel
from yigthinker.tui.ws_client import GatewayWSClient


class YigthinkerTUI(App):
    TITLE = "Yigthinker"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+g", "show_session_picker", "Sessions"),
        ("ctrl+l", "show_model_picker", "Models"),
        ("ctrl+d", "preview_dataframe", "Preview"),
        ("ctrl+t", "toggle_thinking", "Thinking"),
        ("ctrl+o", "toggle_tools", "Tools"),
    ]

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:8766/ws",
        token: str = "",
        session_key: str = "",
    ) -> None:
        super().__init__()
        self._gateway_url = gateway_url
        self._token = token
        self._session_key = session_key or f"tui:{uuid.uuid4().hex[:8]}"
        self._show_thinking = False
        self._tools_collapsed = True
        self._tool_cards: list[ToolCard] = []
        self._sessions: list[dict[str, Any]] = []
        self._vars_data: list[dict[str, Any]] = []
        self._stream: Any = None  # MarkdownStream handle, set during active streaming
        self._stream_widget: Any = None  # Markdown widget mounted for streaming
        self._stream_cursor: Any = None  # Static widget with blinking cursor (D-12)
        self._cursor_visible: bool = True
        self._cursor_timer: Any = None

        self._ws_client = GatewayWSClient(
            url=gateway_url,
            token=token,
            on_message=self._on_ws_message,
            on_state_change=self._on_state_change,
        )

    async def on_mount(self) -> None:
        self.push_screen(ChatScreen(session_key=self._session_key))
        self.run_worker(self._ws_client.connect_loop(), exclusive=True)
        try:
            self._status_bar.set_status(session=self._session_key, state="connecting")
        except Exception:
            pass  # Widget not yet mounted during early state changes

    async def on_input_submitted(self, event: InputBar.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.clear()
        self._chat_log.append_user(text)

        try:
            await self._ws_client.send_input(text)
        except Exception as exc:
            self._chat_log.append_error(str(exc))

    @property
    def _chat_log(self) -> ChatLog:
        return self.screen.query_one("#chat-log", ChatLog)

    @property
    def _vars_panel(self) -> VarsPanel:
        return self.screen.query_one("#vars-panel", VarsPanel)

    @property
    def _status_bar(self) -> StatusBar:
        return self.screen.query_one("#status-bar", StatusBar)

    def _on_ws_message(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type", "")

        if msg_type == "token":
            text = data.get("text", "")
            if text:
                try:
                    if self._stream is None:
                        # Start new streaming response per amended D-10:
                        # Mount a temporary Markdown widget, use MarkdownStream for incremental rendering
                        from textual.widgets import Markdown as MdWidget, Static
                        self._stream_widget = MdWidget("", id="streaming-md")
                        chat_panel = self.screen.query_one("#chat-panel")
                        input_bar = self.screen.query_one("#input-bar")
                        chat_panel.mount(self._stream_widget, before=input_bar)
                        self._stream = MdWidget.get_stream(self._stream_widget)

                        # D-12: Mount blinking cursor after the streaming widget
                        self._stream_cursor = Static("\u258c", id="stream-cursor")
                        chat_panel.mount(self._stream_cursor, before=input_bar)

                        # D-12: Start blink timer
                        self._cursor_visible = True
                        self._cursor_timer = self.set_interval(0.5, self._blink_cursor)

                    asyncio.ensure_future(self._stream.write(text))
                except Exception:
                    pass
            return

        if msg_type == "response_done":
            if self._stream is not None:
                # Finalize streaming -- stop the stream, remove temp widget, render final Markdown
                try:
                    asyncio.ensure_future(self._finalize_stream(data.get("full_text", "")))
                except Exception:
                    pass
            else:
                # Non-streaming path (unchanged)
                self._chat_log.append_response(data.get("full_text", ""))
        elif msg_type == "tool_call":
            # Per D-11: if streaming, finalize current text block before showing ToolCard
            if self._stream is not None:
                asyncio.ensure_future(self._handle_tool_call_midstream(data))
            else:
                self._mount_tool_card(data)
        elif msg_type == "tool_result":
            content = data.get("content", "")
            is_error = data.get("is_error", False)
            # Update the most recent tool card with the result
            if self._tool_cards:
                self._tool_cards[-1].set_result(content, is_error=is_error)
        elif msg_type == "vars_update":
            self._vars_data = data.get("vars", [])
            self._vars_panel.update_vars(self._vars_data)
        elif msg_type == "session_list":
            self._sessions = data.get("sessions", [])
        elif msg_type == "error":
            self._chat_log.append_error(data.get("message", ""))
        elif msg_type == "auth_result" and data.get("ok"):
            self.run_worker(self._ws_client.attach_session(self._session_key))

    def _mount_tool_card(self, data: dict[str, Any]) -> None:
        """Mount a ToolCard widget in the chat-panel."""
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        card = ToolCard(
            tool_name=tool_name,
            tool_input=tool_input,
            collapsed=self._tools_collapsed,
        )
        self._tool_cards.append(card)
        try:
            chat_panel = self.screen.query_one("#chat-panel")
            chat_panel.mount(card, before=self.screen.query_one("#input-bar"))
        except Exception:
            pass  # Widget not yet mounted during early messages

    async def _handle_tool_call_midstream(self, data: dict[str, Any]) -> None:
        """Stop streaming, remove cursor, then mount ToolCard (D-11, D-12)."""
        try:
            if self._stream is not None:
                await self._stream.stop()
            # D-12: Stop cursor blink timer
            if self._cursor_timer is not None:
                self._cursor_timer.stop()
                self._cursor_timer = None
            # D-12: Remove cursor on mid-stream tool call
            if self._stream_cursor is not None:
                await self._stream_cursor.remove()
        except Exception:
            pass
        finally:
            self._stream = None
            self._stream_widget = None
            self._stream_cursor = None
        self._mount_tool_card(data)

    async def _finalize_stream(self, full_text: str) -> None:
        """Stop the MarkdownStream, remove cursor and temp widget, write final text to ChatLog."""
        try:
            if self._stream is not None:
                await self._stream.stop()
            # D-12: Stop cursor blink timer
            if self._cursor_timer is not None:
                self._cursor_timer.stop()
                self._cursor_timer = None
            # D-12: Remove the blinking cursor
            if self._stream_cursor is not None:
                await self._stream_cursor.remove()
            if self._stream_widget is not None:
                await self._stream_widget.remove()
        except Exception:
            pass
        finally:
            self._stream = None
            self._stream_widget = None
            self._stream_cursor = None
        # Write the final complete text to the ChatLog as rendered Markdown
        self._chat_log.append_response(full_text)

    def _blink_cursor(self) -> None:
        """Toggle cursor visibility for blinking effect (D-12)."""
        if self._stream_cursor is not None:
            self._cursor_visible = not self._cursor_visible
            self._stream_cursor.display = self._cursor_visible
        else:
            # Cursor removed, stop timer
            if self._cursor_timer is not None:
                self._cursor_timer.stop()
                self._cursor_timer = None

    def _on_state_change(self, state: str) -> None:
        try:
            self._status_bar.set_status(session=self._session_key, state=state)
            input_bar = self.screen.query_one("#input-bar", InputBar)
            input_bar.disabled = state != "connected"
        except Exception:
            pass  # Widget not yet mounted during early state changes

    def action_show_session_picker(self) -> None:
        def on_session_selected(key: str | None) -> None:
            if key is not None and key != self._session_key:
                self._session_key = key
                self._chat_log.append_response(f"Switched to session: {key}")
                self.run_worker(self._ws_client.attach_session(key))
        self.push_screen(SessionPickerScreen(sessions=self._sessions), callback=on_session_selected)

    def action_show_model_picker(self) -> None:
        def on_model_selected(model: str | None) -> None:
            if model is not None:
                self._chat_log.append_response(f"Model set to: {model}")
                # Model switching will be wired when Gateway supports it
        self.push_screen(ModelPickerScreen(), callback=on_model_selected)

    def action_preview_dataframe(self) -> None:
        if not self._vars_data:
            self._chat_log.append_error("No variables available for preview")
            return
        # Preview the first variable
        first_var = self._vars_data[0]
        name = first_var.get("name", "unknown")
        # For Phase 3, show metadata as preview since we don't have row data from Gateway
        preview_rows = [first_var.get("dtypes", {})] if first_var.get("dtypes") else []
        from yigthinker.tui.screens.dataframe_preview import DataFramePreviewScreen
        self.push_screen(DataFramePreviewScreen(name=name, data=preview_rows))

    def action_toggle_thinking(self) -> None:
        self._show_thinking = not self._show_thinking
        state = "shown" if self._show_thinking else "hidden"
        self._chat_log.append_response(f"[dim](thinking tokens {state})[/]")

    def action_toggle_tools(self) -> None:
        self._tools_collapsed = not self._tools_collapsed
        for card in self._tool_cards:
            card.collapsed = self._tools_collapsed
