import pytest
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext
from yigthinker.tools.base import YigthinkerTool
from yigthinker.tools.registry import ToolRegistry


class EchoInput(BaseModel):
    message: str


class EchoTool:
    name = "echo"
    description = "Echoes the message back"
    input_schema = EchoInput
    is_concurrency_safe = False

    async def execute(self, input: EchoInput, ctx: SessionContext) -> ToolResult:
        return ToolResult(tool_use_id="", content=f"echo: {input.message}")


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(EchoTool())
    tool = reg.get("echo")
    assert tool.name == "echo"


def test_get_missing_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="no_such_tool"):
        reg.get("no_such_tool")


def test_export_schemas():
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.export_schemas()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["name"] == "echo"
    assert schema["description"] == "Echoes the message back"
    assert "properties" in schema["input_schema"]
    assert "message" in schema["input_schema"]["properties"]


def test_names():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert "echo" in reg.names()


def test_echo_tool_is_yigthinker_tool():
    assert isinstance(EchoTool(), YigthinkerTool)
