from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(slots=True)
class Tool:
    """暴露给 LLM 的工具；参数用 pydantic 模型描述。"""

    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[..., Awaitable[str]]
    source: str = "builtin"
    scopes: tuple[str, ...] = field(default_factory=tuple)


class ToolRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._items:
            raise ValueError(f"工具重复注册: {tool.name}")
        self._items[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._items.get(name)

    def all(self) -> list[Tool]:
        return list(self._items.values())

    def openai_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.params.model_json_schema(),
                },
            }
            for tool in self._items.values()
        ]

    async def run(self, name: str, arguments: dict) -> str:
        tool = self._items.get(name)
        if tool is None:
            return f"错误：没有名为 {name} 的工具"
        try:
            payload = tool.params(**arguments)
        except Exception as exc:  # noqa: BLE001
            return f"错误：参数不合法（{exc}）"
        try:
            return await tool.handler(**payload.model_dump())
        except Exception as exc:  # noqa: BLE001
            return f"错误：工具执行失败（{exc}）"
