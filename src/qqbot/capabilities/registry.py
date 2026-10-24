from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(slots=True)
class Action:
    """一个可以发给 QQ 平台或内部复用的动作。"""

    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[..., Awaitable[Any]]
    chat_types: tuple[str, ...] = ("private",)
    expose_as_tool: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)


class ActionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Action] = {}

    def register(self, action: Action) -> None:
        if action.name in self._items:
            raise ValueError(f"动作重复注册: {action.name}")
        self._items[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._items.get(name)

    def all(self) -> list[Action]:
        return list(self._items.values())

    async def invoke(self, name: str, **kwargs: Any) -> Any:
        action = self._items.get(name)
        if action is None:
            raise KeyError(f"未知动作: {name}")
        payload = action.params(**kwargs)
        return await action.handler(**payload.model_dump())
