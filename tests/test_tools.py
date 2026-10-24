from __future__ import annotations

from pydantic import BaseModel

from qqbot.runtime.simple import SimpleRuntime
from qqbot.tools.registry import Tool, ToolRegistry


class EchoParams(BaseModel):
    text: str


class FakeLLM:
    def __init__(self, tool_responses: list | None = None) -> None:
        self.tool_responses = list(tool_responses or [])
        self.calls: list[str] = []

    async def complete(self, messages):
        self.calls.append("complete")
        return "plain", 1

    async def complete_with_tools(self, messages, tools=None):
        self.calls.append("tools")
        return self.tool_responses.pop(0)


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def echo(text: str) -> str:
        return f"echo:{text}"

    registry.register(Tool("echo", "回声", EchoParams, echo))
    return registry


async def test_tool_schema():
    registry = _echo_registry()
    schema = registry.openai_schemas()[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert "text" in schema["function"]["parameters"]["properties"]


async def test_tool_run_and_unknown():
    registry = _echo_registry()
    assert await registry.run("echo", {"text": "hi"}) == "echo:hi"
    assert "没有名为" in await registry.run("nope", {})


async def test_runtime_without_tools_uses_plain_complete():
    llm = FakeLLM()
    runtime = SimpleRuntime(llm, _echo_registry(), enabled=False)
    content, tokens = await runtime.run([{"role": "user", "content": "hi"}])
    assert content == "plain"
    assert tokens == 1
    assert llm.calls == ["complete"]


async def test_runtime_runs_tool_loop():
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "echo", "arguments": '{"text":"hi"}'},
    }
    llm = FakeLLM([("", 5, [tool_call]), ("done", 7, [])])
    runtime = SimpleRuntime(llm, _echo_registry(), enabled=True)
    content, tokens = await runtime.run([{"role": "user", "content": "hi"}])
    assert content == "done"
    assert tokens == 12
    assert llm.calls == ["tools", "tools"]
