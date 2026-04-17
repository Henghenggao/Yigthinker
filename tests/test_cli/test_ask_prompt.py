from unittest.mock import patch
from yigthinker.presence.cli.ask_prompt import ask_user_permission, PermissionAnswer


async def test_user_approves():
    with patch("yigthinker.presence.cli.ask_prompt._prompt_user", return_value="y"):
        answer = await ask_user_permission("sql_query", {"query": "SELECT * FROM orders"})
    assert answer == PermissionAnswer.ALLOW


async def test_user_denies():
    with patch("yigthinker.presence.cli.ask_prompt._prompt_user", return_value="n"):
        answer = await ask_user_permission("df_transform", {"code": "result = df"})
    assert answer == PermissionAnswer.DENY


async def test_user_allows_all():
    with patch("yigthinker.presence.cli.ask_prompt._prompt_user", return_value="a"):
        answer = await ask_user_permission("sql_query", {})
    assert answer == PermissionAnswer.ALLOW_ALL
