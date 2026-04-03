"""Tests for WebSocket message protocol."""
import pytest

from yigthinker.gateway.protocol import (
    AttachMsg,
    AuthMsg,
    ErrorMsg,
    ResponseDoneMsg,
    UserInputMsg,
    VarsUpdateMsg,
    parse_client_msg,
    to_json_dict,
)


def test_to_json_dict():
    msg = AuthMsg(token="abc123")
    d = to_json_dict(msg)
    assert d == {"type": "auth", "token": "abc123"}


def test_parse_auth():
    msg = parse_client_msg({"type": "auth", "token": "abc"})
    assert isinstance(msg, AuthMsg)
    assert msg.token == "abc"


def test_parse_attach():
    msg = parse_client_msg({"type": "attach", "session_key": "tui:user1"})
    assert isinstance(msg, AttachMsg)
    assert msg.session_key == "tui:user1"


def test_parse_user_input():
    msg = parse_client_msg({"type": "user_input", "text": "hello", "request_id": "r1"})
    assert isinstance(msg, UserInputMsg)
    assert msg.text == "hello"
    assert msg.request_id == "r1"


def test_parse_unknown_type():
    with pytest.raises(ValueError, match="Unknown"):
        parse_client_msg({"type": "bogus"})


def test_server_messages_serialize():
    msg = ResponseDoneMsg(full_text="Done", request_id="r1")
    d = to_json_dict(msg)
    assert d["type"] == "response_done"
    assert d["full_text"] == "Done"


def test_vars_update():
    msg = VarsUpdateMsg(vars=[{"name": "df1", "shape": (10, 3)}])
    d = to_json_dict(msg)
    assert d["type"] == "vars_update"
    assert len(d["vars"]) == 1


def test_error_msg():
    msg = ErrorMsg(message="something broke")
    d = to_json_dict(msg)
    assert d["type"] == "error"
    assert d["message"] == "something broke"
