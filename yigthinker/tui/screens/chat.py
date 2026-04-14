from __future__ import annotations

from yigthinker.tui._import_error import TEXTUAL_IMPORT_ERROR

try:
    from textual.containers import Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import Footer, Header
except ImportError as exc:
    raise ImportError(TEXTUAL_IMPORT_ERROR) from exc

from yigthinker.tui.widgets.chat_log import ChatLog
from yigthinker.tui.widgets.input_bar import InputBar
from yigthinker.tui.widgets.status_bar import StatusBar
from yigthinker.tui.widgets.vars_panel import VarsPanel


class ChatScreen(Screen[None]):
    def __init__(self, session_key: str) -> None:
        super().__init__()
        self._session_key = session_key

    def compose(self):
        yield Header()
        with Horizontal():
            with Vertical(id="chat-panel"):
                yield ChatLog(id="chat-log", highlight=True, markup=True)
                yield InputBar()
            yield VarsPanel(id="vars-panel")
        yield StatusBar(id="status-bar")
        yield Footer()
