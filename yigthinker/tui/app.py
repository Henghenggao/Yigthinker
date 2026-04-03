"""Yigthinker TUI: Textual-based terminal client for the Gateway."""
from __future__ import annotations

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
        self._tools_collapsed = False
        self._sessions: list[dict[str, Any]] = []
        self._vars_data: list[dict[str, Any]] = []
        self._ws_client = GatewayWSClient(
            url=gateway_url,
            token=token,
            on_message=self._on_ws_message,
            on_state_change=self._on_state_change,
        )

    async def on_mount(self) -> None:
        self.push_screen(ChatScreen(session_key=self._session_key))
        self.run_worker(self._ws_client.connect_loop(), exclusive=True)
        self._status_bar.set_status(session=self._session_key, state="connecting")

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
        return self.query_one("#chat-log", ChatLog)

    @property
    def _vars_panel(self) -> VarsPanel:
        return self.query_one("#vars-panel", VarsPanel)

    @property
    def _status_bar(self) -> StatusBar:
        return self.query_one("#status-bar", StatusBar)

    def _on_ws_message(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type", "")

        if msg_type == "response_done":
            self._chat_log.append_response(data.get("full_text", ""))
        elif msg_type == "tool_call":
            self._chat_log.append_tool_call(
                data.get("tool_name", ""),
                tool_input=data.get("tool_input"),
            )
        elif msg_type == "tool_result":
            self._chat_log.append_tool_result(
                data.get("content", ""),
                is_error=data.get("is_error", False),
            )
        elif msg_type == "vars_update":
            self._vars_data = data.get("vars", [])
            self._vars_panel.update_vars(self._vars_data)
        elif msg_type == "session_list":
            self._sessions = data.get("sessions", [])
        elif msg_type == "error":
            self._chat_log.append_error(data.get("message", ""))
        elif msg_type == "auth_result" and data.get("ok"):
            self.run_worker(self._ws_client.attach_session(self._session_key))

    def _on_state_change(self, state: str) -> None:
        try:
            self._status_bar.set_status(session=self._session_key, state=state)
            input_bar = self.query_one("#input-bar", InputBar)
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
        state = "collapsed" if self._tools_collapsed else "expanded"
        self._chat_log.append_response(f"[dim](tool cards {state})[/]")
